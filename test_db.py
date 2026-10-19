import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

client = MongoClient(
    os.environ["MONGO_URI"],
    serverSelectionTimeoutMS=5000
)

db = client[os.environ["MONGO_DB_NAME"]]


client.admin.command("ping")
print("Connected to MongoDB!")


result = db.connection_tests.insert_one({
    "name": "Scott",
    "message": "Testing MongoDB connection"
})

print("Inserted document ID:", result.inserted_id)