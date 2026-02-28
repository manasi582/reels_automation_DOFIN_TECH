import os
import unittest
from unittest.mock import MagicMock, patch
import tempfile
import shutil

from src.agents.faceless_reel_agent import FacelessReelAgent
from src.services.faceless_video_service import FacelessVideoService
from src.config.settings import settings

class TestFacelessReel(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.images_dir = os.path.join(self.test_dir, "images")
        os.makedirs(self.images_dir)
        
        # Create dummy images
        self.image_paths = []
        for i in range(2):
            path = os.path.join(self.images_dir, f"test_{i}.jpg")
            # Create a 1x1 black pixel JPG using ffmpeg to ensure valid format
            import subprocess
            subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1x1", 
                "-frames:v", "1", path
            ], capture_output=True)
            self.image_paths.append(path)
            
        # Create a dummy audio file
        self.audio_path = os.path.join(self.test_dir, "test.mp3")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=5", 
            "-acodec", "libmp3lame", self.audio_path
        ], capture_output=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch('src.services.elevenlabs_service.ElevenLabsService.generate_audio')
    def test_end_to_end_generation(self, mock_gen_audio):
        # Setup mock
        mock_gen_audio.return_value = self.audio_path
        
        agent = FacelessReelAgent()
        output_path = os.path.join(self.test_dir, "output.mp4")
        
        # Test generation with script
        final_path = agent.generate_reel(
            images=self.image_paths,
            script_text="This is a test script for the faceless reel agent.",
            output_path=output_path,
            enable_captions=True
        )
        
        self.assertTrue(os.path.exists(final_path))
        self.assertGreater(os.path.getsize(final_path), 0)
        
    def test_video_service_direct(self):
        service = FacelessVideoService()
        output_path = os.path.join(self.test_dir, "direct_output.mp4")
        
        # Define some dummy captions
        captions = [
            ("Test Caption 1", 1.0, 3.0),
            ("Test Caption 2", 4.0, 6.0)
        ]
        
        final_path = service.build_reel(
            images=self.image_paths,
            audio_path=self.audio_path,
            output_path=output_path,
            captions=captions
        )
        
        self.assertTrue(os.path.exists(final_path))
        self.assertGreater(os.path.getsize(final_path), 0)

if __name__ == '__main__':
    unittest.main()
