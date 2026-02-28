import os
import sys
import logging
from typing import Dict, Any, List

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.mongodb_service import MongoDBService
from src.services.langchain_llm import get_chat_model
from src.services.elevenlabs_service import ElevenLabsService
from reel_generator.video_builder import VideoBuilder
from reel_generator.caption_generator import render_captions_to_images
from reel_generator.utils import ensure_dir, get_audio_duration
from langchain_core.messages import HumanMessage, SystemMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CloudReelMaker")

# Set to False to disable the stylistic news frame and shift captions down
USE_OVERLAY = False

def _generate_title(article_text: str) -> str:
    """Helper to generate a title using LLM."""
    llm = get_chat_model(temperature=0.8, max_tokens=100)
    msg = HumanMessage(
        content=f"Read this article and write a SHORT, punchy ALL CAPS headline title (max 8 words) for a video reel:\n\n{article_text[:2000]}"
    )
    try:
        response = llm.invoke([msg])
        return response.content.strip().strip('"').upper()
    except Exception as e:
        logger.warning(f"Title generation failed: {e}")
        return "BREAKING NEWS"

def _generate_script(article_text: str, num_images: int) -> str:
    """Helper to generate a script using LLM."""
    llm = get_chat_model(temperature=0.8, max_tokens=500)
    # Roughly 20-25 seconds = 50-60 words
    msg = HumanMessage(
        content=f"Write a 20-25 second news script (approx 50-60 words) for a reel showing {num_images} images based on this article. SPOKEN TEXT ONLY, no cues:\n\n{article_text[:3000]}"
    )
    try:
        response = llm.invoke([msg])
        return response.content.strip().strip('"')
    except Exception as e:
        logger.error(f"Script generation failed: {e}")
        return "New update on the story today. Stay tuned for more details."

def create_reel_from_cloud(article_id: str):
    db = MongoDBService()
    if not db.client:
        logger.error("Could not connect to MongoDB Atlas.")
        return

    logger.info(f"🔍 Fetching data for {article_id} from MongoDB Atlas...")
    
    # 1. Fetch content
    content_doc = db.find_one("content", {"article_id": article_id})
    if not content_doc:
        logger.error(f"No content found for {article_id}")
        return
    
    article_text = content_doc.get("content", "")
    
    # 2. Fetch media metadata
    media_docs = db.find_many("media", {"article_id": article_id})
    if not media_docs:
        logger.error(f"No media found for {article_id}")
        return
    
    images = [m["local_path"] for m in media_docs if m["media_type"] == "image"]
    logger.info(f"✅ Found {len(images)} images for the reel.")

    # 3. Generate script and title (Cloud AI power)
    logger.info("🤖 Generating script and title...")
    script = _generate_script(article_text, len(images))
    title = _generate_title(article_text)
    
    logger.info(f"📜 Script: {script[:50]}...")
    logger.info(f"🏷️ Title: {title}")

    # 4. Generate Voiceover (ElevenLabs)
    logger.info("🎙️ Generating voiceover...")
    tts = ElevenLabsService()
    audio_path = f"outputs/audio/{article_id}_cloud_vo.mp3"
    ensure_dir(os.path.dirname(audio_path))
    
    try:
        tts.generate_audio(
            text=script,
            output_filename=os.path.basename(audio_path),
            output_path_override=audio_path
        )
    except Exception as e:
        if "quota_exceeded" in str(e).lower() or "401" in str(e):
            logger.warning(f"⚠️ ElevenLabs quota exceeded. Falling back to mock silent audio.")
            from reel_generator.utils import generate_mock_audio
            generate_mock_audio(script, audio_path)
        else:
            logger.error(f"TTS failed: {e}")
            return

    voice_duration = get_audio_duration(audio_path)
    logger.info(f"🔊 Voiceover duration: {voice_duration}s")

    # 5. Assemble Video
    logger.info("🎬 Assembling final reel...")
    output_path = f"outputs/final_reels/{article_id}_cloud_reel.mp4"
    ensure_dir(os.path.dirname(output_path))
    temp_dir = "reel_generator/temp"
    ensure_dir(temp_dir)
    
    caption_data = render_captions_to_images(script, temp_dir, typewriter=True, use_overlay=USE_OVERLAY)
    caption_images = [c["image_path"] for c in caption_data]
    
    config = {
        "intro_image": "assets/mumbai-news-logo.png", 
        "outro_image": "assets/mbn_reels_outro1.mp4", 
        "middle_images": images,
        "voiceover_audio": audio_path,
        "caption_images": caption_images,
        "title": title,
        "script": script,
        "use_overlay": USE_OVERLAY
    }
    
    builder = VideoBuilder()
    try:
        builder.build_video(config, voice_duration, output_path, temp_dir)
        print(f"\n✨ SUCCESS! Reel created at: {output_path}")
    except Exception as e:
        logger.error(f"Assembly failed: {e}")

if __name__ == "__main__":
    create_reel_from_cloud("article_005")
