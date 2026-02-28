"""Agent 3: Multi-Variation Script Generator Agent."""
from typing import List, Any
from datetime import datetime
from src.models.news_article import WorthyStory  
from src.models.script_variation import (
    ScriptVariation,
    VariationGenerationResult
)
from src.services.llm_service import LLMService
from src.config.settings import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class MultiVariationGeneratorAgent:
    """Agent responsible for generating 3 script variations per worthy story."""
    
    def __init__(self):
        """Initialize the Multi-Variation Generator Agent."""
        self.llm_service = LLMService()
        self.words_per_minute = settings.WORDS_PER_MINUTE
        self.target_duration_min = settings.TARGET_SCRIPT_DURATION_MIN
        self.target_duration_max = settings.TARGET_SCRIPT_DURATION_MAX
        
        logger.info(
            f"Initialized MultiVariationGeneratorAgent "
            f"(target duration: {self.target_duration_min}-{self.target_duration_max}s)"
        )
    
    def generate_variations(
        self, 
        worthy_stories: List[WorthyStory],
        styles: List[str] = ["A", "B", "C"]
    ) -> List[VariationGenerationResult]:
        """Generate variations for each worthy story.
        
        Args:
            worthy_stories: List of worthy stories from Agent 2
            styles: List of styles to generate (default: ["A", "B", "C"])
            
        Returns:
            List of VariationGenerationResult
        """
        logger.info(f"Generating {len(styles)} variations for {len(worthy_stories)} worthy stories")
        
        all_results = []
        
        for idx, story in enumerate(worthy_stories, 1):
            logger.info(
                f"Generating variations {idx}/{len(worthy_stories)}: "
                f"{story.article.headline[:60]}..."
            )
            
            try:
                result = self._generate_for_story(story, styles)
                all_results.append(result)
                logger.info(f"✓ Generated {len(result.variations)} variations for story {idx}")
            except Exception as e:
                logger.error(f"Failed to generate variations for story {story.article.article_id}: {e}")
                continue
        
        total_variations = sum(len(r.variations) for r in all_results)
        logger.info(
            f"Variation generation complete: {total_variations} total variations "
            f"from {len(all_results)} stories"
        )
        
        return all_results

    def _generate_for_story(self, story: WorthyStory, styles: List[str]) -> VariationGenerationResult:
        """Generate specific variations for a single story.
        
        Args:
            story: WorthyStory to generate variations for
            styles: Styles to generate
            
        Returns:
            VariationGenerationResult
        """
        variations = []
        
        # Prepare story data for LLM
        story_data = {
            "headline": story.article.headline,
            "summary": story.article.summary,
            "suggested_angles": story.suggested_angles
        }
        
        # Generate requested style(s)
        for style in styles:
            try:
                variation = self._generate_variation(story, story_data, style)
                variations.append(variation)
            except Exception as e:
                logger.error(f"Failed to generate variation {style} for {story.article.article_id}: {e}")
                variation = self._create_fallback_variation(story, style, str(e))
                variations.append(variation)
        
        return VariationGenerationResult(
            story=story,
            variations=variations,
            generation_timestamp=datetime.now()
        )
    
    def _generate_variation(
        self,
        story: WorthyStory,
        story_data: dict,
        style: str
    ) -> ScriptVariation:
        """Generate a single variation using LLM.
        
        Args:
            story: Original WorthyStory
            story_data: Story data dict for LLM
            style: "A", "B", or "C"
            
        Returns:
            ScriptVariation object
        """
        logger.debug(f"Generating variation {style} for {story.article.article_id}")
        
        # Call LLM to generate script
        script_data = self.llm_service.generate_script_variation(story_data, style)
        
        # Estimate duration
        script_text = script_data['script_text']
        estimated_duration = self._estimate_duration(script_text)
        
        # Create variation ID
        variation_id = f"{story.article.article_id}_var_{style}"
        
        return ScriptVariation(
            variation_id=variation_id,
            story_id=story.article.article_id,
            style=style,
            script_text=script_text,
            hook_text=script_data['hook_text'],
            estimated_duration=estimated_duration,
            visual_cues=script_data.get('visual_cues', []),
            caption_segments=script_data.get('caption_segments', [])
        )
    
    def _estimate_duration(self, script_text: Any) -> int:
        """Estimate reading time for the script.
        
        Args:
            script_text: Full script text
            
        Returns:
            Estimated duration in seconds
        """
        # Ensure it's a string
        if not isinstance(script_text, str):
            script_text = str(script_text)
            
        # Count words (simple split by whitespace)
        word_count = len(script_text.split())
        
        # Calculate duration: (words / words_per_minute) * 60 seconds
        duration_seconds = int((word_count / self.words_per_minute) * 60)
        
        return duration_seconds
    
    def _create_fallback_variation(
        self,
        story: WorthyStory,
        style: str,
        error_msg: str
    ) -> ScriptVariation:
        """Create a fallback variation when generation fails.
        
        Args:
            story: Original WorthyStory
            style: "A", "B", or "C"
            error_msg: Error message
            
        Returns:
            Basic ScriptVariation with placeholder content
        """
        variation_id = f"{story.article.article_id}_var_{style}_fallback"
        
        # Create a simple fallback script
        fallback_script = f"""[ERROR: Script generation failed - {error_msg}]

[0:00-0:05] Breaking news: {story.article.headline}

[0:05-0:20] {story.article.summary[:200]}

[0:20-0:55] This is a placeholder script that was generated due to an error.
The actual script generation failed for this variation.

[0:55-1:00] Stay tuned for more updates."""
        
        return ScriptVariation(
            variation_id=variation_id,
            story_id=story.article.article_id,
            style=style,
            script_text=fallback_script,
            hook_text="Breaking news",
            estimated_duration=60,
            visual_cues=["0:00 - Error placeholder"],
            caption_segments=["Breaking news", "Error occurred"]
        )
