#!/usr/bin/env python3
"""
LangGraph-Powered Reel Generation Pipeline

A state-graph workflow that downloads articles from Google Drive,
uses an LLM to select the best ones, generates scripts + voiceovers,
and assembles polished faceless reels.

Usage:
    Single:  python langgraph_pipeline.py --url <drive_url> --folder article_001
    Multi:   python langgraph_pipeline.py --url <drive_url> --count 4
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from typing import Any, Optional, TypedDict

# ── path fix ──────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import END, StateGraph

from src.services.drive_service import DriveService
from src.services.elevenlabs_service import ElevenLabsService
from src.services.langchain_llm import get_chat_model
from src.services.mongodb_service import MongoDBService

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
# ── settings ──────────────────────────────────────────────────────────────────
USE_OVERLAY = False  # Set to True to enable the stylistic news frame
USE_MONGO = True     # Set to True to fetch from MongoDB Atlas by default
logger = logging.getLogger("LangGraphPipeline")


# ═══════════════════════════════════════════════════════════════════════════════
# STATE SCHEMA
# ═══════════════════════════════════════════════════════════════════════════════

class ReelResult(TypedDict):
    """Result for a single reel generation."""
    folder: str
    script: str
    audio_path: str
    reel_path: Optional[str]
    status: str  # "success" | "failed"
    error: Optional[str]


class PipelineState(TypedDict):
    """Typed state flowing through the LangGraph pipeline."""
    drive_url: str
    target_count: int                    # 0 = ask user interactively
    folder_name: Optional[str]          # single-mode override
    skip_download: bool                  # True = use existing drive_downloads/
    previews: dict                       # {folder_name: article_text_preview}
    selected_folders: list[str]          # LLM-chosen or all folders
    current_folder_idx: int              # iteration pointer
    results: list[dict]                  # list of ReelResult dicts
    error: Optional[str]                 # fatal error message
    interactive: bool                    # True when --count is not provided
    use_mongo: bool                      # True = fetch from MongoDB Atlas
    use_drive: bool                      # True = fetch from Google Drive (or local cache)
    cloud_data: dict                     # Buffers content from MongoDB


# ═══════════════════════════════════════════════════════════════════════════════
# GRAPH NODES
# ═══════════════════════════════════════════════════════════════════════════════

def download_drive(state: PipelineState) -> dict:
    """Node 1: Download from Drive OR fetch from MongoDB Atlas."""
    drive = DriveService(download_dir="drive_downloads")
    
    # --- MONGODB MODE ---
    if state.get("use_mongo"):
        logger.info(" Fetching article summaries from MongoDB Atlas...")
        db = MongoDBService()
        if not db.client:
            return {"error": "Could not connect to MongoDB Atlas."}
        
        content_docs = db.find_many("content", {})
        if not content_docs:
            return {"error": "No articles found in MongoDB 'content' collection."}
            
        previews = {}
        cloud_data = {}
        for doc in content_docs:
            folder_id = doc.get("article_id", "unknown")
            text = doc.get("content", "")
            previews[folder_id] = text[:200] # Use first 200 chars for preview
            cloud_data[folder_id] = text
            
        logger.info(f"✅ Found {len(previews)} articles in MongoDB Atlas.")
        
        # If single-folder mode
        if state.get("folder_name"):
            folder = state["folder_name"]
            if folder not in previews:
                return {"error": f"Article '{folder}' not found in MongoDB."}
            return {
                "selected_folders": [folder],
                "previews": previews,
                "cloud_data": cloud_data
            }
            
        return {"previews": previews, "cloud_data": cloud_data}

    # --- DRIVE MODE ---
    # Skip download if --local flag was used or files already exist
    if state.get("skip_download"):
        logger.info(" Using existing local files in drive_downloads/ (--local mode)")
    else:
        drive_url = state["drive_url"]
        logger.info(f"📥 Downloading from Drive: {drive_url}")
        try:
            drive.download_folder(drive_url)
        except Exception as e:
            # If download fails but we already have local files, continue
            existing = [d for d in os.listdir(drive.download_dir)
                        if os.path.isdir(os.path.join(drive.download_dir, d))]
            if existing:
                logger.warning(f"⚠️ Drive download failed ({e}), but found {len(existing)} "
                               f"existing folders locally. Continuing with those.")
            else:
                raise

    # If single-folder mode, just use that one folder
    if state.get("folder_name"):
        folder = state["folder_name"]
        folder_path = os.path.join(drive.download_dir, folder)
        if not os.path.isdir(folder_path):
            return {"error": f"Subfolder '{folder}' not found in drive_downloads/."}
        return {
            "selected_folders": [folder],
            "previews": {},
        }

    # Multi mode: collect article previews for LLM selection
    previews = drive.get_article_previews()
    if len(previews) == 0:
        return {"error": "No articles found in any subfolder!"}

    logger.info(f"✅ Found {len(previews)} article folders")
    return {"previews": previews}


def prompt_user(state: PipelineState) -> dict:
    """Node 1b: Interactive prompt — show article count, ask how many reels."""
    previews = state["previews"]
    num_articles = len(previews)

    print(f"\n{'─'*50}")
    print(f" Found {num_articles} articles in the drive:")
    for i, folder in enumerate(sorted(previews.keys()), 1):
        preview_text = previews[folder][:80].replace('\n', ' ')
        print(f"   {i}. {folder} — {preview_text}...")
    print(f"{'─'*50}")

    # If count was already set via CLI, skip the interactive prompt
    if state.get("target_count") and state["target_count"] > 0:
        count = state["target_count"]
        logger.info(f"Using pre-set count from CLI: {count}")
        return {"target_count": min(count, num_articles)}

    # Interactive prompt
    while True:
        try:
            raw = input(f"\n🎬 How many reels do you want to create? (1–{num_articles}): ").strip()
            count = int(raw)
            if 1 <= count <= num_articles:
                break
            print(f"   ⚠️  Please enter a number between 1 and {num_articles}.")
        except (ValueError, EOFError):
            print(f"   ⚠️  Please enter a valid number between 1 and {num_articles}.")

    logger.info(f"✅ User requested {count} reels")
    return {"target_count": count}


def select_articles(state: PipelineState) -> dict:
    """Node 2: LLM selects the best N articles (with structured output + retry)."""
    previews = state["previews"]
    count = state["target_count"]

    # If there are fewer articles than requested, use all
    if len(previews) <= count:
        logger.info(f"Only {len(previews)} articles available, using all.")
        return {"selected_folders": list(previews.keys())}

    logger.info(f"🤖 Asking LLM to select best {count} from {len(previews)} articles...")

    articles_block = ""
    for folder, text in previews.items():
        articles_block += f"\n--- {folder} ---\n{text}\n"

    system_msg = SystemMessage(
        content="You are a content strategist for a short-form news video channel. "
        "Always respond with ONLY a valid JSON array."
    )
    human_msg = HumanMessage(
        content=f"""Below are {len(previews)} article previews. Select the {count} BEST articles
