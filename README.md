# AI Reel Generator (LangGraph Edition)

A professional, agentic video production pipeline that transforms news stories into high-quality social media reels. Built with **LangGraph**, **Groq LLM**, and **ElevenLabs**.

---

## Quick Start

### 1. Installation
```bash
git clone [repository-url]
cd reels_gen_ai
python -m venv venv
source venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

### 2. Configuration
Copy the template and add your API keys:
```bash
cp .env.example .env
```
Key requirements:
- `GROQ_API_KEY` (for the "Brain")
- `ELEVENLABS_API_KEY` (for the Voice)
- `GOOGLE_DRIVE_LINK` (pointing to your news source folder)

---

## Usage Commands

### **Single Article Mode (~30s, Typewriter Captions)**
Run for a specific folder you've already synced:
```bash
python langgraph_pipeline.py --folder article_001 --local
```
Ask the LLM to pick the top story and download it:
```bash
python langgraph_pipeline.py --count 1
```

### **Combined Digest Mode (~50s, Static Captions)**
Creates a multi-story "News Round-up" video:
```bash
python langgraph_pipeline.py --combined --local
```

### **Testing (Mock Mode)**
Skips ElevenLabs API to save credits, generating silent placeholder audio:
```bash
python langgraph_pipeline.py --combined --local --mock
```

---

## Key Features

### News Overlay System
The pipeline includes a stylistic "News Frame" (Search Bar + Breaking News bar). 
- **Toggle:** Controlled globally in `langgraph_pipeline.py` via `USE_OVERLAY = True/False`.
- **Smart Layout:** Titles and captions automatically shift positions (y-axis) when the overlay is enabled to stay within the frame's safe area.

### LangGraph Orchestration
The project uses a directed acyclic graph (DAG) to manage the workflow:
1.  **Sync:** Pulls images/articles from Drive.
2.  **Brain:** LLM generates a script and headline.
3.  **Voice:** ElevenLabs generates high-quality audio.
4.  **Assemble:** FFmpeg builds the final 1080x1920 video with smooth Ken Burns transitions (30fps).

### Silent Audio Fallback
If ElevenLabs credits are exhausted, the system **automatically** switches to "Mock Mode," generating silent audio so the video can still be built for layout testing.

---

## Project Structure

### Root Directory
- `langgraph_pipeline.py`: The main entry point and "Brain" of the project; orchestrates the entire workflow using LangGraph.

### Core Modules (reel_generator/)
- `video_builder.py`: Contains the logic for FFmpeg assembly, video transitions, and Ken Burns effects.
- `caption_generator.py`: Renders spoken text into styled image overlays for video subtitles.
- `utils.py`: General utility functions for directory management, audio duration calculation, and mock audio generation.
- `main.py`: Legacy entry point or standalone test script for the reel generation logic.
- `tts.py`: Specialized text-to-speech utility for converting scripts to audio.

### Integration Services (src/services/)
- `drive_service.py`: Handles downloading and syncing folders from Google Drive using gdown.
- `mongodb_service.py`: Interfaces with MongoDB Atlas for storing and retrieving article content and media metadata.
- `elevenlabs_service.py`: Direct integration with the ElevenLabs API for high-quality AI voiceovers.
- `langchain_llm.py`: Common utility to initialize and manage LangChain chat models (e.g., Groq).
- `llm_service.py`: Service for handling direct LLM prompts and specific content generation tasks.
- `faceless_video_service.py`: High-level wrapper service that coordinates multiple sub-services for video production.

### Utility Scripts (scripts/)
- `upload_drive_data.py`: A migration tool to upload local files from drive downloads to MongoDB Atlas.
- `create_reel_from_cloud.py`: Standalone script to generate reels using data primarily sourced from the cloud (MongoDB).
- `test_atlas.py`: Simple utility to verify the MongoDB Atlas connection and credentials.

### Other Directories
- `assets/`: Contains logos, news overlays, and other static branding files.
- `demos/`: Example videos and transition previews.
- `tests/`: Contains unit tests like `test_faceless_reel.py` for verifying project components.

---

## Performance & Tuning
To speed up rendering on Apple Silicon (M1/M2/M3), you can adjust the `video_builder.py` to use `h264_videotoolbox` instead of `libx264`.

---