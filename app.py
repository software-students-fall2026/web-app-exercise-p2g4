import os
import re
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError
from werkzeug.security import check_password_hash, generate_password_hash


# This is the single canonical restaurant list used by profiles and reviews.
DINING_HALLS = [
    "Downstein",
    "ThirdNorth",
    "Lipton",
    "Kosher Cafe",
    "Kimmel",
    "JasperKane",
    "Palladium",
    "Upstein",
    "Crave",
    "Flaovr Lab",
    "Cafe 181",
    "Cafe 370",
]


load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ["FLASK_SECRET_KEY"]

client = MongoClient(
    os.environ["MONGO_URI"],
    serverSelectionTimeoutMS=5000,
)

db = client[os.environ["MONGO_DB_NAME"]]

users_collection = db["users"]
reviews_collection = db["reviews"]
follows_collection = db["follows"]
dining_halls_collection = db["dining_halls"]

# Protect against duplicate usernames.
users_collection.create_index("username", unique=True)

# One user may follow another user only once.
follows_collection.create_index(
    [
        ("follower_id", ASCENDING),
        ("following_id", ASCENDING),
    ],
    unique=True,
)

# Makes profile "recent comment" lookups faster.
reviews_collection.create_index(
    [
        ("author_id", ASCENDING),
        ("created_at", DESCENDING),
    ]
)

# "slug" for each dining hall name
dining_halls_collection.create_index("slug", unique=True)

# index for each dining hall (for review search)
reviews_collection.create_index("dining_hall_name")


SAVED_LIST_FIELDS = {
    "favorites": "favorites",
    "want_to_go": "want_to_go",
}


class User(UserMixin):
    def __init__(self, user_document):
        self.id = str(user_document["_id"])
        self.username = user_document["username"]


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "error"


@login_manager.user_loader
def load_user(user_id):
    try:
        object_id = ObjectId(user_id)
    except InvalidId:
        return None

    user_document = users_collection.find_one(
        {"_id": object_id},
        {"password_hash": 0},
    )

    if user_document is None:
        return None

    return User(user_document)


def get_user_or_404(user_id):
    """Find a user without ever returning password_hash to a template."""
    try:
        object_id = ObjectId(user_id)
    except InvalidId:
        abort(404)

    user_document = users_collection.find_one(
        {"_id": object_id},
        {"password_hash": 0},
    )

    if user_document is None:
        abort(404)

    return user_document


def get_review_or_404(review_id):
    try:
        review = reviews_collection.find_one({"_id": ObjectId(review_id)})
    except InvalidId:
        abort(404)

    if review is None:
        abort(404)

    return review


def require_review_owner(review):
    """Only the original review author may edit or delete the review."""
    if review.get("author_id") != current_user.id:
        abort(403)


def get_profile_data(profile_user):
    """
    Calculate profile values from reviews/follows instead of storing
    duplicate Followers, Following, or Recent Comment fields in users.
    """
    profile_id = str(profile_user["_id"])

    followers_count = follows_collection.count_documents(
        {"following_id": profile_id}
    )

    following_count = follows_collection.count_documents(
        {"follower_id": profile_id}
    )

    recent_review = reviews_collection.find_one(
        {"author_id": profile_id},
        sort=[("created_at", DESCENDING)],
    )

    return {
        "followers_count": followers_count,
        "following_count": following_count,
        "recent_review": recent_review,
    }


def get_users_from_follows(follow_documents, related_id_field):
    """
    Convert follow documents into user documents.

    related_id_field:
    - follower_id: used on a Followers page
    - following_id: used on a Following page
    """
    object_ids = []

    for follow in follow_documents:
        try:
            object_ids.append(ObjectId(follow[related_id_field]))
        except (InvalidId, KeyError, TypeError):
            continue

    if not object_ids:
        return []

    user_documents = list(
        users_collection.find(
            {"_id": {"$in": object_ids}},
            {"password_hash": 0},
        )
    )

    users_by_id = {
        str(user_document["_id"]): user_document
        for user_document in user_documents
    }

    # Keep the order from the follows query.
    return [
        users_by_id[str(object_id)]
        for object_id in object_ids
        if str(object_id) in users_by_id
    ]