for engaging 30-second video reels.

SELECTION CRITERIA (in priority order):
1. Emotional impact / shock value — will viewers stop scrolling?
2. Visual potential — is this story easy to illustrate with images?
3. Timeliness / relevance — is this newsworthy right now?
4. Clarity — can the story be told in 30 seconds?
5. Topic diversity — avoid picking multiple articles on the same topic.

ARTICLES:
{articles_block}

RESPOND WITH ONLY a JSON array of the {count} folder names you selected,
ordered from best to worst.  Example: ["article_005", "article_002"]

JSON ARRAY:"""
    )

    llm = get_chat_model(temperature=0.0, max_tokens=500)

    # Retry up to 2 times
    last_error = None
    for attempt in range(3):
        try:
            response = llm.invoke([system_msg, human_msg])
            raw = response.content.strip()

            # Parse JSON (handle markdown code fences)
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            selected = json.loads(raw.strip())
            selected = [s for s in selected if s in previews][:count]

            if not selected:
                raise ValueError("LLM returned no valid folder names")

            logger.info(f"✅ LLM selected (attempt {attempt + 1}): {selected}")
            return {"selected_folders": selected}

        except Exception as e:
            last_error = e
            logger.warning(f"⚠️ LLM selection attempt {attempt + 1} failed: {e}")

    # Final fallback: take the first N
    fallback = list(previews.keys())[:count]
    logger.warning(f"⚠️ All LLM attempts failed ({last_error}). Falling back to: {fallback}")
    return {"selected_folders": fallback}


def generate_script(state: PipelineState) -> dict:
    """Node 3: Generate a script for the current article (with retry)."""
    idx = state["current_folder_idx"]
    folder = state["selected_folders"][idx]

    logger.info(f"📝 [{idx + 1}/{len(state['selected_folders'])}] Generating script for: {folder}")

    # Read article text
    article_text = ""
    num_images = 0
    images = []

    if state.get("use_mongo"):
        article_text = state.get("cloud_data", {}).get(folder, "")
        db = MongoDBService()
        media_docs = db.find_many("media", {"article_id": folder})
        images = [m["local_path"] for m in media_docs if m["media_type"] == "image"]
        num_images = len(images)
    else:
        drive = DriveService(download_dir="drive_downloads")
        folder_path = os.path.join(drive.download_dir, folder)
        assets = drive._categorize_files([
            os.path.join(folder_path, f) for f in os.listdir(folder_path)
        ])
        if assets["article"]:
            with open(assets["article"], "r") as f:
                article_text = f.read()
        images = assets.get("images", [])
        num_images = len(images)

    if not article_text:
        return _add_result(state, folder, status="failed", error="No article text found")
    if num_images == 0:
        return _add_result(state, folder, status="failed", error="No images found")

    words_per_sec = 2.3  # Roughly 140 wpm
    target_words_min = int(20 * words_per_sec) 
    target_words_max = int(25 * words_per_sec)

    system_msg = SystemMessage(
        content="You are a professional news script writer for short-form video reels."
    )
    human_msg = HumanMessage(
        content=f"""SOURCE MATERIAL:
{article_text[:3000]}

