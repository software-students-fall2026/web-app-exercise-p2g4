
import importlib
import os
import sys
from unittest.mock import patch
from pathlib import Path
import mongomock
import pytest
from bson import ObjectId
from werkzeug.security import generate_password_hash
from datetime import datetime, timezone


# Make the project root importable when running pytest.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def test_app():
    mock_client = mongomock.MongoClient()

    test_env = {
        "FLASK_SECRET_KEY": "test-only-secret",
        "MONGO_URI": "mongodb://localhost:27017",
        "MONGO_DB_NAME": "nyu_dining_test",
    }

    # Patch MongoClient before importing app.py.
    with patch.dict(os.environ, test_env):
        with patch("pymongo.MongoClient", return_value=mock_client):
            sys.modules.pop("app", None)
            application = importlib.import_module("app")

    application.app.config.update(
        TESTING=True,
        SECRET_KEY="test-only-secret",
    )

    yield application

    sys.modules.pop("app", None)
    mock_client.close()


@pytest.fixture
def client(test_app):
    return test_app.app.test_client()


@pytest.fixture
def user(test_app):
    user_id = ObjectId()

    test_app.users_collection.insert_one({
        "_id": user_id,
        "username": "scott",
        "password_hash": generate_password_hash("password123"),
    })

    return user_id


def login(client):
    return client.post(
        "/login",
        data={
            "username": "scott",
            "password": "password123",
        },
        follow_redirects=True,
    )


def test_profile_requires_login(client):
    response = client.get("/profile")

    assert response.status_code == 302
    assert "/login" in response.location


def test_profile_loads_for_logged_in_user(client, user):
    login(client)

    response = client.get("/profile")

    assert response.status_code == 200
    assert b"scott" in response.data
    assert b"My Dining Lists" in response.data


def test_add_favorite(client, user, test_app):
    login(client)

    response = client.post(
        "/profile/lists/favorites/add",
        data={"dining_hall": "Lipton Hall"},
        follow_redirects=True,
    )

    assert response.status_code == 200

    saved_user = test_app.users_collection.find_one(
        {"_id": user}
    )

    assert "Lipton Hall" in saved_user["favorites"]


def test_prevent_duplicate_favorites(client, user, test_app):
    login(client)

    for _ in range(2):
        client.post(
            "/profile/lists/favorites/add",
            data={"dining_hall": "Lipton Hall"},
        )

    saved_user = test_app.users_collection.find_one(
        {"_id": user}
    )

    assert saved_user["favorites"].count("Lipton Hall") == 1


def test_remove_favorite(client, user, test_app):
    login(client)

    test_app.users_collection.update_one(
        {"_id": user},
        {"$set": {"favorites": ["Lipton Hall"]}},
    )

    response = client.post(
        "/profile/lists/favorites/remove",
        data={"dining_hall": "Lipton Hall"},
        follow_redirects=True,
    )

    assert response.status_code == 200

    saved_user = test_app.users_collection.find_one(
        {"_id": user}
    )

    assert "Lipton Hall" not in saved_user["favorites"]


def test_invalid_dining_hall_is_rejected(client, user, test_app):
    login(client)

    client.post(
        "/profile/lists/favorites/add",
        data={"dining_hall": "Not A Real Hall"},
    )

    saved_user = test_app.users_collection.find_one(
        {"_id": user}
    )

    assert saved_user.get("favorites", []) == []


def test_invalid_list_type_returns_404(client, user):
    login(client)

    response = client.post(
        "/profile/lists/unknown/add",
        data={"dining_hall": "Lipton Hall"},
    )

    assert response.status_code == 404


def test_add_and_remove_want_to_go(client, user, test_app):
    login(client)

    response = client.post(
        "/profile/lists/want_to_go/add",
        data={"dining_hall": "Palladium"},
    )
    assert response.status_code == 302

    saved_user = test_app.users_collection.find_one(
        {"_id": user}
    )
    assert saved_user["want_to_go"] == ["Palladium"]

    response = client.post(
        "/profile/lists/want_to_go/remove",
        data={"dining_hall": "Palladium"},
    )
    assert response.status_code == 302

    saved_user = test_app.users_collection.find_one(
        {"_id": user}
    )
    assert saved_user["want_to_go"] == []


