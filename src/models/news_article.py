"""Data models for news articles and worthiness evaluation."""
from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class NewsArticle(BaseModel):
    """Raw news article from news API."""
    
    article_id: str = Field(description="Unique identifier for the article")
    headline: str = Field(description="Article headline/title")
    summary: str = Field(description="Article summary (100-200 words)")
    content: Optional[str] = Field(default=None, description="Full article content if available")
    source: str = Field(description="News source name")
    author: Optional[str] = Field(default=None, description="Article author")
    published_at: datetime = Field(description="Publication timestamp")
    url: str = Field(description="Source URL")
    image_url: Optional[str] = Field(default=None, description="Main article image URL")
    category: Optional[str] = Field(default=None, description="Article category/topic")
    
    class Config:
        json_schema_extra = {
            "example": {
                "article_id": "news_001",
                "headline": "Major Tech Company Announces AI Breakthrough",
                "summary": "A leading tech company revealed a significant advancement in AI...",
                "source": "TechNews",
                "published_at": "2024-01-24T09:00:00Z",
                "url": "https://example.com/article",
                "category": "technology"
            }
        }


class WorthinessScores(BaseModel):
    """Individual dimension scores for worthiness evaluation."""
    
    trending: int = Field(ge=1, le=10, description="Is this going viral RIGHT NOW?")
    suitability: int = Field(ge=1, le=10, description="Can this be a compelling 60-sec video?")
    hook_potential: int = Field(ge=1, le=10, description="Can we grab attention in first 3 seconds?")
    visual: int = Field(ge=1, le=10, description="Do we have strong visuals?")
    audience_interest: int = Field(ge=1, le=10, description="Will people care about this?")
    
    def calculate_weighted_score(self) -> float:
        """Calculate weighted worthiness score.
        
        Returns:
            Weighted score between 1-10
        """
        return (
            self.trending * 0.25 +
            self.suitability * 0.25 +
            self.hook_potential * 0.25 +
            self.visual * 0.15 +
            self.audience_interest * 0.10
        )


class WorthyStory(BaseModel):
    """News article with worthiness judgment."""
    
    article: NewsArticle = Field(description="Original news article")
    verdict: Literal["MAKE_REEL", "MAYBE_REEL", "SKIP"] = Field(description="Decision verdict")
    scores: WorthinessScores = Field(description="Individual dimension scores")
    worthiness_score: float = Field(ge=1.0, le=10.0, description="Weighted overall score")
    reasoning: str = Field(description="Explanation of the verdict")
    suggested_angles: List[str] = Field(
        default_factory=list,
        description="3 creative angles/hooks for MAKE_REEL stories"
    )
    priority_rank: Optional[int] = Field(default=None, description="Priority ranking among worthy stories")
    
    class Config:
        json_schema_extra = {
            "example": {
                "article": {"article_id": "news_001", "headline": "AI Breakthrough"},
                "verdict": "MAKE_REEL",
                "scores": {
                    "trending": 9,
                    "suitability": 8,
                    "hook_potential": 9,
                    "visual": 7,
                    "audience_interest": 8
                },
                "worthiness_score": 8.2,
                "reasoning": "Breaking tech news with high virality...",
                "suggested_angles": [
                    "Shocking reveal approach",
                    "Explanation style",
                    "Debate angle"
                ]
            }
        }


class WorthinessEvaluation(BaseModel):
    """Complete evaluation result from worthiness judgment."""
    
    total_articles_evaluated: int = Field(description="Total number of articles evaluated")
    worthy_stories: List[WorthyStory] = Field(description="Stories selected for reel creation")
    skipped_count: int = Field(description="Number of articles skipped")
    maybe_count: int = Field(description="Number of maybe articles")
    evaluation_timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_articles_evaluated": 40,
                "worthy_stories": [],
                "skipped_count": 28,
                "maybe_count": 2,
                "evaluation_timestamp": "2024-01-24T09:00:00Z"
            }
        }