TASK: Write a news script tailored for a reel that will show {num_images} images.

STRICT CONSTRAINTS:
1. Length: EXACTLY {target_words_min}-{target_words_max} words (Target 20-25 seconds).
2. Format: Write ONLY the spoken words. 
3. BANNED: Do NOT include any visual cues (e.g. "Visual 1:", "[Image]"), stage directions, speaker tags ("Host:"), or music cues.
4. Hook: Start with a strong opening sentence.
5. Pacing: Structure the script so it naturally flows across {num_images} visual changes.

OUTPUT: Return 100% spoken text only. Nothing else."""
    )

    llm = get_chat_model(temperature=0.8, max_tokens=500)

    # Retry up to 2 times
    last_error = None
    for attempt in range(3):
        try:
            response = llm.invoke([system_msg, human_msg])
            script = response.content.strip().strip('"')

            word_count = len(script.split())
            if word_count < 30:
                raise ValueError(f"Script too short ({word_count} words)")

            logger.info(f"✅ Script generated: {word_count} words (attempt {attempt + 1})")

            # Save to script.txt
            script_path = f"outputs/scripts/script_{folder}.txt"
            os.makedirs(os.path.dirname(script_path), exist_ok=True)
            with open(script_path, "w") as f:
                f.write(script)

            # Generate a short title for the article overlay
            title = _generate_title(article_text, llm)
            logger.info(f"✅ Title: {title}")

            return {
                "results": state["results"] + [{
                    "folder": folder,
                    "script": script,
                    "script_path": script_path,
                    "title": title,
                    "audio_path": "",
                    "reel_path": None,
                    "status": "script_done",
                    "error": None,
                }]
            }

        except Exception as e:
            last_error = e
            logger.warning(f"⚠️ Script attempt {attempt + 1} failed: {e}")

    return _add_result(state, folder, status="failed", error=f"Script generation failed: {last_error}")


def _generate_title(article_text: str, llm) -> str:
    """Use the LLM to generate a short headline title from the article."""
    try:
        msg = HumanMessage(
            content=f"""Read this article and write a SHORT, punchy headline title for it.
The title will be overlaid on a video reel.

RULES:
- Maximum 8 words
- No quotes, no punctuation at the end
- Catchy and attention-grabbing
- ALL CAPS