def test_saved_lists_are_independent(client, user, test_app):
    login(client)

    client.post(
        "/profile/lists/favorites/add",
        data={"dining_hall": "Downstein"},
    )
    client.post(
        "/profile/lists/want_to_go/add",
        data={"dining_hall": "Downstein"},
    )

    client.post(
        "/profile/lists/favorites/remove",
        data={"dining_hall": "Downstein"},
    )

    saved_user = test_app.users_collection.find_one(
        {"_id": user}
    )

    assert saved_user["favorites"] == []
    assert saved_user["want_to_go"] == ["Downstein"]


def test_users_have_separate_favorites(client, user, test_app):
    other_user_id = ObjectId()

    test_app.users_collection.insert_one({
        "_id": other_user_id,
        "username": "otherstudent",
        "password_hash": generate_password_hash("password456"),
        "favorites": ["Palladium"],
    })

    login(client)

    client.post(
        "/profile/lists/favorites/add",
        data={"dining_hall": "Lipton Hall"},
    )

    scott = test_app.users_collection.find_one(
        {"_id": user}
    )
    other_student = test_app.users_collection.find_one(
        {"_id": other_user_id}
    )

    assert scott["favorites"] == ["Lipton Hall"]
    assert other_student["favorites"] == ["Palladium"]


def test_profile_displays_own_reviews_only(client, user, test_app):
    other_user_id = ObjectId()

    test_app.reviews_collection.insert_many([
        {
            "author_id": str(user),
            "author_username": "scott",
            "dining_hall_name": "Lipton Hall",
            "food": "Pasta",
            "rank": 5,
            "comment": "Great pasta",
            "meal_date": "2026-10-20",
            "created_at": datetime.now(timezone.utc),
        },
        {
            "author_id": str(other_user_id),
            "author_username": "otherstudent",
            "dining_hall_name": "Palladium",
            "food": "Pizza",
            "rank": 2,
            "comment": "Not my favorite",
            "meal_date": "2026-10-19",
            "created_at": datetime.now(timezone.utc),
        },
    ])

    login(client)
    response = client.get("/profile")

    assert response.status_code == 200
    assert b"Great pasta" in response.data
    assert b"Not my favorite" not in response.data


def test_edit_review_updates_profile(client, user, test_app):
    review_id = ObjectId()

    test_app.reviews_collection.insert_one({
        "_id": review_id,
        "author_id": str(user),
        "author_username": "scott",
        "dining_hall_name": "Lipton Hall",
        "food": "Pasta",
        "rank": 3,
        "comment": "Okay food",
        "meal_date": "2026-10-20",
        "created_at": datetime.now(timezone.utc),
    })

    login(client)

    response = client.post(
        f"/reviews/{review_id}/edit",
        data={
            "dining_hall_name": "Lipton Hall",
            "food": "Pasta",
            "rank": "5",
            "comment": "Amazing food",
            "meal_date": "2026-10-20",
        },
    )

    assert response.status_code == 302

    profile_response = client.get("/profile")
    assert profile_response.status_code == 200
    assert b"Amazing food" in profile_response.data
    assert b"Okay food" not in profile_response.data

    updated = test_app.reviews_collection.find_one(
        {"_id": review_id}
    )
    assert updated["rank"] == 5


def test_delete_review_updates_profile(client, user, test_app):
    review_id = ObjectId()

    test_app.reviews_collection.insert_one({
        "_id": review_id,
        "author_id": str(user),
        "author_username": "scott",
        "dining_hall_name": "Downstein",
        "food": "Pizza",
        "rank": 4,
        "comment": "Review to delete",
        "meal_date": "2026-10-20",
        "created_at": datetime.now(timezone.utc),
    })

    login(client)

    response = client.post(
        f"/reviews/{review_id}/delete"
    )

    assert response.status_code == 302

    profile_response = client.get("/profile")
    assert profile_response.status_code == 200
    assert b"Review to delete" not in profile_response.data

    deleted = test_app.reviews_collection.find_one(
        {"_id": review_id}
    )
    assert deleted is None
