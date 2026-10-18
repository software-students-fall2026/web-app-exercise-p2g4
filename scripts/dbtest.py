import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

mongo_uri = os.getenv("MONGO_URI")
database_name = os.getenv("MONGO_DB_NAME")

client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)

try:
    client.admin.command("ping")
    print("MongoDB connected successfully!")

    study_spaces = client[database_name]["swe_p2g4"]

    result = study_spaces.insert_one(
        {
            "name": "Test Study Space",
            "building": "Test Building",
            "description": "A temporary record inserted from Python.",
            "noise_level": "quiet",
        }
    )

    print(f"Inserted document ID: {result.inserted_id}")

finally:
    client.close()