ARTICLE:
{article_text[:2000]}

TITLE:"""
        )
        response = llm.invoke([msg])
        title = response.content.strip().strip('"').strip("'").strip('.')
        # Ensure uppercase and reasonable length
        title = title.upper()
        if len(title) > 60:
            title = title[:57] + "..."
        return title
    except Exception as e:
        logger.warning(f"⚠️ Title generation failed: {e}")
        return "BREAKING NEWS"


def generate_voiceover(state: PipelineState) -> dict:
    """Node 4: Generate voiceover for the script."""
    current_result = state["results"][-1]

    if current_result["status"] == "failed":
        return {}

    from reel_generator.utils import generate_mock_audio, get_audio_duration

    folder = current_result["folder"]
    script = current_result["script"]

    logger.info(f"🎙️ Generating voiceover for: {folder}")

    tts = ElevenLabsService()
    ts = int(time.time())
    audio_path = f"outputs/audio/pipeline_vo_{folder}_{ts}.mp3"
    os.makedirs(os.path.dirname(audio_path), exist_ok=True)

    # If mock mode is explicitly on, skip API
    if state.get("mock"):
        duration = generate_mock_audio(script, audio_path)
        updated = list(state["results"])
        updated[-1] = {**current_result, "audio_path": audio_path, "voice_duration": duration, "status": "audio_done"}
        return {"results": updated}

    # Otherwise try API with fallback
    try:
        tts.generate_audio(
            text=script,
            output_filename=os.path.basename(audio_path),
            output_path_override=audio_path,
        )
        logger.info(f"✅ Voiceover generated: {audio_path}")

        voice_duration = get_audio_duration(audio_path)

        updated = list(state["results"])
        updated[-1] = {**current_result, "audio_path": audio_path, "voice_duration": voice_duration, "status": "audio_done"}
        return {"results": updated}

    except Exception as e:
        if "quota_exceeded" in str(e).lower() or "401" in str(e):
            logger.warning(f"⚠️ ElevenLabs quota exceeded. Falling back to mock silent audio.")
            duration = generate_mock_audio(script, audio_path)
            updated = list(state["results"])
            updated[-1] = {**current_result, "audio_path": audio_path, "voice_duration": duration, "status": "audio_done"}
            return {"results": updated}
        
        logger.error(f"❌ TTS failed: {e}")
        updated = list(state["results"])
        updated[-1] = {**current_result, "status": "failed", "error": f"TTS failed: {e}"}
        return {"results": updated}


def assemble_reel(state: PipelineState) -> dict:
    """Node 5: Assemble the final reel via run_reel.py."""
    current_result = state["results"][-1]

    if current_result["status"] == "failed":
        return {}  # Skip

    folder = current_result["folder"]
    audio_path = current_result["audio_path"]
    script_path = current_result.get("script_path", "script.txt")

    logger.info(f"🎬 Assembling reel for: {folder}")

    # Get assets
    images = []
    if state.get("use_mongo"):
        db = MongoDBService()
        media_docs = db.find_many("media", {"article_id": folder})
        images = [m["local_path"] for m in media_docs if m["media_type"] == "image"]
    else:
        drive = DriveService(download_dir="drive_downloads")
        folder_path = os.path.join(drive.download_dir, folder)
        assets = drive._categorize_files([
            os.path.join(folder_path, f) for f in os.listdir(folder_path)
        ])
        images = assets.get("images", [])

    output_name = f"reel_{folder}.mp4"
    output_path = f"outputs/final_reels/{output_name}"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Determine intro/outro
    intro = "assets/mbn_reels_intro.mp4"
    outro = "assets/mbn_reels_outro1.mp4"

    # Generate captions
    from reel_generator.caption_generator import render_captions_to_images
    from reel_generator.utils import ensure_dir
    temp_dir = "reel_generator/temp"
    ensure_dir(temp_dir)
    
    script_text = ""
    if os.path.exists(script_path):
        with open(script_path, "r") as f:
            script_text = f.read()

    caption_data = render_captions_to_images(script_text, temp_dir, typewriter=True, use_overlay=USE_OVERLAY)
    caption_images = [c["image_path"] for c in caption_data]

    # Build config
    config = {
        "intro_image": intro,
        "outro_image": outro,
        "middle_images": images,
        "voiceover_audio": audio_path,
        "caption_images": caption_images,
        "title": current_result.get("title", ""),
        "script": script_text,
        "use_overlay": USE_OVERLAY
    }

    try:
        from reel_generator.video_builder import VideoBuilder
        builder = VideoBuilder()
        voice_duration = current_result.get("voice_duration", 0)
        builder.build_video(config, voice_duration, output_path, temp_dir)

        logger.info(f"✅ Reel complete: {output_path}")

        updated = list(state["results"])
        updated[-1] = {**current_result, "reel_path": output_path, "status": "success"}
        return {"results": updated}

    except Exception as e:
        logger.error(f"❌ Reel assembly failed: {e}")
        updated = list(state["results"])
        updated[-1] = {**current_result, "status": "failed", "error": f"VideoBuilder failed: {e}"}
        return {"results": updated}


def advance_or_finish(state: PipelineState) -> dict:
    """Increment the folder pointer for the next iteration."""
    return {"current_folder_idx": state["current_folder_idx"] + 1}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _add_result(state: PipelineState, folder: str, **kwargs) -> dict:
    """Append a result entry for a folder."""
    entry: dict[str, Any] = {
        "folder": folder,
        "script": "",
        "audio_path": "",
        "reel_path": None,
        "status": "pending",
        "error": None,
    }
    entry.update(kwargs)
    return {"results": state["results"] + [entry]}


# ═══════════════════════════════════════════════════════════════════════════════
# CONDITIONAL EDGES
# ═══════════════════════════════════════════════════════════════════════════════

def should_select(state: PipelineState) -> str:
    """After download: go directly to generation (single) or prompt user (multi)."""
    if state.get("error"):
        return "finish"
    if state.get("selected_folders"):
        # Already set (single-mode)
        return "generate_script"
    return "prompt_user"


def after_prompt(state: PipelineState) -> str:
    """After user selects count: LLM selection or use all."""
    count = state["target_count"]
    num_articles = len(state["previews"])
    if count >= num_articles:
        # Use all articles — no LLM selection needed
        return "use_all"
    return "select_articles"


def has_more_articles(state: PipelineState) -> str:
    """After assembly: check if there are more articles to process."""
    idx = state["current_folder_idx"]
    total = len(state["selected_folders"])
    if idx < total:
        return "generate_script"
    return "finish"


def print_summary(state: PipelineState) -> dict:
    """Final node: print results summary."""
    results = state["results"]
    successes = [r for r in results if r["status"] == "success"]
    failures = [r for r in results if r["status"] == "failed"]

    print(f"\n{'='*60}")
    print(f"🏁 LANGGRAPH PIPELINE COMPLETE")
    print(f"   ✅ Succeeded: {len(successes)}/{len(results)}")
    if failures:
        print(f"   ❌ Failed:    {len(failures)}/{len(results)}")
    print(f"{'='*60}")

    for r in successes:
        print(f"   ✅ {r['folder']} → {r['reel_path']}")
    for r in failures:
        print(f"   ❌ {r['folder']} — {r.get('error', 'Unknown error')}")

    print(f"{'='*60}\n")
    return {}


# ═══════════════════════════════════════════════════════════════════════════════
# GRAPH CONSTRUCTION
# ═══════════════════════════════════════════════════════════════════════════════

def use_all_articles(state: PipelineState) -> dict:
    """When user wants all articles, select them all without LLM."""
    return {"selected_folders": list(state["previews"].keys())}


def build_graph() -> StateGraph:
    """Build the LangGraph pipeline graph."""

    graph = StateGraph(PipelineState)

    # ── Add Nodes ─────────────────────────────────────────────────────────
    graph.add_node("download_drive", download_drive)
    graph.add_node("prompt_user", prompt_user)
    graph.add_node("use_all", use_all_articles)
    graph.add_node("select_articles", select_articles)
    graph.add_node("generate_script", generate_script)
    graph.add_node("generate_voiceover", generate_voiceover)
    graph.add_node("assemble_reel", assemble_reel)
    graph.add_node("advance", advance_or_finish)
    graph.add_node("finish", print_summary)

    # ── Entry Point ───────────────────────────────────────────────────────
    graph.set_entry_point("download_drive")

    # ── Edges ─────────────────────────────────────────────────────────────
    # After download → decide: single mode or prompt user?
    graph.add_conditional_edges("download_drive", should_select, {
        "prompt_user": "prompt_user",
        "generate_script": "generate_script",
        "finish": "finish",
    })

    # After user prompt → LLM selection or use all?
    graph.add_conditional_edges("prompt_user", after_prompt, {
        "select_articles": "select_articles",
        "use_all": "use_all",
    })

    # After using all articles or LLM selection → start generating
    graph.add_edge("use_all", "generate_script")
    graph.add_edge("select_articles", "generate_script")

    # Linear: script → voiceover → assemble → advance
    graph.add_edge("generate_script", "generate_voiceover")
    graph.add_edge("generate_voiceover", "assemble_reel")
    graph.add_edge("assemble_reel", "advance")

    # After advance: loop or finish?
    graph.add_conditional_edges("advance", has_more_articles, {
        "generate_script": "generate_script",
        "finish": "finish",
    })

    # Finish → END
    graph.add_edge("finish", END)

    return graph


def run_pipeline(drive_url: str = None, folder_name: str = None, count: int = None, local: bool = False, mock: bool = False, mongo: bool = False):
    """Compile and run the LangGraph pipeline."""
    interactive = count is None and folder_name is None

    graph = build_graph()
    app = graph.compile()

    initial_state: PipelineState = {
        "drive_url": drive_url or "",
        "target_count": count or 0,
        "folder_name": folder_name,
        "skip_download": local,
        "mock": mock,
        "use_mongo": mongo or USE_MONGO,
        "use_drive": not (mongo or USE_MONGO),
        "cloud_data": {},
        "previews": {},
        "selected_folders": [],
        "current_folder_idx": 0,
        "results": [],
        "error": None,
        "interactive": interactive,
    }

    logger.info(" Starting LangGraph Reel Generation Pipeline")
    logger.info(f"   Mode: {'MongoDB Atlas (Cloud)' if initial_state['use_mongo'] else 'Google Drive / Local'}")
    logger.info(f"   Flags: [MONGO={initial_state['use_mongo']}, DRIVE={initial_state['use_drive']}]")
    
    if not initial_state["use_mongo"]:
        logger.info(f"   Drive URL: {drive_url or 'N/A'}")
        
    if folder_name:
        logger.info(f"   Folder: {folder_name}")
    elif count:
        logger.info(f"   Count: {count}")

    # Execute the graph
    final_state = app.invoke(initial_state)

    if final_state.get("error"):
        logger.error(f"❌ Pipeline error: {final_state['error']}")
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# COMBINED REEL PIPELINE (3 articles → 1 reel, ~50s content)
# ═══════════════════════════════════════════════════════════════════════════════

def run_combined_pipeline(drive_url: str, local: bool = False, mock: bool = False):
    """Generate a single combined reel from the top 3 articles (~50s content)."""
    from reel_generator import ReelGenerator
    from reel_generator.caption_generator import render_captions_to_images
    from reel_generator.video_builder import VideoBuilder
    from reel_generator.utils import get_audio_duration, ensure_dir, generate_mock_audio

    logger.info(" Starting COMBINED Reel Pipeline (3 articles → 1 reel)")

    # ── 1. Sync Drive or use local ────────────────────────────────────────
    drive = DriveService(download_dir="drive_downloads")
    if not local:
        drive.sync_folder(drive_url)
    else:
        logger.info(" Using existing local files (--local mode)")

    # ── 2. Get all article folders & select top 3 ─────────────────────────
    previews = drive.get_article_previews()
    if len(previews) == 0:
        logger.error("❌ No articles found!")
        return

    if len(previews) <= 3:
        selected = list(previews.keys())
    else:
        # LLM selects top 3
        articles_block = ""
        for folder, text in previews.items():
            articles_block += f"\n--- {folder} ---\n{text}\n"

        llm = get_chat_model(temperature=0.0, max_tokens=500)
        msg = HumanMessage(
            content=f"""Below are {len(previews)} article previews. Select the 3 BEST for a combined news reel.

