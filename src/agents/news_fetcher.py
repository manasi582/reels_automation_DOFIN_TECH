"""Agent 1: News Fetcher & Aggregation Agent."""
import hashlib
import requests
from datetime import datetime, timedelta
from typing import List, Set
from src.models.news_article import NewsArticle
from src.config.settings import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class NewsFetcherAgent:
    """Agent responsible for fetching and aggregating news content."""
    
    def __init__(self):
        """Initialize the News Fetcher Agent."""
        self.api_key = settings.NEWS_API_KEY
        self.endpoint = settings.NEWS_API_ENDPOINT
        self.fetch_count = settings.FETCH_ARTICLE_COUNT
        logger.info(f"Initialized NewsFetcherAgent (target: {self.fetch_count} articles)")
    
    def fetch_news(self, category: str = "general", language: str = "en") -> List[NewsArticle]:
        """Fetch recent news articles from News API.
        
        Args:
            category: News category (business, entertainment, general, health, science, sports, technology)
            language: Language code (default: en)
            
        Returns:
            List of NewsArticle objects
        """
        logger.info(f"Fetching news articles (category: {category}, target: {self.fetch_count})")
        
        try:
            # Fetch articles from News API
            raw_articles = self._fetch_from_api(category, language)
            
            # Deduplicate articles
            unique_articles = self._deduplicate(raw_articles)
            
            logger.info(f"Successfully fetched {len(unique_articles)} unique articles")
            return unique_articles
            
        except Exception as e:
            logger.error(f"Error fetching news: {e}")
            raise
    
    def _fetch_from_api(self, category: str, language: str) -> List[NewsArticle]:
        """Make API request to News API.
        
        Args:
            category: News category
            language: Language code
            
        Returns:
            List of NewsArticle objects
        """
        params = {
            "apiKey": self.api_key,
            "category": category,
            "language": language,
            "pageSize": min(self.fetch_count, 100),  # API max is 100
        }
        
        try:
            response = requests.get(self.endpoint, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") != "ok":
                raise ValueError(f"API returned error: {data.get('message', 'Unknown error')}")
            
            articles = []
            for idx, article_data in enumerate(data.get("articles", [])):
                try:
                    news_article = self._parse_article(article_data, idx)
                    articles.append(news_article)
                except Exception as e:
                    logger.warning(f"Failed to parse article: {e}")
                    continue
            
            return articles
            
        except requests.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise
    
    def _parse_article(self, article_data: dict, index: int) -> NewsArticle:
        """Parse raw API response into NewsArticle object.
        
        Args:
            article_data: Raw article data from API
            index: Article index for ID generation
            
        Returns:
            NewsArticle object
        """
        # Generate unique ID from URL or title
        url = article_data.get("url", "")
        article_id = hashlib.md5(url.encode()).hexdigest()[:12] if url else f"article_{index}"
        
        # Parse published date
        published_str = article_data.get("publishedAt")
        try:
            published_at = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            published_at = datetime.now()
        
        return NewsArticle(
            article_id=article_id,
            headline=article_data.get("title", "No title"),
            summary=article_data.get("description", "No description available"),
            content=article_data.get("content"),
            source=article_data.get("source", {}).get("name", "Unknown"),
            author=article_data.get("author"),
            published_at=published_at,
            url=url,
            image_url=article_data.get("urlToImage"),
            category=None  # News API doesn't return category in response
        )
    
    def _deduplicate(self, articles: List[NewsArticle]) -> List[NewsArticle]:
        """Remove duplicate articles based on headline similarity.
        
        Args:
            articles: List of articles to deduplicate
            
        Returns:
            Deduplicated list of articles
        """
        seen_headlines: Set[str] = set()
        unique_articles = []
        
        for article in articles:
            # Normalize headline for comparison
            normalized = article.headline.lower().strip()
            
            # Skip if we've seen a very similar headline
            is_duplicate = False
            for seen in seen_headlines:
                if self._similarity(normalized, seen) > 0.85:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                seen_headlines.add(normalized)
                unique_articles.append(article)
            else:
                logger.debug(f"Skipping duplicate: {article.headline}")
        
        logger.info(f"Removed {len(articles) - len(unique_articles)} duplicates")
        return unique_articles
    
    def _similarity(self, s1: str, s2: str) -> float:
        """Calculate simple word-based similarity between two strings.
        
        Args:
            s1: First string
            s2: Second string
            
        Returns:
            Similarity score between 0 and 1
        """
        words1 = set(s1.split())
        words2 = set(s2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