def get_review_fields_from_form():
    dining_hall_name = request.form.get("dining_hall_name", "")
    food = request.form.get("food", "").strip()
    comment = request.form.get("comment", "").strip()
    meal_date = request.form.get("meal_date", "")

    try:
        rank = int(request.form.get("rank", 0))
    except ValueError:
        rank = 0

    if dining_hall_name not in DINING_HALLS:
        return None, "Please choose a dining hall from the list."

    if not food or not meal_date:
        return None, "Please complete every required field."

    if rank not in range(1, 6):
        return None, "Rank must be a number from 1 to 5."

    return {
        "dining_hall_name": dining_hall_name,
        "food": food,
        "rank": rank,
        "comment": comment,
        "meal_date": meal_date,
    }, None


def get_favorite_restaurant_from_form():
    favorite_restaurant = request.form.get("favorite_restaurant", "")

    # Blank means the user cleared their favourite restaurant.
    if favorite_restaurant and favorite_restaurant not in DINING_HALLS:
        return None, "Please choose a restaurant from the list."

    return favorite_restaurant, None

@app.template_filter("slugify")
def make_slug(name):
    # "Slug"-ify dining hall names
    return name.lower().replace(" ", "-")

def findhall(slug):
    dining_hall = dining_halls_collection.find_one({"slug": slug})
    if dining_hall is None:
        abort(404)
    return dining_hall

def calc_avgstar(tot, cnt):
    # avg. calculator. Returns "None" if cnt==0
    if cnt==0:
        return None
    return tot/cnt

def get_stat_hall(dining_hall_name):
    reviews= reviews_collection.find({"dining_hall_name": dining_hall_name},
                                     {"rank": 1})

    tot = 0
    cnt = 0
    star_cnt = {5:0, 4:0, 3:0, 2:0, 1:0}

    for review in reviews:
        rank = review.get("rank")

        if rank not in range(1,6):
            continue

        tot= tot+rank
        cnt= cnt+1
        star_cnt[rank]= star_cnt[rank]+1

    return {
        "avg": calc_avgstar(tot, cnt),
        "cnt": cnt,
        "star_cnt": star_cnt
    }