CRITERIA: Emotional impact, visual potential, timeliness, topic diversity.

ARTICLES:
{articles_block}

RESPOND WITH ONLY a JSON array of 3 folder names. Example: ["article_005", "article_002", "article_001"]
JSON ARRAY:"""
        )
        try:
            response = llm.invoke([msg])
            raw = response.content.strip()
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            selected = json.loads(raw.strip())
            selected = [s for s in selected if s in previews][:3]
        except Exception as e:
            logger.warning(f"⚠️ LLM selection failed ({e}), using first 3")
            selected = list(previews.keys())[:3]

    logger.info(f"📰 Selected {len(selected)} articles: {selected}")

    # ── 3. For each article: generate script, title, voiceover ────────────
    TARGET_SECS_PER_ARTICLE = 50.0 / len(selected)  # ~16s each for 3 articles
    llm = get_chat_model(temperature=0.8, max_tokens=500)
    tts = ElevenLabsService()

    article_data = []  # list of dicts with all per-article info
    combined_script_parts = []

    for folder in selected:
        folder_path = os.path.join(drive.download_dir, folder)
        assets = drive._categorize_files([
            os.path.join(folder_path, f) for f in os.listdir(folder_path)
        ])

        if not assets["article"] or not assets["images"]:
            logger.warning(f"⚠️ Skipping {folder} (missing article or images)")
            continue

        with open(assets["article"], "r") as f:
            article_text = f.read()

        num_images = len(assets["images"])
        words_per_sec = 2.3
        target_min = int(TARGET_SECS_PER_ARTICLE * words_per_sec)
        target_max = int((TARGET_SECS_PER_ARTICLE + 2) * words_per_sec)

        # Generate script
        human_msg = HumanMessage(
            content=f"""SOURCE MATERIAL:
{article_text[:3000]}

