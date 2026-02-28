import datetime
import logging
import re

logger = logging.getLogger(__name__)

def format_timestamp(seconds):
    td = datetime.timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int(td.microseconds / 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

def split_into_chunks(text):
    # Split by common sentence endings and logical pauses
    chunks = re.split(r'([.!?])\s*', text)
    processed_chunks = []
    for i in range(0, len(chunks)-1, 2):
        chunk = chunks[i] + chunks[i+1]
        if chunk.strip():
            processed_chunks.append(chunk.strip())
    
    # If there's a trailing piece without punctuation
    if len(chunks) % 2 != 0 and chunks[-1].strip():
        processed_chunks.append(chunks[-1].strip())
        
    return processed_chunks

from PIL import Image, ImageDraw, ImageFont
import os

def render_captions_to_images(script, temp_dir, typewriter=True, use_overlay=True):
    """Render caption PNGs.
    
    Args:
        script: The voiceover script text
        temp_dir: Directory to save PNGs
        typewriter: If True, renders word-by-word progressive PNGs.
        use_overlay: If True, shifts text up to fit the news frame.
    """
    chunks = split_into_chunks(script)
    caption_data = []
    
    # Try to find a font
    font_paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ]
    font = None
    for path in font_paths:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, 40)
                break
            except:
                continue
    
    if font is None:
        font = ImageFont.load_default()

    import textwrap
    MAX_CHARS_FROM_WIDTH = 35 

    frame_counter = 0
    for chunk_idx, chunk in enumerate(chunks):
        words = chunk.split()
        num_words = len(words)
        
        # In static mode, only render the full sentence
        word_steps = range(num_words) if typewriter else [num_words - 1]
        
        for word_step in word_steps:
            # Show words 0..word_step
            visible_text = " ".join(words[:word_step + 1])
            
            # Create a transparent image for the caption
            img = Image.new('RGBA', (1080, 1920), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            # Wrap text
            lines = textwrap.wrap(visible_text, width=MAX_CHARS_FROM_WIDTH)
            
            # Calculate total text height
            line_heights = []
            line_widths = []
            total_text_height = 0
            spacing = 10
            
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
                line_widths.append(w)
                line_heights.append(h)
                total_text_height += h
                
            total_text_height += (len(lines) - 1) * spacing
            
            # Position: Shift up if overlay is used, otherwise use default
            ratio = 0.75 if use_overlay else 0.8
            start_y = int(1920 * ratio) 
            
            current_y = start_y
            
            for j, line in enumerate(lines):
                w = line_widths[j]
                h = line_heights[j]
                x = (1080 - w) // 2
                
                # Draw shadow
                draw.text((x+2, current_y+2), line, font=font, fill="black")
                # Draw text
                draw.text((x, current_y), line, font=font, fill="white")
                
                current_y += h + spacing
            
            png_path = os.path.join(temp_dir, f"caption_{frame_counter}.png")
            img.save(png_path)
            caption_data.append({
                "text": visible_text,
                "image_path": png_path,
                "chunk_idx": chunk_idx,
                "word_idx": word_step,
                "total_words": num_words,
            })
            frame_counter += 1
        
    return caption_data

def generate_srt(script, voice_duration, output_path, start_offset=3.0):
    # We'll keep SRT generation for reference, but we primarily need the timing data
    chunks = split_into_chunks(script)
    # ... rest of existing logic ...
