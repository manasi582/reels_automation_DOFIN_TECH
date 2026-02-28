"""Service for building faceless reels using FFmpeg.

Produces a 9:16 (1080×1920) vertical video composed of:
  1. Intro — logo/brand card with fade-in/out
  2. Image slideshow — Ken Burns zoom with crossfade transitions
  3. Outro — closing brand card with fade-in/out
  4. Voiceover audio overlay
  5. Optional caption burn-in
"""

import os
import re
import subprocess
import tempfile
from typing import List, Optional, Tuple

from src.config.settings import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
WIDTH = 1080
HEIGHT = 1920
FPS = 30
PIX_FMT = "yuv420p"

# Curated list of premium xfade transitions (cycled between images)
TRANSITION_STYLES = [
    "fadeblack",    # cinematic fade through black
    "slideleft",   # horizontal swipe
    "diagtl",       # diagonal wipe top-left
    "circlecrop",   # circle reveal
    "radial",       # radial wipe
    "smoothleft",   # smooth slide with easing
]


class FacelessVideoService:
    """Build faceless reels from images + audio via FFmpeg."""

    _filter_cache = {}

    def __init__(self):
        self.font_path = settings.FONT_PATH
        self.output_dir = settings.FINAL_OUTPUT_DIR
        self.intro_duration = settings.INTRO_DURATION
        self.outro_duration = settings.OUTRO_DURATION
        self.image_duration = settings.IMAGE_DURATION
        self.transition_dur = settings.TRANSITION_DURATION

    # ── Public API ────────────────────────────────────────────────────────

    def build_reel(
        self,
        images: List[str],
        audio_path: str,
        output_path: Optional[str] = None,
        intro_logo: Optional[str] = None,
        outro_image: Optional[str] = None,
        captions: Optional[List[Tuple[str, float, float]]] = None,
    ) -> str:
        """Assemble a complete faceless reel.

        Args:
            images: Paths to content images (news screenshots, etc.)
            audio_path: Path to voiceover MP3/WAV
            output_path: Where to save the final MP4 (auto-generated if None)
            intro_logo: Path to logo PNG/JPG for intro (falls back to settings)
            outro_image: Path to outro PNG/JPG (falls back to settings)
            captions: List of (text, start_sec, end_sec) tuples for burn-in

        Returns:
            Absolute path to the final MP4
        """
        settings.ensure_dirs()

        if output_path is None:
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(self.output_dir, f"faceless_{ts}.mp4")

        intro_logo = intro_logo or settings.INTRO_LOGO_PATH
        outro_image = outro_image or settings.OUTRO_IMAGE_PATH

        # Get audio duration to auto-size the slideshow
        audio_duration = self._get_audio_duration(audio_path)
        slideshow_duration = max(
            1.0,
            audio_duration - self.intro_duration - self.outro_duration
        )

        logger.info(
            f"Building faceless reel: {len(images)} images, "
            f"audio={audio_duration:.1f}s, slideshow={slideshow_duration:.1f}s"
        )

        # Build individual segments as temp files
        tmp_dir = tempfile.mkdtemp(prefix="faceless_")
        try:
            intro_clip = self._build_intro(intro_logo, tmp_dir)
            slideshow_clip = self._build_slideshow(images, slideshow_duration, tmp_dir)
            outro_clip = self._build_outro(outro_image, tmp_dir)

            final = self._concat_and_mix(
                intro_clip, slideshow_clip, outro_clip,
                audio_path, captions, output_path
            )

            logger.info(f"✓ Faceless reel saved: {final}")
            return final

        except Exception as e:
            logger.error(f"Reel build failed: {e}", exc_info=True)
            raise

    # ── Intro ─────────────────────────────────────────────────────────────

    def _build_intro(self, logo_path: str, tmp_dir: str) -> str:
        """Create intro clip: logo on black background with fade-in/out."""
        output = os.path.join(tmp_dir, "intro.mp4")
        total_frames = int(self.intro_duration * FPS)
        fade_frames = int(self.transition_dur * FPS)

        if os.path.isfile(logo_path):
            # Logo exists — scale it and center on black background
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c=black:s={WIDTH}x{HEIGHT}:d={self.intro_duration}:r={FPS}",
                "-i", logo_path,
                "-filter_complex",
                (
                    f"[1:v]scale={WIDTH-200}:-1,format={PIX_FMT}[logo];"
                    f"[0:v][logo]overlay=(W-w)/2:(H-h)/2:format=auto,"
                    f"fade=t=in:st=0:d={self.transition_dur},"
                    f"fade=t=out:st={self.intro_duration - self.transition_dur}:d={self.transition_dur}"
                    f"[out]"
                ),
                "-map", "[out]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-pix_fmt", PIX_FMT,
                "-t", str(self.intro_duration),
                output,
            ]
        else:
            # No logo — create a branded text card
            logger.warning(f"Logo not found at {logo_path}, generating text placeholder")
            
            if self._has_filter("drawtext"):
                vf = (
                    f"drawtext=text='NEWS REEL':fontfile='{self.font_path}':"
                    f"fontsize=80:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2,"
                    f"fade=t=in:st=0:d={self.transition_dur},"
                    f"fade=t=out:st={self.intro_duration - self.transition_dur}:d={self.transition_dur}"
                )
            else:
                logger.warning("FFmpeg 'drawtext' filter missing. Skipping text on intro.")
                vf = (
                    f"fade=t=in:st=0:d={self.transition_dur},"
                    f"fade=t=out:st={self.intro_duration - self.transition_dur}:d={self.transition_dur}"
                )

            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c=#1a1a2e:s={WIDTH}x{HEIGHT}:d={self.intro_duration}:r={FPS}",
                "-vf", vf,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-pix_fmt", PIX_FMT,
                "-t", str(self.intro_duration),
                output,
            ]

        self._run_ffmpeg(cmd, "intro")
        return output

    # ── Image Slideshow with Ken Burns + Varied Transitions ────────────

    def _build_slideshow(self, images: List[str], total_duration: float, tmp_dir: str) -> str:
        """Build a slideshow from images with Ken Burns zoom and varied xfade transitions."""
        output = os.path.join(tmp_dir, "slideshow.mp4")

        valid = [img for img in images if os.path.isfile(img)]
        if not valid:
            logger.warning("No valid images — generating black placeholder")
            return self._black_clip(total_duration, output)

        n = len(valid)
        per_image = total_duration / n

        # Step 1: create image clips with Ken Burns zoom motion
        segment_paths = []
        for i, img in enumerate(valid):
            seg = os.path.join(tmp_dir, f"seg_{i}.mp4")
            zoompan_frames = int(per_image * FPS)

            # Alternate between zoom-in and zoom-out for variety
            if i % 2 == 0:
                # Slow zoom IN (1.0 → 1.15), centered
                zp = (
                    f"zoompan=z='min(zoom+0.0008,1.15)':"
                    f"d={zoompan_frames}:"
                    f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                    f"s={WIDTH}x{HEIGHT}:fps={FPS}"
                )
            else:
                # Slow zoom OUT (1.15 → 1.0), centered
                zp = (
                    f"zoompan=z='if(eq(on,1),1.15,max(zoom-0.0008,1.0))':"
                    f"d={zoompan_frames}:"
                    f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                    f"s={WIDTH}x{HEIGHT}:fps={FPS}"
                )

            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", img,
                "-vf",
                (
                    f"scale=1280:2275:force_original_aspect_ratio=increase,"
                    f"crop={WIDTH+200}:{HEIGHT+200},"
                    f"{zp},"
                    f"format={PIX_FMT}"
                ),
                "-t", str(per_image),
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-pix_fmt", PIX_FMT,
                seg,
            ]
            self._run_ffmpeg(cmd, f"segment_{i}")
            segment_paths.append(seg)

        # Step 2: Concatenate segments with varied xfade transitions
        if len(segment_paths) == 1:
            os.rename(segment_paths[0], output)
            return output

        current = segment_paths[0]
        for i in range(1, len(segment_paths)):
            merged = os.path.join(tmp_dir, f"merged_{i}.mp4")
            offset = per_image - self.transition_dur

            # Cycle through the curated transition styles
            transition = TRANSITION_STYLES[(i - 1) % len(TRANSITION_STYLES)]

            cmd = [
                "ffmpeg", "-y",
                "-i", current,
                "-i", segment_paths[i],
                "-filter_complex",
                f"[0:v][1:v]xfade=transition={transition}:duration={self.transition_dur}:offset={offset},format={PIX_FMT}[out]",
                "-map", "[out]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-pix_fmt", PIX_FMT,
                merged,
            ]
            self._run_ffmpeg(cmd, f"xfade_{i} ({transition})")
            current = merged

        os.rename(current, output)
        return output

    # ── Outro ─────────────────────────────────────────────────────────────

    def _build_outro(self, outro_path: str, tmp_dir: str) -> str:
        """Create outro clip from a video file, image, or text placeholder."""
        output = os.path.join(tmp_dir, "outro.mp4")

        if os.path.isfile(outro_path):
            ext = os.path.splitext(outro_path)[1].lower()

            if ext in ('.mp4', '.mov', '.webm', '.mkv'):
                # ── VIDEO OUTRO: scale/crop/trim to fit ──────────────
                logger.info(f"Using video outro: {outro_path}")
                cmd = [
                    "ffmpeg", "-y",
                    "-i", outro_path,
                    "-vf",
                    (
                        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
                        f"crop={WIDTH}:{HEIGHT},"
                        f"fade=t=in:st=0:d={self.transition_dur},"
                        f"format={PIX_FMT}"
                    ),
                    "-t", str(self.outro_duration),
                    "-an",  # drop original audio from outro video
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-pix_fmt", PIX_FMT,
                    "-r", str(FPS),
                    output,
                ]
            else:
                # ── IMAGE OUTRO: overlay on black background ─────────
                cmd = [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", f"color=c=black:s={WIDTH}x{HEIGHT}:d={self.outro_duration}:r={FPS}",
                    "-i", outro_path,
                    "-filter_complex",
                    (
                        f"[1:v]scale={WIDTH-200}:-1,format={PIX_FMT}[img];"
                        f"[0:v][img]overlay=(W-w)/2:(H-h)/2:format=auto,"
                        f"fade=t=in:st=0:d={self.transition_dur},"
                        f"fade=t=out:st={self.outro_duration - self.transition_dur}:d={self.transition_dur}"
                        f"[out]"
                    ),
                    "-map", "[out]",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                    "-pix_fmt", PIX_FMT,
                    "-t", str(self.outro_duration),
                    output,
                ]
        else:
            logger.warning(f"Outro not found at {outro_path}, generating text placeholder")

            if self._has_filter("drawtext"):
                vf = (
                    f"drawtext=text='Follow for more':fontfile='{self.font_path}':"
                    f"fontsize=60:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2,"
                    f"fade=t=in:st=0:d={self.transition_dur},"
                    f"fade=t=out:st={self.outro_duration - self.transition_dur}:d={self.transition_dur}"
                )
            else:
                logger.warning("FFmpeg 'drawtext' filter missing. Skipping text on outro.")
                vf = (
                    f"fade=t=in:st=0:d={self.transition_dur},"
                    f"fade=t=out:st={self.outro_duration - self.transition_dur}:d={self.transition_dur}"
                )

            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c=#1a1a2e:s={WIDTH}x{HEIGHT}:d={self.outro_duration}:r={FPS}",
                "-vf", vf,
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-pix_fmt", PIX_FMT,
                "-t", str(self.outro_duration),
                output,
            ]

        self._run_ffmpeg(cmd, "outro")
        return output

    # ── Concatenation + Audio + Captions ──────────────────────────────────

    def _concat_and_mix(
        self,
        intro: str,
        slideshow: str,
        outro: str,
        audio_path: str,
        captions: Optional[List[Tuple[str, float, float]]],
        output_path: str,
    ) -> str:
        """Concatenate intro+slideshow+outro, overlay audio, and burn-in captions."""
        tmp_dir = os.path.dirname(intro)

        # 1. Create concat list file
        concat_file = os.path.join(tmp_dir, "concat.txt")
        with open(concat_file, "w") as f:
            for seg in [intro, slideshow, outro]:
                f.write(f"file '{seg}'\n")

        # 2. Concat video segments
        concat_out = os.path.join(tmp_dir, "concat.mp4")
        cmd_concat = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_file,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", PIX_FMT,
            concat_out,
        ]
        self._run_ffmpeg(cmd_concat, "concat")

        # 3. Overlay audio + captions in one pass
        caption_filters = self._build_caption_filters(captions)
        
        if not self._has_filter("drawtext") and caption_filters:
            logger.warning("FFmpeg 'drawtext' filter missing. Skipping captions.")
            caption_filters = []

        if caption_filters:
            vf = ",".join(caption_filters)
            cmd_final = [
                "ffmpeg", "-y",
                "-i", concat_out,
                "-i", audio_path,
                "-vf", vf,
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-c:a", "aac", "-b:a", "256k",
                "-pix_fmt", PIX_FMT,
                "-shortest",
                output_path,
            ]
        else:
            cmd_final = [
                "ffmpeg", "-y",
                "-i", concat_out,
                "-i", audio_path,
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-c:a", "aac", "-b:a", "256k",
                "-pix_fmt", PIX_FMT,
                "-shortest",
                output_path,
            ]

        self._run_ffmpeg(cmd_final, "final_mix")
        return output_path

    # ── Caption Filters ───────────────────────────────────────────────────

    def _build_caption_filters(
        self, captions: Optional[List[Tuple[str, float, float]]]
    ) -> List[str]:
        """Build FFmpeg drawtext filters for each caption tuple."""
        if not captions:
            return []

        filters = []
        for text, start, end in captions:
            if end <= start:
                continue
            clean = text.replace("'", "'\\''").replace(":", "\\:")
            f = (
                f"drawtext=text='{clean}':fontfile='{self.font_path}':"
                f"fontsize=46:fontcolor=white:box=1:boxcolor=black@0.5:"
                f"boxborderw=20:x=(w-text_w)/2:y=h*0.82-th/2:"
                f"enable='between(t,{start:.2f},{end:.2f})'"
            )
            filters.append(f)
        return filters

    # ── Helpers ────────────────────────────────────────────────────────────

    def _black_clip(self, duration: float, output: str) -> str:
        """Generate a plain black clip as a fallback."""
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=black:s={WIDTH}x{HEIGHT}:d={duration}:r={FPS}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", PIX_FMT,
            "-t", str(duration),
            output,
        ]
        self._run_ffmpeg(cmd, "black_clip")
        return output

    def _get_audio_duration(self, audio_path: str) -> float:
        """Get duration of an audio file using ffprobe."""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ],
                capture_output=True, text=True, check=True,
            )
            return float(result.stdout.strip())
        except Exception as e:
            logger.warning(f"ffprobe failed, estimating duration: {e}")
            # Rough fallback: 16 KB/s for 128kbps MP3
            size = os.path.getsize(audio_path)
            return size / (16 * 1024)

    @staticmethod
    def _run_ffmpeg(cmd: list, stage: str):
        """Run an FFmpeg command and handle errors."""
        logger.debug(f"FFmpeg [{stage}]: {' '.join(cmd)}")
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode() if e.stderr else "Unknown"
            logger.error(f"FFmpeg [{stage}] failed:\n{stderr}")
            raise RuntimeError(f"FFmpeg [{stage}] failed: {stderr}") from e

    def _has_filter(self, name: str) -> bool:
        """Check if a specific FFmpeg filter is available."""
        if name in self._filter_cache:
            return self._filter_cache[name]
        
        try:
            result = subprocess.run(
                ["ffmpeg", "-filters"],
                capture_output=True, text=True, check=True
            )
            exists = name in result.stdout
            self._filter_cache[name] = exists
            return exists
        except Exception:
            return False
