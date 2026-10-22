import os
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
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from werkzeug.security import check_password_hash, generate_password_hash


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

users_collection.create_index("username", unique=True)


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
        user_document = users_collection.find_one({"_id": ObjectId(user_id)})
    except InvalidId:
        return None

    if user_document is None:
        return None

    return User(user_document)


def get_review_or_404(review_id):
    
    try:
        review = reviews_collection.find_one({"_id": ObjectId(review_id)})
    except InvalidId:
        abort(404)

    if review is None:
        abort(404)

    return review


def require_review_owner(review):
    
    if review.get("author_id") != current_user.id:
        abort(403)


def get_review_fields_from_form():
    
    dining_hall_name = request.form.get("dining_hall_name", "").strip()
    food = request.form.get("food", "").strip()
    comment = request.form.get("comment", "").strip()
    meal_date = request.form.get("meal_date", "")

    try:
        rank = int(request.form.get("rank", 0))
    except ValueError:
        rank = 0

    if not dining_hall_name or not food or not meal_date:
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
                    "created_at": datetime.now(timezone.utc),
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


@app.get("/profile")
@login_required
def profile():
    # Retrieve reviews written by the logged-in user
    user_reviews = list(
        reviews_collection.find(
            {"author_id": current_user.id}
        ).sort("created_at", -1)
    )

    return render_template(
        "profile.html",
        profile=current_user,
        reviews=user_reviews,
        followers_count=0,
        following_count=0,
        favorites=[],
        want_to_go=[],
    )


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
    )


@app.post("/reviews/<review_id>/delete")
@login_required
def delete_review(review_id):
    review = get_review_or_404(review_id)
    require_review_owner(review)

    reviews_collection.delete_one({"_id": review["_id"]})
    flash("Review deleted.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)