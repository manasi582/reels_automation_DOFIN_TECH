"""Service for ElevenLabs voice synthesis API."""
import os
import requests
from typing import Dict, Any, Optional, List
from src.config.settings import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class ElevenLabsService:
    """Interface for ElevenLabs Text-to-Speech API."""
    
    def __init__(self):
        """Initialize the service with API key and base URL."""
        self.api_key = settings.ELEVENLABS_API_KEY
        self.base_url = "https://api.elevenlabs.io/v1"
        self.voice_id = settings.ELEVENLABS_VOICE_ID

    def list_voices(self) -> List[Dict[str, str]]:
        """Fetch all available voices from ElevenLabs.
        
        Returns:
            List of dicts with 'voice_id', 'name', 'category', and 'description'.
        """
        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY is required to list voices.")

        url = f"{self.base_url}/voices"
        headers = {"xi-api-key": self.api_key}

        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"ElevenLabs API error ({response.status_code}): {response.text}")

        voices_raw = response.json().get("voices", [])
        voices = []
        for v in voices_raw:
            voices.append({
                "voice_id": v.get("voice_id", ""),
                "name": v.get("name", "Unknown"),
                "category": v.get("category", ""),
                "description": ", ".join(
                    v.get("labels", {}).values()
                ) if v.get("labels") else "",
            })
        return voices

    def generate_audio(
        self,
        text: str,
        output_filename: str,
        voice_id: Optional[str] = None,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        output_path_override: Optional[str] = None,
    ) -> str:
        """Generate audio from text and save to file.
        
        Args:
            text: The script text to synthesize
            output_filename: Filename (e.g., 'reel_1.mp3')
            voice_id: Override voice ID (defaults to settings)
            stability: Voice stability 0.0-1.0 (lower = more expressive)
            similarity_boost: Voice similarity 0.0-1.0 (higher = closer to original)
            output_path_override: Full output path; skips default directory logic
            
        Returns:
            Absolute path to the saved audio file
        """
        if not self.api_key:
            logger.warning("ELEVENLABS_API_KEY not set. Audio generation will fail.")
            raise ValueError("ELEVENLABS_API_KEY is required for voice synthesis.")
            
        settings.ensure_dirs()

        if output_path_override:
            output_path = output_path_override
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        else:
            output_path = os.path.join(settings.audio_dir, output_filename)

        vid = voice_id or self.voice_id
        url = f"{self.base_url}/text-to-speech/{vid}"
        
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key
        }
        
        data = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
                "style": 0.0,
                "use_speaker_boost": True
            }
        }
        
        logger.info(f"Calling ElevenLabs API for voice synthesis: {output_filename}")
        
        try:
            response = requests.post(url, json=data, headers=headers)
            
            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"ElevenLabs API error ({response.status_code}): {error_detail}")
                raise Exception(f"ElevenLabs API request failed with status {response.status_code}: {error_detail}")
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
            
            logger.info(f"✓ Audio successfully saved to: {output_path}")
            return output_path
            
        except requests.RequestException as e:
            logger.error(f"Error making request to ElevenLabs: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in ElevenLabsService: {e}")
            raise

    def get_audio_duration(self, audio_path: str) -> float:
        """Calculate duration of the audio file in seconds.
        
        Note: Requires 'pydub' or 'mutagen' if we want precision, or we can use 
        some simple estimation or ffprobe if available. For now, we'll try to use 
        pydub if installed, otherwise return an estimation.
        """
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(audio_path)
            return len(audio) / 1000.0
        except ImportError:
            logger.warning("pydub not installed. Using file size for duration estimation.")
            # Rough estimation for 128kbps MP3: ~16KB/s
            file_size = os.path.getsize(audio_path)
            return file_size / (16 * 1024)
        except Exception as e:
            logger.error(f"Error getting audio duration: {e}")
            return 0.0
