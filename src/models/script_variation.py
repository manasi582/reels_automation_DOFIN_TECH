"""Data models for script variations and evaluations."""
from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from src.models.news_article import WorthyStory


class ScriptVariation(BaseModel):
    """A single script variation for a worthy story."""
    
    variation_id: str = Field(description="Unique identifier for this variation")
    story_id: str = Field(description="Reference to the original worthy story article ID")
    style: Literal["A", "B", "C"] = Field(description="Variation style: A=Direct, B=Engaging, C=Provocative")
    script_text: str = Field(description="Full script text (55-60 seconds)")
    hook_text: str = Field(description="Opening hook (first 3-5 seconds)")
    estimated_duration: int = Field(ge=10, le=120, description="Estimated reading time in seconds")
    visual_cues: List[str] = Field(default_factory=list, description="Timing markers for visual elements")
    caption_segments: List[str] = Field(default_factory=list, description="Key phrases for captions")
    
    class Config:
        json_schema_extra = {
            "example": {
                "variation_id": "var_001_A",
                "story_id": "news_001",
                "style": "A",
                "script_text": "Breaking news: A major development has occurred...",
                "hook_text": "Breaking news: A major development has occurred",
                "estimated_duration": 58,
                "visual_cues": ["0:00 - Opening shot", "0:15 - Context image"],
                "caption_segments": ["Breaking news", "Major development", "Here's what it means"]
            }
        }


class VariationScores(BaseModel):
    """Evaluation scores for a script variation."""
    
    human_likeness: int = Field(ge=1, le=10, description="How natural and human the script sounds")
    attention_grabbing: int = Field(ge=1, le=10, description="Hook strength and retention potential")
    
    def calculate_combined_score(self) -> float:
        """Calculate combined score with bonus for dual excellence.
        
        Returns:
            Combined score (can exceed 10 with bonus)
        """
        base_score = (self.human_likeness * 0.5) + (self.attention_grabbing * 0.5)
        
        # Bonus for excellence in both dimensions
        if self.human_likeness >= 8 and self.attention_grabbing >= 8:
            base_score += 0.5
        
        return base_score


class EvaluatedVariation(BaseModel):
    """Script variation with evaluation results."""
    
    variation: ScriptVariation = Field(description="The script variation")
    story: Optional[WorthyStory] = Field(default=None, description="The original worthy story")
    scores: VariationScores = Field(description="Evaluation scores")
    combined_score: float = Field(ge=1.0, le=10.5, description="Combined score with bonus")
    reasoning: str = Field(description="Detailed evaluation explanation")
    strengths: List[str] = Field(default_factory=list, description="Strong points of the script")
    weaknesses: List[str] = Field(default_factory=list, description="Areas for improvement")
    recommendation: Literal["EXCELLENT", "GOOD", "AVERAGE", "POOR"] = Field(
        description="Overall quality recommendation"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "variation": {"variation_id": "var_001_A", "style": "A"},
                "scores": {
                    "human_likeness": 9,
                    "attention_grabbing": 8
                },
                "combined_score": 9.0,
                "reasoning": "Exceptional natural flow with strong hook",
                "strengths": ["Clear delivery", "Professional tone"],
                "weaknesses": ["Could be more engaging"],
                "recommendation": "EXCELLENT"
            }
        }


class VariationGenerationResult(BaseModel):
    """Result of generating variations for a single story."""
    
    story: WorthyStory = Field(description="The original worthy story")
    variations: List[ScriptVariation] = Field(
        min_length=1,
        max_length=3,
        description="1 to 3 script variations"
    )
    generation_timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_schema_extra = {
            "example": {
                "story": {"article": {"article_id": "news_001"}},
                "variations": [],
                "generation_timestamp": "2024-01-24T09:00:00Z"
            }
        }


class VariationEvaluationResult(BaseModel):
    """Complete evaluation results from variation evaluator."""
    
    total_variations_evaluated: int = Field(description="Total number of variations evaluated")
    all_evaluations: List[EvaluatedVariation] = Field(description="All evaluated variations")
    selected_for_production: List[EvaluatedVariation] = Field(
        description="Top variations selected for production"
    )
    evaluation_timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_variations_evaluated": 30,
                "all_evaluations": [],
                "selected_for_production": [],
                "evaluation_timestamp": "2024-01-24T09:00:00Z"
            }
        }
