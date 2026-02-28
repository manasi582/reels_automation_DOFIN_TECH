"""Agent 2: Worthiness Judgment Agent."""
from typing import List
from datetime import datetime
from src.models.news_article import (
    NewsArticle,
    WorthinessScores,
    WorthyStory,
    WorthinessEvaluation
)
from src.services.llm_service import LLMService
from src.config.settings import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class WorthinessJudgeAgent:
    """Agent responsible for judging if news stories are worthy of reel creation."""
    
    def __init__(self):
        """Initialize the Worthiness Judge Agent."""
        self.llm_service = LLMService()
        self.worthiness_threshold = settings.WORTHINESS_THRESHOLD
        self.maybe_threshold = settings.MAYBE_THRESHOLD
        self.target_min = settings.TARGET_WORTHY_STORIES_MIN
        self.target_max = settings.TARGET_WORTHY_STORIES_MAX
        
        logger.info(
            f"Initialized WorthinessJudgeAgent "
            f"(target: {self.target_min}-{self.target_max} stories, "
            f"threshold: {self.worthiness_threshold})"
        )
    
    def evaluate_stories(self, articles: List[NewsArticle]) -> WorthinessEvaluation:
        """Evaluate all articles and select worthy stories for reel creation.
        
        Args:
            articles: List of news articles to evaluate
            
        Returns:
            WorthinessEvaluation with selected worthy stories
        """
        logger.info(f"Evaluating {len(articles)} articles for worthiness")
        
        all_evaluations = []
        
        # Evaluate each article
        for idx, article in enumerate(articles, 1):
            logger.info(f"Evaluating {idx}/{len(articles)}: {article.headline[:60]}...")
            try:
                worthy_story = self._evaluate_single_article(article)
                all_evaluations.append(worthy_story)
            except Exception as e:
                logger.error(f"Failed to evaluate article {article.article_id}: {e}")
                continue
        
        # Select top worthy stories
        worthy_stories = self._select_worthy_stories(all_evaluations)
        
        # Count verdicts
        make_reel_count = sum(1 for s in worthy_stories if s.verdict == "MAKE_REEL")
        maybe_count = sum(1 for s in worthy_stories if s.verdict == "MAYBE_REEL")
        skipped_count = len(articles) - len(worthy_stories)
        
        logger.info(
            f"Evaluation complete: {make_reel_count} MAKE_REEL, "
            f"{maybe_count} MAYBE_REEL, {skipped_count} SKIP"
        )
        
        return WorthinessEvaluation(
            total_articles_evaluated=len(articles),
            worthy_stories=worthy_stories,
            skipped_count=skipped_count,
            maybe_count=maybe_count,
            evaluation_timestamp=datetime.now()
        )
    
    def _evaluate_single_article(self, article: NewsArticle) -> WorthyStory:
        """Evaluate a single article for worthiness.
        
        Args:
            article: NewsArticle to evaluate
            
        Returns:
            WorthyStory with evaluation results
        """
        # Prepare article data for LLM
        article_data = {
            "article_id": article.article_id,
            "headline": article.headline,
            "summary": article.summary,
            "source": article.source,
            "published_at": article.published_at.isoformat()
        }
        
        # Get LLM evaluation
        evaluation_result = self.llm_service.evaluate_worthiness(article_data)
        
        # Parse scores
        scores = WorthinessScores(**evaluation_result["scores"])
        
        # Calculate weighted score
        worthiness_score = scores.calculate_weighted_score()
        
        # Determine verdict based on score and LLM suggestion
        llm_verdict = evaluation_result.get("verdict", "SKIP")
        
        # Use score-based threshold as primary decision
        if worthiness_score >= self.worthiness_threshold:
            verdict = "MAKE_REEL"
        elif worthiness_score >= self.maybe_threshold:
            verdict = "MAYBE_REEL"
        else:
            verdict = "SKIP"
        
        # But defer to LLM if it says SKIP (trust the expert)
        if llm_verdict == "SKIP":
            verdict = "SKIP"
        
        return WorthyStory(
            article=article,
            verdict=verdict,
            scores=scores,
            worthiness_score=worthiness_score,
            reasoning=evaluation_result.get("reasoning", "No reasoning provided"),
            suggested_angles=evaluation_result.get("suggested_angles", [])
        )
    
    def _select_worthy_stories(self, all_evaluations: List[WorthyStory]) -> List[WorthyStory]:
        """Select the top worthy stories from all evaluations.
        
        Args:
            all_evaluations: All evaluated stories
            
        Returns:
            List of selected worthy stories with priority rankings
        """
        # First, get all MAKE_REEL stories
        make_reel_stories = [
            story for story in all_evaluations
            if story.verdict == "MAKE_REEL"
        ]
        
        # Sort by worthiness score (highest first)
        make_reel_stories.sort(key=lambda x: x.worthiness_score, reverse=True)
        
        # If we have enough MAKE_REEL stories, select top ones
        if len(make_reel_stories) >= self.target_min:
            selected = make_reel_stories[:self.target_max]
            logger.info(f"Selected {len(selected)} MAKE_REEL stories")
        else:
            # Need to include MAYBE_REEL stories
            maybe_stories = [
                story for story in all_evaluations
                if story.verdict == "MAYBE_REEL"
            ]
            maybe_stories.sort(key=lambda x: x.worthiness_score, reverse=True)
            
            # Combine and take top stories
            combined = make_reel_stories + maybe_stories
            needed = max(self.target_min, min(len(combined), self.target_max))
            selected = combined[:needed]
            
            logger.info(
                f"Selected {len(selected)} stories "
                f"({len(make_reel_stories)} MAKE_REEL + "
                f"{len(selected) - len(make_reel_stories)} MAYBE_REEL)"
            )
        
        # Assign priority rankings
        for idx, story in enumerate(selected, 1):
            story.priority_rank = idx
        
        return selected
