"""Configuration settings for the reels generator."""
import os
from dotenv import load_dotenv
from typing import Literal

load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""
    
    # Google Drive
    GOOGLE_DRIVE_LINK: str = os.getenv("GOOGLE_DRIVE_LINK", "")
    
    # News API
    NEWS_API_KEY: str = os.getenv("NEWS_API_KEY", "")
    NEWS_API_ENDPOINT: str = os.getenv("NEWS_API_ENDPOINT", "https://newsapi.org/v2/top-headlines")
    
    # LLM Configuration
    # Choose provider: "openai", "anthropic", or "groq"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    
    # Agent Configuration
    FETCH_ARTICLE_COUNT: int = int(os.getenv("FETCH_ARTICLE_COUNT", "10"))
    TARGET_WORTHY_STORIES_MIN: int = int(os.getenv("TARGET_WORTHY_STORIES_MIN", "1"))
    TARGET_WORTHY_STORIES_MAX: int = int(os.getenv("TARGET_WORTHY_STORIES_MAX", "1"))
    WORTHINESS_THRESHOLD: float = float(os.getenv("WORTHINESS_THRESHOLD", "7.0"))
    MAYBE_THRESHOLD: float = float(os.getenv("MAYBE_THRESHOLD", "6.0"))
    
    # Script Generation Settings
    TARGET_SCRIPT_DURATION_MIN: int = int(os.getenv("TARGET_SCRIPT_DURATION_MIN", "55"))
    TARGET_SCRIPT_DURATION_MAX: int = int(os.getenv("TARGET_SCRIPT_DURATION_MAX", "60"))
    WORDS_PER_MINUTE: int = int(os.getenv("WORDS_PER_MINUTE", "150"))
    
    # Variation Evaluation Settings
    TARGET_VARIATIONS_FOR_PRODUCTION: int = int(os.getenv("TARGET_VARIATIONS_FOR_PRODUCTION", "5"))
    EXCELLENCE_BONUS_THRESHOLD: float = float(os.getenv("EXCELLENCE_BONUS_THRESHOLD", "8.0"))
    
    # Media Generation Settings (Phase 3)
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgmqS29pXo3W")  # Default: News voice
    
    # Faceless Reel Settings
    INTRO_LOGO_PATH: str = os.getenv("INTRO_LOGO_PATH", "assets/logo.png")
    OUTRO_IMAGE_PATH: str = os.getenv("OUTRO_IMAGE_PATH", "assets/outro.png")
    INTRO_DURATION: float = float(os.getenv("INTRO_DURATION", "3.0"))
    OUTRO_DURATION: float = float(os.getenv("OUTRO_DURATION", "3.0"))
    IMAGE_DURATION: float = float(os.getenv("IMAGE_DURATION", "5.0"))
    TRANSITION_DURATION: float = float(os.getenv("TRANSITION_DURATION", "1.2"))
    
    # File Storage
    OUTPUT_DIR: str = os.getenv("OUTPUT_DIR", "outputs")
    FINAL_OUTPUT_DIR: str = os.path.join(OUTPUT_DIR, "final_reels")
    FONT_PATH: str = os.getenv("FONT_PATH", "/System/Library/Fonts/Supplemental/Arial Bold.ttf")  # Default for Mac
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    @property
    def audio_dir(self) -> str:
        return os.path.join(self.OUTPUT_DIR, "audio")
    
    @property
    def video_dir(self) -> str:
        return os.path.join(self.OUTPUT_DIR, "video")
    
    @property
    def images_dir(self) -> str:
        return os.path.join(self.OUTPUT_DIR, "images")
    
    def ensure_dirs(self) -> None:
        """Create output directories if they don't exist."""
        os.makedirs(self.audio_dir, exist_ok=True)
        os.makedirs(self.video_dir, exist_ok=True)
        os.makedirs(self.images_dir, exist_ok=True)
        os.makedirs(self.FINAL_OUTPUT_DIR, exist_ok=True)
    
    @classmethod
    def validate(cls) -> None:
        """Validate required settings are present."""
        errors = []
        
        if not cls.NEWS_API_KEY:
            errors.append("NEWS_API_KEY is required")
        
        if cls.LLM_PROVIDER == "openai" and not cls.OPENAI_API_KEY:
            errors.append("OPENAI_API_KEY is required when using OpenAI provider")
        
        if cls.LLM_PROVIDER == "anthropic" and not cls.ANTHROPIC_API_KEY:
            errors.append("ANTHROPIC_API_KEY is required when using Anthropic provider")
            
        if cls.LLM_PROVIDER == "groq" and not cls.GROQ_API_KEY:
            errors.append("GROQ_API_KEY is required when using Groq provider")
            
        # We don't error on these yet to allow testing Phase 1/2 without them, 
        # but we'll log warnings if missing when Phase 3 is triggered.
        
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")


settings = Settings()
