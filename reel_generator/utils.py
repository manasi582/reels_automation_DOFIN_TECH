import subprocess
import json
import logging
import os

def setup_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )

def get_audio_duration(file_path):
    """Returns the duration of an audio file in seconds using ffprobe."""
    cmd = [
        "ffprobe", 
        "-v", "error", 
        "-show_entries", "format=duration", 
        "-of", "default=noprint_wrappers=1:nokey=1", 
        file_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return float(result.stdout.strip())

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def generate_mock_audio(text: str, output_path: str) -> float:
    """Generate a silent placeholder audio file using FFmpeg."""
    # Estimate duration: ~150 words per minute
    word_count = len(text.split())
    duration = max(3.0, (word_count / 150) * 60.0)
    
    # Needs logging from outside or define local logger
    logger = logging.getLogger(__name__)
    logger.info(f"🔇 Generating mock silent audio ({duration:.2f}s): {output_path}")
    
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
        "-t", str(duration), "-q:a", "9", "-acodec", "libmp3lame", output_path
    ], check=True, capture_output=True)
    return duration
