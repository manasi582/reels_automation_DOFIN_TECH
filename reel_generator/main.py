import os
import json
import logging
from .utils import setup_logging, get_audio_duration, ensure_dir
from .tts import ElevenLabsTTS
from .caption_generator import generate_srt
from .video_builder import VideoBuilder

logger = logging.getLogger(__name__)

class ReelGenerator:
    def __init__(self, temp_dir="temp", output_dir="output", use_mock_tts=False):
        self.temp_dir = temp_dir
        self.output_dir = output_dir
        self.use_mock_tts = use_mock_tts
        ensure_dir(self.temp_dir)
        ensure_dir(self.output_dir)
        setup_logging()

    def generate(self, config):
        """
        config: {
            "script": str,
            "intro_image": str,
            "outro_image": str,
            "middle_images": List[str],
            "voice_settings": dict
        }
        """
        logger.info("Starting Reel Generation Pipeline")
        
        # 1. Voiceover Selection
        external_audio = config.get("voiceover_audio")
        if external_audio and os.path.exists(external_audio):
            logger.info(f"Using external voiceover: {external_audio}")
            voiceover_path = external_audio
        else:
            voiceover_path = os.path.join(self.temp_dir, "voiceover.mp3")
            from .tts import ElevenLabsTTS, MockTTS
            tts = MockTTS() if self.use_mock_tts else ElevenLabsTTS()
            if not tts.generate_voiceover(config["script"], voiceover_path, config.get("voice_settings")):
                raise RuntimeError("Voiceover generation failed.")
        
        # 2. Measure Duration
        voice_duration = get_audio_duration(voiceover_path)
        logger.info(f"Voiceover duration: {voice_duration}s")
        
        if voice_duration < 3.0:
            raise ValueError("Voice duration too short (minimum 3 seconds).")
        
        # 3. Timing Logic
        num_middle = len(config["middle_images"])
        if num_middle == 0:
            raise ValueError("No middle images provided.")
            
        per_image_duration = voice_duration / num_middle
        if per_image_duration < 0.5:
             logger.warning(f"Image duration ({per_image_duration}s) is very short.")

        # 4. Caption Generation
        from .caption_generator import render_captions_to_images
        caption_data = render_captions_to_images(config["script"], self.temp_dir)
        caption_images = [c["image_path"] for c in caption_data]
        
        # 5. Video Generation
        output_file = os.path.join(self.output_dir, "final_reel.mp4")
        builder_config = {
            "intro_image": config["intro_image"],
            "outro_image": config["outro_image"],
            "middle_images": config["middle_images"],
            "voiceover_audio": voiceover_path,
            "caption_images": caption_images,
            "title": config.get("title", ""),
            "script": config.get("script", ""),
        }
        
        builder = VideoBuilder()
        if not builder.build_video(builder_config, voice_duration, output_file, self.temp_dir):
            raise RuntimeError("Video construction failed.")
        
        final_video_duration = 3 + voice_duration + 3
        
        result = {
            "voice_duration": voice_duration,
            "per_image_duration": per_image_duration,
            "final_video_duration": final_video_duration,
            "output_file": output_file
        }
        
        logger.info(f"Reel generation complete: {json.dumps(result, indent=2)}")
        return result

if __name__ == "__main__":
    # Example usage / Test stub
    import sys
    
    # Simple test config (expects images to exist or will fail at FFmpeg step)
    test_config = {
        "script": "Welcome to our automated reel generator. This system uses ElevenLabs for voice and FFmpeg for assembly. Precision is our goal.",
        "intro_image": "assets/mbn_reels_intro.mp4",
        "outro_image": "assets/outro.png",
        "middle_images": ["assets/img1.png", "assets/img2.png"],
        "voice_settings": {"voice_id": None}
    }
    
    gen = ReelGenerator()
    try:
        gen.generate(test_config)
    except Exception as e:
        logger.error(f"Pipeline Error: {e}")
