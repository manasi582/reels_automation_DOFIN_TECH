import os
import sys
from pymongo import MongoClient
from dotenv import load_dotenv

def test_atlas():
    load_dotenv()
    uri = os.getenv("MONGODB_URI")
    print(f"Testing URI: {uri}")
    
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        # The ismaster command is cheap and does not require auth.
        client.admin.command('ismaster')
        print("Connected successfully to Atlas!")
        db_name = os.getenv("DB_NAME", "contentdb")
        print(f"Database name: {db_name}")
        db = client[db_name]
        print(f"Collections: {db.list_collection_names()}")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    test_atlas()
