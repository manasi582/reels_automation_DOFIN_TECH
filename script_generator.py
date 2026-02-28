import sys
import os

# Ensure src module can be found
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse
import json
from src.services.llm_service import LLMService

def generate_script(input_source, style="A"):
    # Initialize service
    try:
        llm = LLMService()
    except Exception as e:
        print(f"Error initializing LLM Service: {e}")
        return

    # Determine input type
    article_text = ""
    if os.path.isfile(input_source):
        with open(input_source, 'r') as f:
            article_text = f.read()
    else:
        article_text = input_source

    # Construct Prompt for 20s+ Script
    # Target: ~60-80 words for >20s duration
    prompt = f"""
    You are a professional news script writer for short-form video reels.
    
    SOURCE MATERIAL:
    {article_text[:2000]}  # Limit context

    TASK:
    Write a news script based on the source material.
    
    CONSTRAINTS:
    - Length: EXACTLY 60-80 words. (This ensures a 20-25 second read time).
    - Style: {style} (A=Direct, B=Engaging, C=Provocative).
    - Format: Plain text, ready to be read aloud. No scene directions, no [bracket] cues unless necessary for emphasis.
    - Hook: Start with a strong, attention-grabbing sentence.
    
    OUTPUT:
    Just the script text. No preamble.
    """

    print(f"Generating script from input (Style: {style})...")
    
    try:
        # We use a direct call method or the existing generate method if suitable.
        # Since 'generate_script_variation' logic is tied to specific JSON structure,
        # we'll use the raw _call_llm method for flexibility here, or adapt.
        # Let's use the public method if possible, but _call_llm is internal.
        # We will use the 'evaluate_worthiness' or 'generate_script_variation' flow if we have a proper dict.
        # Actually, let's use the low-level client or just access the internal method for this CLI tool 
        # as it's a utility script in the root.
        
        response = llm._call_llm(prompt)
        
        # Clean up response (remove quotes if added by LLM)
        cleaned_script = response.strip().strip('"')
        
        print("\n--- GENERATED SCRIPT ---\n")
        print(cleaned_script)
        print("\n------------------------\n")
        
        # Save to file
        with open("script.txt", "w") as f:
            f.write(cleaned_script)
        print(f"Script saved to 'script.txt'. Duration estimate: ~{len(cleaned_script.split())/3:.1f} seconds.")

    except Exception as e:
        print(f"Generation failed: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a 20s+ news script from an article.")
    parser.add_argument("input", help="Article text, JSON string, or file path.")
    parser.add_argument("--style", default="A", choices=["A", "B", "C"], help="Script style: A=Direct, B=Engaging, C=Provocative")
    
    args = parser.parse_args()
    generate_script(args.input, args.style)
