import os
import sys
import logging
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.mongodb_service import MongoDBService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_connection():
    load_dotenv()
    
    uri = os.getenv("MONGODB_URI")
    if not uri:
        print("\n[!] ERROR: MONGODB_URI not found in .env file.")
        print("Please add 'MONGODB_URI=your_mongodb_connection_string' to your .env file.")
        return False

    print(f"\n[*] Attempting to connect to MongoDB...")
    mongo_service = MongoDBService()
    
    if mongo_service.client and mongo_service.db is not None:
        print("[+] SUCCESS: Connected to MongoDB!")
        
        # Test write
        print("[*] Testing write operation...")
        test_doc = {"test": "connection", "project": "reels_gen_ai", "timestamp": "now"}
        doc_id = mongo_service.insert_one("test_connection", test_doc)
        
        if doc_id:
            print(f"[+] SUCCESS: Inserted test document with ID: {doc_id}")
            
            # Test read
            print("[*] Testing read operation...")
            found_doc = mongo_service.find_one("test_connection", {"_id": doc_id})
            if found_doc:
                print(f"[+] SUCCESS: Found test document: {found_doc}")
            else:
                print("[-] FAILURE: Could not find the inserted test document.")
        else:
            print("[-] FAILURE: Could not insert test document.")
            
        mongo_service.close()
        return True
    else:
        print("[-] FAILURE: Could not connect to MongoDB. Check your URI and network.")
        return False

if __name__ == "__main__":
    test_connection()
