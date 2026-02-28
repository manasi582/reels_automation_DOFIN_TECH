import os
import gdown
import logging
import glob
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class DriveService:
    """Service to handle Google Drive downloads."""

    def __init__(self, download_dir: str = "downloads"):
        self.download_dir = download_dir
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)

    def download_folder(self, url: str, target_folder: str = None) -> Dict[str, Optional[str] | List[str]]:
        """
        Download contents of a Google Drive folder.
        
        Args:
            url: Google Drive folder URL
            target_folder: Optional subfolder name to target (e.g., 'article_001')
            
        Returns:
            Dictionary with keys 'images', 'article', 'intro', 'outro' containing file paths.
        """
        logger.info(f"Downloading from Drive: {url}")
        if target_folder:
            logger.info(f"Targeting subfolder: {target_folder}")
        
        try:
            # Clear previous downloads
            import shutil
            if os.path.exists(self.download_dir):
                logger.info(f"Clearing previous downloads in {self.download_dir}")
                shutil.rmtree(self.download_dir)
            
            # Recreate empty download directory
            os.makedirs(self.download_dir)

            # gdown.download_folder returns list of files downloaded
            files = gdown.download_folder(url, output=self.download_dir, quiet=False, use_cookies=False)
            
            # If files is None (sometimes gdown does this), scan dir manually
            if not files:
                files = []
                for root, dirs, filenames in os.walk(self.download_dir):
                    for fname in filenames:
                        files.append(os.path.join(root, fname))
            
            # If a target subfolder is specified, filter to only those files
            if target_folder:
                subfolder_path = os.path.join(self.download_dir, target_folder)
                if os.path.isdir(subfolder_path):
                    files = []
                    for fname in os.listdir(subfolder_path):
                        files.append(os.path.join(subfolder_path, fname))
                    logger.info(f"Filtered to subfolder '{target_folder}': {len(files)} files")
                else:
                    logger.warning(f"Subfolder '{target_folder}' not found in downloads. Using all files.")
                
            if not files:
                logger.warning("No files downloaded or folder is empty.")
                return {"images": [], "article": None, "intro": None, "outro": None}
                
            return self._categorize_files(files)
            
        except Exception as e:
            logger.error(f"Failed to download folder: {e}")
            raise

    def sync_folder(self, url: str) -> list[str]:
        """Smart sync: download only new article folders, delete stale local ones.
        
        Returns list of all current local article folder names.
        """
        import shutil
        import tempfile

        logger.info(f"🔄 Syncing with Google Drive: {url}")

        # 1. Download to a temporary directory
        temp_dir = tempfile.mkdtemp(prefix="drive_sync_")
        try:
            gdown.download_folder(url, output=temp_dir, quiet=False, use_cookies=False)
        except Exception as e:
            logger.error(f"❌ Drive download failed: {e}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            # Fall back to whatever is already local
            if os.path.isdir(self.download_dir):
                existing = sorted([d for d in os.listdir(self.download_dir)
                                   if os.path.isdir(os.path.join(self.download_dir, d))])
                logger.warning(f"⚠️ Using {len(existing)} existing local folders")
                return existing
            raise

        # 2. Identify folders on Drive vs local
        remote_folders = set()
        for entry in os.listdir(temp_dir):
            if os.path.isdir(os.path.join(temp_dir, entry)):
                remote_folders.add(entry)

        os.makedirs(self.download_dir, exist_ok=True)
        local_folders = set()
        for entry in os.listdir(self.download_dir):
            if os.path.isdir(os.path.join(self.download_dir, entry)):
                local_folders.add(entry)

        # 3. Copy new folders (on Drive but not local)
        new_folders = remote_folders - local_folders
        for folder in sorted(new_folders):
            src = os.path.join(temp_dir, folder)
            dst = os.path.join(self.download_dir, folder)
            shutil.copytree(src, dst)
            logger.info(f"📥 NEW: {folder}")

        # 4. Delete stale folders (local but not on Drive)
        stale_folders = local_folders - remote_folders
        for folder in sorted(stale_folders):
            path = os.path.join(self.download_dir, folder)
            shutil.rmtree(path)
            logger.info(f"🗑️  REMOVED: {folder}")

        # 5. Cleanup temp
        shutil.rmtree(temp_dir, ignore_errors=True)

        # Summary
        current = sorted(remote_folders)
        logger.info(f"✅ Sync complete: {len(current)} folders "
                     f"({len(new_folders)} new, {len(stale_folders)} removed, "
                     f"{len(local_folders & remote_folders)} unchanged)")
        return current

    def _categorize_files(self, file_paths: List[str]) -> Dict[str, Optional[str] | List[str]]:
        """Filter downloaded files into assets."""
        assets = {
            "images": [],
            "article": None,
            "intro": None,
            "outro": None
        }
        
        # Expanded image extensions
        image_exts = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff'}
        
        for path in file_paths:
            if not os.path.exists(path):
                continue
                
            filename = os.path.basename(path).lower()
            ext = os.path.splitext(filename)[1]
            
            if ext == '.txt':
                assets["article"] = path
            
            elif ext in image_exts:
                if "intro" in filename:
                    assets["intro"] = path
                elif "outro" in filename:
                    assets["outro"] = path
                else:
                    assets["images"].append(path)
        
        assets["images"].sort()
        logger.info(f"Download Summary - Images: {len(assets['images'])}, Article: {assets['article']}")
        
        return assets

    def get_article_previews(self) -> Dict[str, str]:
        """
        Scan downloaded subfolders and return a dict of {folder_name: article_text_preview}.
        Must be called AFTER download_folder().
        """
        previews = {}
        
        if not os.path.isdir(self.download_dir):
            return previews
            
        for entry in sorted(os.listdir(self.download_dir)):
            subfolder = os.path.join(self.download_dir, entry)
            if not os.path.isdir(subfolder):
                continue
            
            # Find .txt file in this subfolder
            for fname in os.listdir(subfolder):
                if fname.lower().endswith('.txt'):
                    txt_path = os.path.join(subfolder, fname)
                    try:
                        with open(txt_path, 'r') as f:
                            text = f.read()
                        previews[entry] = text[:1000]  # First 1000 chars for preview
                        logger.info(f"  📄 {entry}: {fname} ({len(text)} chars)")
                    except Exception as e:
                        logger.warning(f"Could not read {txt_path}: {e}")
                    break  # Only first .txt per folder
        
        logger.info(f"Found {len(previews)} article previews across subfolders")
        return previews
