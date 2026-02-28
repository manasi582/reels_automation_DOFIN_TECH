import subprocess
import logging
import os
import platform
import textwrap
from PIL import Image, ImageDraw, ImageFont
from .utils import ensure_dir

logger = logging.getLogger(__name__)

# Internal FPS for zoompan computation — this is the #1 performance lever.
# 15fps halves the frame calculations vs 30fps; output is still 30fps smooth.
ZOOMPAN_FPS = 30

# xfade transition used between all images
TRANSITION_STYLES = [
    "fadeblack",    # cinematic fade through black
]


class VideoBuilder:
    def __init__(self, fps=30):
        self.fps = fps
        self._hw_encoder = self._detect_hw_encoder()

    # ------------------------------------------------------------------
    # Hardware‑encoder detection (macOS VideoToolbox)
    # ------------------------------------------------------------------
    @staticmethod
    def _detect_hw_encoder() -> str:
        """Return the best available H.264 encoder name."""
        if platform.system() == "Darwin":
            try:
                r = subprocess.run(
                    ["ffmpeg", "-hide_banner", "-encoders"],
                    capture_output=True, text=True, timeout=5,
                )
                if "h264_videotoolbox" in r.stdout:
                    logger.info("Using macOS VideoToolbox HW encoder for H.264")
                    return "h264_videotoolbox"
            except Exception:
                pass
        logger.info("Using libx264 (software) encoder")
        return "libx264"

    # ------------------------------------------------------------------
    # Title PNG renderer
    # ------------------------------------------------------------------
    def _render_title_png(self, title_text, temp_dir, use_overlay=True):
        """Render the title as a transparent PNG for FFmpeg overlay."""
        img = Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Find a bold font
        font = None
        for path in [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]:
            if os.path.exists(path):
                try:
                    font = ImageFont.truetype(path, 56)
                    break
                except:
                    continue
        if not font:
            font = ImageFont.load_default()

        # Wrap text
        lines = textwrap.wrap(title_text.upper(), width=24)
        line_sizes = []
        total_h = 0
        spacing = 8
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
            line_sizes.append((w, h))
            total_h += h
        total_h += (len(lines) - 1) * spacing

        # Draw at top-center offset
        # y=280 for overlay, y=80 for default
        y = 280 if use_overlay else 80
        for idx, line in enumerate(lines):
            w, h = line_sizes[idx]
            x = (1080 - w) // 2

            # Black outline
            for dx, dy in [(-2, -2), (-2, 2), (2, -2), (2, 2), (-2, 0), (2, 0), (0, -2), (0, 2)]:
                draw.text((x + dx, y + dy), line, font=font, fill="black")
            # Yellow text
            draw.text((x, y), line, font=font, fill="yellow")
            y += h + spacing

        png_path = os.path.join(temp_dir, "title_overlay.png")
        img.save(png_path)
        logger.info(f"Title overlay rendered: {png_path}")
        return png_path

    # ------------------------------------------------------------------
    # Red side border renderer
    # ------------------------------------------------------------------
    def _render_border_png(self, temp_dir):
        """Render a transparent PNG with black borders on all sides."""
        BORDER_WIDTH = 12
        img = Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Top border
        draw.rectangle([0, 0, 1079, BORDER_WIDTH - 1], fill=(0, 0, 0, 255))
        # Bottom border
        draw.rectangle([0, 1920 - BORDER_WIDTH, 1079, 1919], fill=(0, 0, 0, 255))
        # Left border
        draw.rectangle([0, 0, BORDER_WIDTH - 1, 1919], fill=(0, 0, 0, 255))
        # Right border
        draw.rectangle([1080 - BORDER_WIDTH, 0, 1079, 1919], fill=(0, 0, 0, 255))
        
        png_path = os.path.join(temp_dir, "border_overlay.png")
        img.save(png_path)
        logger.info(f"Border overlay rendered: {png_path}")
        return png_path

    # ------------------------------------------------------------------
    # Main build
    # ------------------------------------------------------------------
    def build_video(self, config, voice_duration, output_file, temp_dir):
        """
        config keys:
            intro_image, outro_image, middle_images, voiceover_audio,
            caption_images (list of overlay PNGs), use_overlay (bool)
        """
        ensure_dir(temp_dir)
        use_overlay = config.get("use_overlay", True)

        intro_img   = config["intro_image"]
        outro_img   = config["outro_image"]
        middle_imgs = config["middle_images"]
        voice_audio = config["voiceover_audio"]
        caption_images = config.get("caption_images", [])
        title_text  = config.get("title", "")

        num_middle = len(middle_imgs)
        
        # ---- Timing Math ----------------------------------------------------
        # The outro MUST start exactly when the voiceover ends.
        TRANSITION_DURATION = 1.0
        INTRO_DURATION = 3.0
        outro_offset = INTRO_DURATION + voice_duration  # Hard anchor
        
        # Each xfade transition "eats" TRANSITION_DURATION from the visual timeline.
        # With N middle images there are N xfade transitions in the middle loop
        # (intro→img1, img1→img2, ..., imgN-1→imgN).
        # The cumulative duration after the middle loop is:
        #   cum = INTRO_DURATION + N * (per_image_duration - TRANSITION_DURATION)
        # For the outro xfade at outro_offset, we need:
        #   cum >= outro_offset + TRANSITION_DURATION
        # Solving: per_image_duration = (voice_duration + TRANSITION_DURATION) / N + TRANSITION_DURATION
        
        if num_middle > 0:
            per_image_duration = (voice_duration + TRANSITION_DURATION) / num_middle + TRANSITION_DURATION
        else:
            per_image_duration = 5.0

        # ---- input arguments ------------------------------------------------
        inputs = [intro_img] + middle_imgs + [outro_img]
        video_exts = ('.mp4', '.mov', '.webm', '.mkv')
        intro_is_video = os.path.splitext(intro_img)[1].lower() in video_exts
        outro_is_video = os.path.splitext(outro_img)[1].lower() in video_exts
        input_args = []
        for img in inputs:
            is_video = (img == intro_img and intro_is_video) or (img == outro_img and outro_is_video)
            if is_video:
                input_args.extend(["-t", "3", "-i", img])
            elif img in (intro_img, outro_img):
                input_args.extend(["-loop", "1", "-t", "3", "-i", img])
            else:
                input_args.extend(["-i", img])

        input_args.extend(["-i", voice_audio])

        caption_start_idx = len(inputs) + 1
        for cap in caption_images:
            input_args.extend(["-i", cap])

        # ---- filter_complex -------------------------------------------------
        filter_parts = []

        for i in range(len(inputs)):
            if inputs[i] == intro_img:
                filter_parts.append(
                    f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                    f"crop=1080:1920,fps={ZOOMPAN_FPS},setsar=1[v{i}]"
                )
            elif inputs[i] == outro_img:
                filter_parts.append(
                    f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                    f"crop=1080:1920,fps={ZOOMPAN_FPS},setsar=1[v{i}]"
                )
            else:
                zoompan_frames = int(per_image_duration * ZOOMPAN_FPS)
                img_index = i - 1

                if img_index % 2 == 0:
                    zp = (
                        f"zoompan=z='min(zoom+0.0008,1.15)':"
                        f"d={zoompan_frames}:"
                        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                        f"s=1080x1920:fps={ZOOMPAN_FPS}"
                    )
                else:
                    zp = (
                        f"zoompan=z='if(eq(on,1),1.15,max(zoom-0.0008,1.0))':"
                        f"d={zoompan_frames}:"
                        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                        f"s=1080x1920:fps={ZOOMPAN_FPS}"
                    )

                filter_parts.append(
                    f"[{i}:v]scale=1280:2275:force_original_aspect_ratio=increase,"
                    f"crop=1280:2120,{zp},setsar=1[v{i}]"
                )

        # ---- Transitions: Intro + Middle images -----------------------------
        last_label = "v0"
        cumulative_duration = INTRO_DURATION
        
        for i in range(1, len(inputs) - 1):  # Middle images only
            next_label = f"v_join_{i}"
            offset = cumulative_duration - TRANSITION_DURATION
            transition = TRANSITION_STYLES[(i - 1) % len(TRANSITION_STYLES)]
            filter_parts.append(
                f"[{last_label}][v{i}]xfade=transition={transition}"
                f":duration={TRANSITION_DURATION}:offset={offset:.2f}[{next_label}]"
            )
            last_label = next_label
            cumulative_duration += (per_image_duration - TRANSITION_DURATION)

        filter_parts.append(f"[{last_label}]null[v_base_middle]")

        # ---- Caption overlays ------------------------------------------------
        num_captions = len(caption_images)
        caption_start = INTRO_DURATION
        caption_end = outro_offset

        if num_captions and caption_end > caption_start:
            caption_window = caption_end - caption_start
            
            from .caption_generator import split_into_chunks
            script_text = config.get("script", "")
            chunks = split_into_chunks(script_text)
            
            # Compute per-sentence time window (weighted by word count)
            chunk_word_counts = [max(len(c.split()), 1) for c in chunks]
            total_words = sum(chunk_word_counts)
            
            chunk_windows = []
            t = caption_start
            for cw in chunk_word_counts:
                fraction = cw / total_words
                chunk_windows.append((t, t + fraction * caption_window))
                t += fraction * caption_window
            
            is_typewriter = num_captions > len(chunks)
            
            curr_v = "v_base_middle"
            if is_typewriter:
                # Typewriter mode: multiple sub-frames per sentence
                for i in range(num_captions):
                    cap_idx = caption_start_idx + i
                    
                    # Find which chunk/word this frame belongs to
                    chunk_idx = 0
                    word_idx = 0
                    frame_counter = 0
                    found = False
                    for ci, chunk in enumerate(chunks):
                        words_in_chunk = len(chunk.split())
                        for wi in range(words_in_chunk):
                            if frame_counter == i:
                                chunk_idx = ci
                                word_idx = wi
                                found = True
                                break
                            frame_counter += 1
                        if found:
                            break
                    
                    chunk_start_t, chunk_end_t = chunk_windows[chunk_idx]
                    chunk_dur = chunk_end_t - chunk_start_t
                    chunk_words = chunks[chunk_idx].split()
                    char_weights = [max(len(w), 2) for w in chunk_words]
                    total_chars = sum(char_weights)
                    
                    t0 = chunk_start_t + sum(char_weights[:word_idx]) / total_chars * chunk_dur
                    t1 = chunk_start_t + sum(char_weights[:word_idx + 1]) / total_chars * chunk_dur
                    
                    nxt = f"v_cap{i}"
                    filter_parts.append(
                        f"[{curr_v}][{cap_idx}:v]overlay=0:0"
                        f":enable='between(t,{t0:.2f},{t1:.2f})'[{nxt}]"
                    )
                    curr_v = nxt
            else:
                # Static mode: one caption per sentence
                for i in range(num_captions):
                    cap_idx = caption_start_idx + i
                    chunk_i = min(i, len(chunk_windows) - 1)
                    t0, t1 = chunk_windows[chunk_i]
                    
                    nxt = f"v_cap{i}"
                    filter_parts.append(
                        f"[{curr_v}][{cap_idx}:v]overlay=0:0"
                        f":enable='between(t,{t0:.2f},{t1:.2f})'[{nxt}]"
                    )
                    curr_v = nxt
            filter_parts.append(f"[{curr_v}]null[v_captioned]")
        else:
            filter_parts.append("[v_base_middle]null[v_captioned]")

        # ---- Title overlay ---------------------------------------------------
        segments = config.get("segments")
        next_input_idx = len(inputs) + 1 + len(caption_images)

        title_png = None
        if title_text:
            title_png = self._render_title_png(title_text, temp_dir, use_overlay=use_overlay)

        if segments:
            # Combined reel: per-article title overlays
            # Calculate time windows per segment
            seg_start = INTRO_DURATION
            curr_v = "v_captioned"
            for seg_i, seg in enumerate(segments):
                seg_end = seg_start + seg["voice_duration"]
                # Render title for segment, passing use_overlay
                seg_title_png = self._render_title_png(seg["title"], temp_dir, use_overlay=use_overlay)
                # Rename to avoid overwriting
                import shutil
                seg_title_path = os.path.join(temp_dir, f"title_seg_{seg_i}.png")
                shutil.copy(seg_title_png, seg_title_path)
                input_args.extend(["-i", seg_title_path])
                nxt = f"v_title_{seg_i}"
                filter_parts.append(
                    f"[{curr_v}][{next_input_idx}:v]overlay=0:0"
                    f":enable='between(t,{seg_start:.2f},{seg_end:.2f})'[{nxt}]"
                )
                curr_v = nxt
                next_input_idx += 1
                seg_start = seg_end
            pre_outro_label = curr_v
        elif title_png:
            # Single reel: one title for entire content section
            input_args.extend(["-i", title_png])
            filter_parts.append(
                f"[v_captioned][{next_input_idx}:v]overlay=0:0"
                f":enable='between(t,{caption_start},{outro_offset:.2f})'[v_titled]"
            )
            pre_outro_label = "v_titled"
            next_input_idx += 1
        else:
            pre_outro_label = "v_captioned"

        # ---- News Frame Overlay (Stylistic) ---------------------------------
        # Replace the simple black border with the thematic news overlay
        overlay_path = "assets/main_overlay.png"
        if use_overlay and os.path.exists(overlay_path):
            input_args.extend(["-i", overlay_path])
            # Scale overlay to 1080x1920
            filter_parts.append(
                f"[{next_input_idx}:v]scale=1080:1920[ov_scaled]"
            )
            filter_parts.append(
                f"[{pre_outro_label}][ov_scaled]overlay=0:0[v_framed]"
            )
            pre_outro_label = "v_framed"
            next_input_idx += 1
        elif use_overlay:
            logger.warning(f"Overlay requested but not found: {overlay_path}")

        # ---- Attach Outro with xfade at exactly outro_offset -----------------
        outro_idx = len(inputs) - 1
        outro_transition = TRANSITION_STYLES[(outro_idx - 1) % len(TRANSITION_STYLES)]
        filter_parts.append(
            f"[{pre_outro_label}][v{outro_idx}]xfade=transition={outro_transition}"
            f":duration={TRANSITION_DURATION}:offset={outro_offset:.2f}[v_final]"
        )

        # ---- Audio: starts at 3s, plays full voiceover, hard trimmed ---------
        audio_idx = len(inputs)
        filter_parts.append(
            f"[{audio_idx}:a]atrim=0:{voice_duration:.2f},asetpts=PTS-STARTPTS,"
            f"adelay=3000|3000[a_delayed]"
        )

        # ---- assemble command -----------------------------------------------
        cmd = ["ffmpeg", "-y"]
        cmd.extend(input_args)
        cmd.extend([
            "-filter_complex", ";".join(filter_parts),
            "-map", "[v_final]",
            "-map", "[a_delayed]",
            "-c:v", self._hw_encoder,
            "-pix_fmt", "yuv420p",
            "-r", str(self.fps),
        ])

        # Encoder‑specific options
        if self._hw_encoder == "h264_videotoolbox":
            cmd.extend(["-b:v", "5M"])         # target bitrate for HW enc
        else:
            cmd.extend(["-preset", "medium"])  # balanced quality/speed

        cmd.append(output_file)

        logger.info(f"Running FFmpeg: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True
            )
            logger.info("FFmpeg execution successful.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg Failure: {e.stderr}")
            return False