def get_stat():
    tot= {}
    cnt= {}

    for name in DINING_HALLS:
        tot[name]= 0
        cnt[name]= 0

    reviews= reviews_collection.find(
        {},
        {"dining_hall_name":1, "rank":1}
    )

    for review in reviews:
        name = review.get("dining_hall_name")
        rank = review.get("rank")

        if name not in totals:
            continue

        if rank not in range(1,6):
            continue

        tot[name] = tot[name]+rank
        cnt[name] = cnt[name]+1

    all_stats = {}

    for name in DINING_HALLS:
        all_stats[name] = {
            "avg": calc_avgstar(tot[name], cnt[name]),
            "cnt": cnt[name]
        }


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        if not username:
            flash("Username is required.", "error")
            return render_template("signup.html", username=username), 400

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
            return render_template("signup.html", username=username), 400

        try:
            result = users_collection.insert_one(
                {
                    "username": username,
                    "password_hash": generate_password_hash(password),
                    "favorite_restaurant": "",
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            )
        except DuplicateKeyError:
            flash("That username is already taken.", "error")
            return render_template("signup.html", username=username), 400

        user_document = users_collection.find_one({"_id": result.inserted_id})
        login_user(User(user_document))

        flash("Account created. You are now logged in.", "success")
        return redirect(url_for("index"))

    return render_template("signup.html", username="")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")

        user_document = users_collection.find_one({"username": username})

        if (
            user_document is None
            or not check_password_hash(user_document["password_hash"], password)
        ):
            flash("Incorrect username or password.", "error")
            return render_template("login.html", username=username), 401

        login_user(User(user_document))
        flash("Logged in successfully.", "success")
        return redirect(url_for("index"))

    return render_template("login.html", username="")


@app.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


SORT_OPTIONS = {
    "newest": ("created_at", -1),
    "oldest": ("created_at", 1),
    "highest": ("rank", -1),
    "lowest": ("rank", 1),
}


@app.get("/")
@login_required
def index():
    selected_hall = request.args.get("dining_hall", "").strip()
    selected_user = request.args.get("user", "").strip()
    selected_sort = request.args.get("sort", "newest")
    if selected_sort not in SORT_OPTIONS:
        selected_sort = "newest"

    query = {}
    if selected_hall:
        query["dining_hall_name"] = selected_hall
    if selected_user:
        query["author_username"] = selected_user

    field, direction = SORT_OPTIONS[selected_sort]
    reviews = list(reviews_collection.find(query).sort(field, direction))

    dining_halls = sorted(h for h in reviews_collection.distinct("dining_hall_name") if h)
    usernames = sorted(u for u in reviews_collection.distinct("author_username") if u)

    return render_template(
        "index.html",
        reviews=reviews,
        dining_halls=dining_halls,
        usernames=usernames,
        selected_hall=selected_hall,
        selected_user=selected_user,
        selected_sort=selected_sort,
    )


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    profile_user = get_user_or_404(current_user.id)

    if request.method == "POST":
        favorite_restaurant, error = get_favorite_restaurant_from_form()

        if error:
            flash(error, "error")
        else:
            users_collection.update_one(
                {"_id": profile_user["_id"]},
                {
                    "$set": {
                        "favorite_restaurant": favorite_restaurant,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
            )
            flash("Profile saved.", "success")
            return redirect(url_for("profile"))

    user_reviews = list(
        reviews_collection.find(
            {"author_id": current_user.id}
        ).sort("created_at", DESCENDING)
    )

    profile_data = get_profile_data(profile_user)

    return render_template(
        "profile.html",
        profile=current_user,
        profile_user=profile_user,
        reviews=user_reviews,
        is_own_profile=True,
        is_following=False,
        favorites=profile_user.get("favorites", []),
        want_to_go=profile_user.get("want_to_go", []),
        dining_halls=DINING_HALLS,
        **profile_data,
    )


@app.get("/users/<user_id>")
@login_required
def public_profile(user_id):
    """Display another user's profile."""
    profile_user = get_user_or_404(user_id)

    # Own profile has the editable settings form.
    if str(profile_user["_id"]) == current_user.id:
        return redirect(url_for("profile"))

    is_following = (
        follows_collection.find_one(
            {
                "follower_id": current_user.id,
                "following_id": str(profile_user["_id"]),
            }
        )
        is not None
    )

    profile_data = get_profile_data(profile_user)
    user_reviews = list(
        reviews_collection.find({"author_id": str(profile_user["_id"])}).sort(
            "created_at", DESCENDING
        )
    )

    return render_template(
        "profile.html",
        profile=User(profile_user),
        reviews=user_reviews,
        favorites=profile_user.get("favorites", []),
        want_to_go=profile_user.get("want_to_go", []),
        profile_user=profile_user,
        is_own_profile=False,
        is_following=is_following,
        dining_halls=DINING_HALLS,
        **profile_data,
    )


@app.post("/users/<user_id>/follow")
@login_required
def follow_user(user_id):
    profile_user = get_user_or_404(user_id)
    profile_user_id = str(profile_user["_id"])

    if profile_user_id == current_user.id:
        flash("You cannot follow yourself.", "error")
        return redirect(url_for("profile"))

    try:
        follows_collection.insert_one(
            {
                "follower_id": current_user.id,
                "following_id": profile_user_id,
                "created_at": datetime.now(timezone.utc),
            }
        )
        flash(f"You are now following {profile_user['username']}.", "success")
    except DuplicateKeyError:
        flash(f"You already follow {profile_user['username']}.", "error")

    return redirect(url_for("public_profile", user_id=profile_user_id))


@app.post("/users/<user_id>/unfollow")
@login_required
def unfollow_user(user_id):
    profile_user = get_user_or_404(user_id)
    profile_user_id = str(profile_user["_id"])

    if profile_user_id == current_user.id:
        flash("You cannot unfollow yourself.", "error")
        return redirect(url_for("profile"))

    result = follows_collection.delete_one(
        {
            "follower_id": current_user.id,
            "following_id": profile_user_id,
        }
    )

    if result.deleted_count:
        flash(f"You unfollowed {profile_user['username']}.", "success")
    else:
        flash(f"You were not following {profile_user['username']}.", "error")

    return redirect(url_for("public_profile", user_id=profile_user_id))


@app.get("/users/<user_id>/followers")
@login_required
def followers_list(user_id):
    profile_user = get_user_or_404(user_id)

    follow_documents = list(
        follows_collection.find(
            {"following_id": str(profile_user["_id"])}
        ).sort("created_at", DESCENDING)
    )

    followers = get_users_from_follows(follow_documents, "follower_id")

    return render_template(
        "followers.html",
        profile_user=profile_user,
        followers=followers,
    )


@app.get("/users/<user_id>/following")
@login_required
def following_list(user_id):
    profile_user = get_user_or_404(user_id)

    follow_documents = list(
        follows_collection.find(
            {"follower_id": str(profile_user["_id"])}
        ).sort("created_at", DESCENDING)
    )

    following = get_users_from_follows(follow_documents, "following_id")

    return render_template(
        "following.html",
        profile_user=profile_user,
        following=following,
    )


@app.post("/profile/lists/<list_type>/add")
@login_required
def add_dining_hall(list_type):
    field = SAVED_LIST_FIELDS.get(list_type)

    if field is None:
        abort(404)

    dining_hall = request.form.get(
        "dining_hall", ""
    ).strip()

    if dining_hall not in DINING_HALLS:
        flash("Please select a valid dining hall.", "error")
        return redirect(url_for("profile"))

    users_collection.update_one(
        {"_id": ObjectId(current_user.id)},
        {
            "$addToSet": {
                field: dining_hall
            }
        },
    )

    flash("Dining hall saved successfully.", "success")
    return redirect(url_for("profile"))


@app.post("/profile/lists/<list_type>/remove")
@login_required
def remove_dining_hall(list_type):
    field = SAVED_LIST_FIELDS.get(list_type)

    if field is None:
        abort(404)

    dining_hall = request.form.get(
        "dining_hall", ""
    ).strip()

    if dining_hall not in DINING_HALLS:
        flash("Please select a valid dining hall.", "error")
        return redirect(url_for("profile"))

    users_collection.update_one(
        {"_id": ObjectId(current_user.id)},
        {
            "$pull": {
                field: dining_hall
            }
        },
    )

    flash("Dining hall removed successfully.", "success")
    return redirect(url_for("profile"))


@app.route("/reviews/new", methods=["GET", "POST"])
@login_required
def new_review():
    if request.method == "POST":
        review_fields, error = get_review_fields_from_form()

        if error:
            flash(error, "error")
            return render_template(
                "review_form.html",
                page_title="Add a review",
                submit_label="Submit review",
                review=request.form,
                dining_halls=DINING_HALLS,
            ), 400

        reviews_collection.insert_one(
            {
                **review_fields,
                "author_id": current_user.id,
                "author_username": current_user.username,
                "created_at": datetime.now(timezone.utc),
            }
        )

        flash("Review added.", "success")
        return redirect(url_for("index"))

    return render_template(
        "review_form.html",
        page_title="Add a review",
        submit_label="Submit review",
        review={},
        dining_halls=DINING_HALLS,
    )


@app.route("/reviews/<review_id>/edit", methods=["GET", "POST"])
@login_required
def edit_review(review_id):
    review = get_review_or_404(review_id)
    require_review_owner(review)

    if request.method == "POST":
        review_fields, error = get_review_fields_from_form()

        if error:
            flash(error, "error")
            return render_template(
                "review_form.html",
                page_title="Edit review",
                submit_label="Save changes",
                review=request.form,
                dining_halls=DINING_HALLS,
            ), 400

        reviews_collection.update_one(
            {"_id": review["_id"]},
            {
                "$set": {
                    **review_fields,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

        flash("Review updated.", "success")
        return redirect(url_for("index"))

    return render_template(
        "review_form.html",
        page_title="Edit review",
        submit_label="Save changes",
        review=review,
        dining_halls=DINING_HALLS,
    )


@app.post("/reviews/<review_id>/delete")
@login_required
def delete_review(review_id):
    review = get_review_or_404(review_id)
    require_review_owner(review)

    reviews_collection.delete_one({"_id": review["_id"]})
    flash("Review deleted.", "success")
    return redirect(url_for("index"))


@app.get("/dining-halls")
@login_required
def dining_halls_list():
    search = request.args.get("q", "").strip()

    if search:
        query = {"name": {"$regex": re.escape(search), "$options": "i"}}
    else:
        query = {}

    halls = list(dining_halls_collection.find(query).sort("name", ASCENDING))
    stats = get_stat()

    for hall in halls:
        hall["stat"] = stats.get(hall["name"], {"avg": None, "cnt": 0})

    return render_template("dining_halls.html", halls=halls, search=search)


@app.get("/dining-halls/<slug>")
@login_required
def dining_hall_detail(slug):
    hall = findhall(slug)
    stat = get_stat_hall(hall["name"])

    recent_reviews = list(
        reviews_collection.find({"dining_hall_name": hall["name"]})
        .sort("created_at", DESCENDING)
        .limit(5)
    )

    return render_template(
        "dining_hall_detail.html",
        hall=hall,
        stat=stat,
        recent_reviews=recent_reviews,
    )

if __name__ == "__main__":
    app.run(debug=True)