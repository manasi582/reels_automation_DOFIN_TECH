import os
from typing import Any, Dict, List, Optional
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from dotenv import load_dotenv
import logging
import certifi

load_dotenv()

logger = logging.getLogger(__name__)

class MongoDBService:
    """Service to handle MongoDB operations."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDBService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.uri = os.getenv("MONGODB_URI")
        self.db_name = os.getenv("DB_NAME", "reels_gen_ai")
        
        if not self.uri:
            logger.warning("MONGODB_URI not found in environment variables. MongoDBService will be inactive.")
            self.client = None
            self.db = None
        else:
            try:
                self.client = MongoClient(self.uri, tlsCAFile=certifi.where())
                self.db = self.client[self.db_name]
                # Test connection
                self.client.admin.command('ping')
                logger.info(f"Successfully connected to MongoDB database: {self.db_name}")
            except Exception as e:
                logger.error(f"Failed to connect to MongoDB: {e}")
                self.client = None
                self.db = None
                
        self._initialized = True

    def get_collection(self, collection_name: str) -> Optional[Collection]:
        """Get a collection by name."""
        if self.db is not None:
            return self.db[collection_name]
        return None

    def insert_one(self, collection_name: str, document: Dict[str, Any]) -> Optional[Any]:
        """Insert a single document and return its ID."""
        collection = self.get_collection(collection_name)
        if collection is not None:
            result = collection.insert_one(document)
            return result.inserted_id
        return None

    def find_one(self, collection_name: str, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single document."""
        from bson.objectid import ObjectId
        collection = self.get_collection(collection_name)
        if collection is not None:
            # Handle string ID in query
            if "_id" in query and isinstance(query["_id"], str):
                try:
                    query["_id"] = ObjectId(query["_id"])
                except:
                    pass
            return collection.find_one(query)
        return None

    def find_many(self, collection_name: str, query: Dict[str, Any], limit: int = 100) -> List[Dict[str, Any]]:
        """Find multiple documents."""
        collection = self.get_collection(collection_name)
        if collection is not None:
            return list(collection.find(query).limit(limit))
        return []

    def update_one(self, collection_name: str, query: Dict[str, Any], update: Dict[str, Any], upsert: bool = False) -> bool:
        """Update a single document."""
        collection = self.get_collection(collection_name)
        if collection is not None:
            result = collection.update_one(query, {"$set": update}, upsert=upsert)
            return result.modified_count > 0 or result.upserted_id is not None
        return False

    def close(self):
        """Close the MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed.")
