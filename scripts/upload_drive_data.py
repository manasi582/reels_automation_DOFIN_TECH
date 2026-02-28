import os
import sys
import logging
from typing import List, Dict, Any

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.mongodb_service import MongoDBService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def upload_drive_data():
    mongo_service = MongoDBService()
    if not mongo_service.client:
        logger.error("Could not connect to MongoDB. Aborting upload.")
        return

    base_dir = "drive_downloads"
    if not os.path.exists(base_dir):
        logger.error(f"Directory '{base_dir}' not found.")
        return

    content_count = 0
    media_count = 0

    for root, dirs, files in os.walk(base_dir):
        # Skip internal directories if any (like .DS_Store)
        for filename in files:
            if filename.startswith('.'):
                continue
                
            file_path = os.path.join(root, filename)
            relative_path = os.path.relpath(file_path, base_dir)
            
            ext = os.path.splitext(filename)[1].lower()
            
            if ext == '.txt':
                # Content collection
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        text_content = f.read()
                    
                    doc = {
                        "filename": filename,
                        "relative_path": relative_path,
                        "content": text_content,
                        "article_id": os.path.basename(root) if root != base_dir else "root"
                    }
                    
                    mongo_service.update_one("content", {"relative_path": relative_path}, doc, upsert=True)
                    content_count += 1
                    logger.info(f"Uploaded content: {relative_path}")
                except Exception as e:
                    logger.error(f"Error reading/uploading {file_path}: {e}")
            
            elif ext in ['.jpg', '.jpeg', '.png', '.mp4', '.mov', '.avi']:
                # Media collection (metadata only)
                doc = {
                    "filename": filename,
                    "relative_path": relative_path,
                    "media_type": "image" if ext in ['.jpg', '.jpeg', '.png'] else "video",
                    "local_path": os.path.abspath(file_path),
                    "article_id": os.path.basename(root) if root != base_dir else "root"
                }
                
                mongo_service.update_one("media", {"relative_path": relative_path}, doc, upsert=True)
                media_count += 1
                logger.info(f"Uploaded media metadata: {relative_path}")

    print(f"\n[+] Upload Complete!")
    print(f"[+] Content documents: {content_count}")
    print(f"[+] Media metadata documents: {media_count}")
    
    mongo_service.close()

if __name__ == "__main__":
    upload_drive_data()
