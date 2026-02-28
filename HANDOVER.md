# 🤝 Project Handover: AI Reel Generator

## 📌 Project Overview
The AI Reel Generator is a **LangGraph-powered agentic pipeline** that automates the creation of "faceless" news reels. It pulls content from Google Drive, uses LLMs (Groq/OpenAI) for storytelling, and ElevenLabs for voice synthesis.

## 🏁 Current Status: PRODUCTION READY
The system is stable and currently being used to generate both:
1.  **Single News Reels (~30s):** Focused deep-dives with typewriter-style captions.
2.  **Combined News Digests (~50s):** Multi-topic roundups with static captions and smooth transitions.

## 🌟 Key Deliverables
- **The Core Engine:** `langgraph_pipeline.py` (Orchestrates the entire logic).
- **Style System:** Conditional News Overlay (Toggleable frame with auto-repositioning text).
- **Robustness:** Automatic silent-audio fallback if ElevenLabs credits are exhausted.
- **Visuals:** High-quality Ken Burns (30fps) and advanced FFmpeg transitions (`zoomin`, `pixelize`).

## 🤖 Technical Philosophy: What is an "Agentic" System?
Instead of a simple linear script, we developed a state-driven "Agentic Workflow" using **LangGraph**.

- **LLM Layer vs. AI Agent:** A simple "LLM Layer" just converts text. An **AI Agent** uses the LLM as a "Brain" to make autonomous decisions—like deciding which news is viral, how to pivot a story's angle, or when to trigger an emergency silent-audio fallback.
- **Resilient:** It can retry individual failed steps (like Voiceover) without restarting the entire process.
- **Future-Proof:** The modular "node" design makes it easy to add "Human-in-the-loop" approval gates or new AI models later.

## 🔄 Alternatives & Comparison
If the team considers other ways to do this, here is how they compare to our custom approach:
1.  **Low-Code (Zapier/Make):** Faster to build, but 10x more expensive per reel and lacks branding control.
2.  **Browser-Based (Remotion):** Better for UI-heavy design, but much slower and uses high server RAM.
3.  **Custom Python (Our Choice):** Lowest cost (<$0.15/reel), fastest rendering, and total control over logic.

## 💰 Cost & Performance FAQ
### **What is the cost per reel?**
- **LLM (The Brain):** ~$0.01 per reel (using Groq).
- **Voice (The Voice):** ~$0.05 - $0.10 per reel (ElevenLabs).
*Total: Under $0.15 per reel.*

### **How long does rendering take?**
- **Single Reel (30s):** ~45-60 seconds.
- **Why?** We prioritized high-quality 30fps zooms and cinematic transitions over speed. Rendering can be cut by 50% on Macs by enabling the `videotoolbox` hardware encoder.

## 🔑 Infrastructure Requirements
- **LLM:** Groq (primary) or OpenAI.
- **Voice:** ElevenLabs.
- **Storage:** Google Drive API.
- **Compute:** Local or Server with `FFmpeg` installed.

---
*Created by [Manasi Patil] - February 2026*
