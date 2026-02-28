import os
import requests
import logging
import subprocess
from abc import ABC, abstractmethod
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class TTSEngine(ABC):
    @abstractmethod
    def generate_voiceover(self, text, output_path, voice_settings=None):
        pass

class ElevenLabsTTS(TTSEngine):
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        self.base_url = "https://api.elevenlabs.io/v1/text-to-speech"

    def generate_voiceover(self, text, output_path, voice_settings=None):
        voice_settings = voice_settings or {}
        voice_id = voice_settings.get("voice_id") or os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        
        logger.info(f"Generating voiceover with ElevenLabs (Voice ID: {voice_id})")
        
        url = f"{self.base_url}/{voice_id}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key
        }
        
        # Strip potential problematic characters
        clean_text = text.replace("’", "'").replace("“", '"').replace("”", '"')
        
        data = {
            "text": clean_text,
            "model_id": "eleven_flash_v2_5"
        }
        
        try:
            response = requests.post(url, json=data, headers=headers)
            response.raise_for_status()
            
            with open(output_path, "wb") as f:
                f.write(response.content)
            
            logger.info(f"Voiceover saved to {output_path}")
            return True
        except Exception as e:
            logger.error(f"TTS Failure: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return False

class MockTTS(TTSEngine):
    def generate_voiceover(self, text, output_path, voice_settings=None):
        logger.info(f"MOCK TTS: Generating voiceover for text: {text[:50]}...")
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", 
            "-t", "5", "-q:a", "9", "-acodec", "libmp3lame", output_path
        ]
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            return True
        except Exception as e:
            logger.error(f"Mock TTS Failure: {str(e)}")
            return False