TASK: Write a news script for a reel segment showing {num_images} images.

STRICT CONSTRAINTS:
1. Length: EXACTLY {target_min}-{target_max} words (Target {TARGET_SECS_PER_ARTICLE:.0f} seconds).
2. Format: Write ONLY the spoken words.
3. BANNED: No visual cues, stage directions, speaker tags, or music cues.
4. Hook: Start with a strong opening sentence.

OUTPUT: Return 100% spoken text only."""
        )
        try:
            response = llm.invoke([human_msg])
            script = response.content.strip().strip('"')
            logger.info(f"✅ Script for {folder}: {len(script.split())} words")
        except Exception as e:
            logger.error(f"❌ Script failed for {folder}: {e}")
            continue

        # Generate title
        title = _generate_title(article_text, llm)
        logger.info(f"✅ Title for {folder}: {title}")

        # Generate voiceover
        audio_path = f"outputs/audio/combined_vo_{folder}_{int(time.time())}.mp3"
        os.makedirs(os.path.dirname(audio_path), exist_ok=True)
        try:
            if mock:
                logger.info(f"MOCK mode: Generating silent audio for {folder}")
                generate_mock_audio(script, audio_path)
            else:
                tts.generate_audio(
                    text=script,
                    output_filename=os.path.basename(audio_path),
                    output_path_override=audio_path,
                )
            logger.info(f"✅ Voiceover for {folder}: {audio_path}")
        except Exception as e:
            if "quota_exceeded" in str(e).lower() or "401" in str(e):
                logger.warning(f"⚠️ ElevenLabs quota exceeded for {folder}. Using mock silent audio.")
                generate_mock_audio(script, audio_path)
            else:
                logger.error(f"❌ Voiceover failed for {folder}: {e}")
                continue

        voice_duration = get_audio_duration(audio_path)
        combined_script_parts.append(script)

        article_data.append({
            "folder": folder,
            "images": assets["images"],
            "script": script,
            "title": title,
            "audio_path": audio_path,
            "voice_duration": voice_duration,
        })

    if len(article_data) < 2:
        logger.error("❌ Need at least 2 articles for a combined reel")
        return

    logger.info(f"📋 {len(article_data)} articles prepared. Building combined reel...")

    # ── 4. Concatenate audio files ────────────────────────────────────────
    concat_audio_path = "outputs/audio/combined_concat.mp3"
    audio_list_path = "outputs/audio/concat_list.txt"
    os.makedirs("outputs/audio", exist_ok=True)
    with open(audio_list_path, "w") as f:
        for ad in article_data:
            f.write(f"file '{os.path.abspath(ad['audio_path'])}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", audio_list_path, "-c", "copy", concat_audio_path
    ], check=True, capture_output=True)

    total_voice_duration = sum(ad["voice_duration"] for ad in article_data)
    logger.info(f"🔊 Combined audio: {total_voice_duration:.1f}s")

    # ── 5. Build combined reel ────────────────────────────────────────────
    # Flatten all images and track per-article boundaries
    all_images = []
    combined_script = " ".join(combined_script_parts)

    # Build article segments info for the video builder
    segments = []
    for ad in article_data:
        segments.append({
            "images": ad["images"],
            "title": ad["title"],
            "script": ad["script"],
            "voice_duration": ad["voice_duration"],
            "num_images": len(ad["images"]),
        })
        all_images.extend(ad["images"])

    # Determine intro/outro
    intro = "assets/mbn_reels_intro.mp4"
    outro = "assets/mbn_reels_outro1.mp4"

    # Generate captions for the combined script
    temp_dir = "reel_generator/temp"
    ensure_dir(temp_dir)
    caption_data = render_captions_to_images(combined_script, temp_dir, typewriter=False, use_overlay=USE_OVERLAY)
    caption_images = [c["image_path"] for c in caption_data]

    # Build the combined reel config
    config = {
        "intro_image": intro,
        "outro_image": outro,
        "middle_images": all_images,
        "voiceover_audio": concat_audio_path,
        "caption_images": caption_images,
        "title": "",  # Will use per-segment titles
        "script": combined_script,
        "segments": segments,  # NEW: per-article segment info
        "use_overlay": USE_OVERLAY
    }

    output_path = "outputs/final_reels/combined_reel.mp4"
    ensure_dir(os.path.dirname(output_path))

    builder = VideoBuilder()
    if builder.build_video(config, total_voice_duration, output_path, temp_dir):
        logger.info(f"✅ Combined reel complete: {output_path}")
        print(f"\n✨ SUCCESS! Combined reel ready at: {output_path}")
        print(f"   📰 Articles: {', '.join(ad['folder'] for ad in article_data)}")
        print(f"   ⏱️  Duration: ~{3 + total_voice_duration + 3:.0f}s")
    else:
        logger.error("❌ Combined reel failed")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="LangGraph-Powered Reel Generation Pipeline"
    )
    parser.add_argument(
        "--url", default=None,
        help="Google Drive Folder URL (defaults to GOOGLE_DRIVE_LINK in .env)"
    )
    parser.add_argument(
        "--folder", default=None,
        help="Single subfolder to process (e.g., article_001)"
    )
    parser.add_argument("--count", type=int, help="Target number of reels (skips interactive prompt)")
    parser.add_argument("--local", action="store_true", help="Use existing local files in drive_downloads/")
    parser.add_argument("--mock", action="store_true", help="Generate silent mock voiceovers (save credits)")
    parser.add_argument("--mongo", action="store_true", help="Use MongoDB Atlas for article content and media metadata")
    parser.add_argument("--combined", action="store_true", help="Generate one combined reel from top 3 articles")
    
    args = parser.parse_args()

    # Resolve Drive URL: CLI flag → .env → allow empty if --local
    drive_url = args.url or os.getenv("GOOGLE_DRIVE_LINK", "")
    if not drive_url and not args.local and not args.mongo: # Added args.mongo here
        parser.error(
            "No Drive URL provided. Either pass --url, set GOOGLE_DRIVE_LINK in .env, or use --local/--mongo."
        )

    if args.combined:
        run_combined_pipeline(drive_url, local=args.local, mock=args.mock)
    else:
        run_pipeline(
            drive_url=drive_url,
            folder_name=args.folder,
            count=args.count,
            local=args.local,
            mock=args.mock,
            mongo=args.mongo
        )

