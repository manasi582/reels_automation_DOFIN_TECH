"""Faceless Reel Agent — Orchestrates voiceover generation + video assembly."""

import os
import re
from typing import List, Optional, Tuple

from src.services.elevenlabs_service import ElevenLabsService
from src.services.faceless_video_service import FacelessVideoService
from src.config.settings import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class FacelessReelAgent:
    """Orchestrates the creation of a faceless news reel.

    Workflow:
        1. Accept image paths + script text
        2. Generate voiceover via ElevenLabs (or use pre-generated audio)
        3. Optionally split script into timed captions
        4. Assemble the final reel via FacelessVideoService
    """

    def __init__(self):
        self.elevenlabs = ElevenLabsService()
        self.video_service = FacelessVideoService()

    def generate_reel(
        self,
        images: List[str],
        script_text: Optional[str] = None,
        audio_path: Optional[str] = None,
        output_path: Optional[str] = None,
        intro_logo: Optional[str] = None,
        outro_image: Optional[str] = None,
        voice_id: Optional[str] = None,
        enable_captions: bool = True,
    ) -> str:
        """Generate a complete faceless reel.

        Args:
            images: Paths to content images
            script_text: Script for voiceover generation (required if no audio_path)
            audio_path: Pre-generated audio file (skips TTS if provided)
            output_path: Output MP4 path (auto-generated if None)
            intro_logo: Override intro logo path
            outro_image: Override outro image path
            voice_id: Override ElevenLabs voice ID
            enable_captions: Whether to burn-in captions from the script

        Returns:
            Absolute path to the final MP4
        """
        if not images:
            raise ValueError("At least one image is required")

        if audio_path is None and script_text is None:
            raise ValueError("Either script_text or audio_path must be provided")

        # Validate images
        valid_images = [img for img in images if os.path.isfile(img)]
        if not valid_images:
            raise FileNotFoundError(f"No valid image files found in: {images}")

        logger.info(f"FacelessReelAgent: {len(valid_images)} images, "
                     f"audio={'provided' if audio_path else 'will generate'}")

        # Step 1: Generate voiceover if needed
        if audio_path is None:
            audio_path = self._generate_voiceover(script_text, voice_id)

        # Step 2: Build captions from script
        captions = None
        if enable_captions and script_text:
            audio_duration = self.video_service._get_audio_duration(audio_path)
            captions = self._build_captions(script_text, audio_duration)

        # Step 3: Assemble the reel
        final_path = self.video_service.build_reel(
            images=valid_images,
            audio_path=audio_path,
            output_path=output_path,
            intro_logo=intro_logo,
            outro_image=outro_image,
            captions=captions,
        )

        return final_path

    def _generate_voiceover(self, script_text: str, voice_id: Optional[str] = None) -> str:
        """Generate voiceover audio from script text via ElevenLabs."""
        # Clean up the script for TTS
        clean_text = self._clean_for_tts(script_text)

        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"faceless_vo_{ts}.mp3"

        logger.info(f"Generating voiceover ({len(clean_text)} chars)")

        audio_path = self.elevenlabs.generate_audio(
            text=clean_text,
            output_filename=filename,
            voice_id=voice_id,
        )

        logger.info(f"✓ Voiceover saved: {audio_path}")
        return audio_path

    def _clean_for_tts(self, text: str) -> str:
        """Remove timing markers and metadata from the script for natural TTS."""
        # Remove [0:00-0:05] style markers
        cleaned = re.sub(r'\[\d+:\d+-\d+:\d+\]', '', text)
        # Remove visual cue markers like [SHOW_IMAGE], [CUT_TO_AVATAR]
        cleaned = re.sub(r'\[[\w_]+\]', '', cleaned)
        # Collapse whitespace
        lines = [line.strip() for line in cleaned.split('\n') if line.strip()]
        return " ".join(lines)

    def _build_captions(
        self,
        script_text: str,
        audio_duration: float,
    ) -> List[Tuple[str, float, float]]:
        """Split script into timed caption segments.

        Strategy: Split by sentences, distribute evenly across the audio
        duration (offset by intro duration to align with the slideshow).
        """
        # Extract clean sentences
        clean = self._clean_for_tts(script_text)
        # Split on sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', clean)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return []

        intro_offset = settings.INTRO_DURATION
        usable_duration = audio_duration - settings.INTRO_DURATION - settings.OUTRO_DURATION
        if usable_duration <= 0:
            usable_duration = audio_duration

        per_sentence = usable_duration / len(sentences)
        captions = []
        for i, sentence in enumerate(sentences):
            start = intro_offset + i * per_sentence
            end = start + per_sentence
            # Truncate very long captions for readability
            display = sentence if len(sentence) <= 80 else sentence[:77] + "..."
            captions.append((display, start, end))

        return captions
