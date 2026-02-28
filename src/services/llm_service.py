"""LLM service for AI-powered content evaluation."""
import json
from typing import Dict, Any, Optional
from src.config.settings import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class LLMService:
    """Service for interacting with LLM APIs (OpenAI or Anthropic)."""
    
    def __init__(self):
        """Initialize LLM service based on configured provider."""
        self.provider = settings.LLM_PROVIDER
        
        if self.provider == "openai":
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
                self.model = settings.OPENAI_MODEL
                logger.info(f"Initialized OpenAI client with model: {self.model}")
            except ImportError:
                raise ImportError("OpenAI package not installed. Run: pip install openai")
        
        elif self.provider == "anthropic":
            try:
                from anthropic import Anthropic
                self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
                self.model = settings.ANTHROPIC_MODEL
                logger.info(f"Initialized Anthropic client with model: {self.model}")
            except ImportError:
                raise ImportError("Anthropic package not installed. Run: pip install anthropic")
        
        elif self.provider == "groq":
            try:
                from groq import Groq
                self.client = Groq(api_key=settings.GROQ_API_KEY)
                self.model = settings.GROQ_MODEL
                logger.info(f"Initialized Groq client with model: {self.model}")
            except ImportError:
                raise ImportError("Groq package not installed. Run: pip install groq")
        
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")
    
    def evaluate_worthiness(self, article_data: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate if a news story is worthy of becoming a reel.
        
        Args:
            article_data: Dictionary with article information
            
        Returns:
            Dictionary with evaluation results including scores, verdict, and suggested angles
        """
        prompt = self._build_worthiness_prompt(article_data)
        
        try:
            response = self._call_llm(prompt)
            evaluation = self._parse_worthiness_response(response)
            return evaluation
        except Exception as e:
            logger.error(f"Error evaluating article {article_data.get('article_id')}: {e}")
            # Return default SKIP verdict on error
            return {
                "scores": {
                    "trending": 1,
                    "suitability": 1,
                    "hook_potential": 1,
                    "visual": 1,
                    "audience_interest": 1
                },
                "verdict": "SKIP",
                "reasoning": f"Error during evaluation: {str(e)}",
                "suggested_angles": []
            }
    
    def _build_worthiness_prompt(self, article: Dict[str, Any]) -> str:
        """Build the evaluation prompt for worthiness judgment.
        
        Args:
            article: Article data dictionary
            
        Returns:
            Formatted prompt string
        """
        return f"""You are a viral content strategist judging if this news story should become a short-form video reel.

Article: {article.get('headline', 'No headline')}
Summary: {article.get('summary', 'No summary')}
Published: {article.get('published_at', 'Unknown')}
Source: {article.get('source', 'Unknown')}

Analyze this story across 5 dimensions and provide scores from 1-10:

1. Trending Score (1-10): Is this going viral RIGHT NOW?
   - Appears in multiple sources?
   - Recent (< 12 hours old)?
   - Social media buzz potential?
   - Breaking news or developing story?

2. Reel Suitability (1-10): Can this be a compelling 60-second video?
   - Can be explained clearly in 60 seconds?
   - Emotionally engaging?
   - Target audience will care?
   - Story has clear narrative arc?

3. Hook Potential (1-10): Can we grab attention in first 3 seconds?
   - Surprising or novel angle?
   - Controversy or debate potential?
   - Curiosity-inducing headline?
   - Celebrity/influencer involvement?

4. Visual Storytelling (1-10): Do we have strong visuals?
   - Good imagery available?
   - Visual interest in the topic?
   - Can create compelling graphics/animations?
   - Avatar presentation fits the story?

5. Audience Interest (1-10): Will people care about this?
   - Relevance to general audience?
   - Timely and important?
   - Shareable content?
   - Creates discussion?

Provide your response in the following JSON format:
{{
  "scores": {{
    "trending": <1-10>,
    "suitability": <1-10>,
    "hook_potential": <1-10>,
    "visual": <1-10>,
    "audience_interest": <1-10>
  }},
  "reasoning": "<1-2 sentence explanation of your scoring>",
  "verdict": "<MAKE_REEL if overall strong, MAYBE_REEL if borderline, SKIP if not suitable>",
  "suggested_angles": ["<angle1>", "<angle2>", "<angle3>"]
}}

If verdict is MAKE_REEL or MAYBE_REEL, provide 3 different creative angles/hooks we could use.
If verdict is SKIP, leave suggested_angles as an empty array.

Respond ONLY with valid JSON, no additional text."""
    
    def _call_llm(self, prompt: str, temperature: float = 0.7) -> str:
        """Call the configured LLM with the prompt.
        
        Args:
            prompt: The prompt to send
            temperature: Sampling temperature (0.0 to 1.0)
            
        Returns:
            LLM response text
        """
        if self.provider == "openai":
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a viral content expert. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=500
            )
            return response.choices[0].message.content
        
        elif self.provider == "anthropic":
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                temperature=temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return response.content[0].text
            
        elif self.provider == "groq":
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a viral content expert. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=500
            )
            return response.choices[0].message.content
    
    def _parse_worthiness_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into structured evaluation data.
        
        Args:
            response: Raw LLM response
            
        Returns:
            Parsed evaluation dictionary
        """
        try:
            # Try to extract JSON from response
            # Sometimes LLMs add extra text, so we look for JSON block
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx == -1 or end_idx == 0:
                raise ValueError("No JSON found in response")
            
            json_str = response[start_idx:end_idx]
            evaluation = json.loads(json_str, strict=False)
            
            # Validate structure
            required_keys = ['scores', 'verdict', 'reasoning']
            if not all(key in evaluation for key in required_keys):
                raise ValueError(f"Missing required keys in response")
            
            # Ensure suggested_angles exists
            if 'suggested_angles' not in evaluation:
                evaluation['suggested_angles'] = []
            
            return evaluation
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.debug(f"Raw response: {response}")
            raise
    
    def generate_script_variation(self, story_data: Dict[str, Any], style: str) -> Dict[str, Any]:
        """Generate a script variation for a worthy story.
        
        Args:
            story_data: Dictionary with story information (headline, summary, etc.)
            style: Variation style - "A" (Direct), "B" (Engaging), or "C" (Provocative)
            
        Returns:
            Dictionary with script text and metadata
        """
        prompt = self._build_script_generation_prompt(story_data, style)
        
        try:
            response = self._call_llm_for_script(prompt)
            script_data = self._parse_script_response(response)
            return script_data
        except Exception as e:
            logger.error(f"Error generating script variation {style}: {e}")
            raise
    
    def _build_script_generation_prompt(self, story: Dict[str, Any], style: str) -> str:
        """Build the script generation prompt based on style.
        
        Args:
            story: Story data with headline, summary, suggested_angles
            style: "A", "B", or "C"
            
        Returns:
            Formatted prompt string
        """
        headline = story.get('headline', 'No headline')
        summary = story.get('summary', 'No summary')
        angles = story.get('suggested_angles', [])
        angles_text = '\n'.join(f"  • {angle}" for angle in angles) if angles else "  • None provided"
        
        base_context = f"""News Story:
Headline: {headline}
Summary: {summary}
Suggested Creative Angles:
{angles_text}

Your task: Create a 60-second reel script (approximately 150 words).

Requirements:
- Exactly 55-60 seconds when read aloud
- Strong hook in first 3-5 seconds
- Clear structure with timing
- Conversational language (written for speaking)
- Include structured visual cue markers strictly in the format: "[MM:SS-MM:SS] - SHOW_AVATAR" or "[MM:SS-MM:SS] - SHOW_IMAGE"
- Alternate between showing the avatar and the news images to keep the video dynamic. 
- Example: Hook (Avatar) -> Context (Image) -> Details (Avatar) -> Conclusion (Image)"""
        
        if style == "A":
            # Direct/Informative Style
            style_prompt = f"""{base_context}

STYLE: Direct/Informative (Professional News Delivery)

Hook: Use "BREAKING:" or "Just announced:" style opening
Tone: Authoritative, clear, fact-focused
Approach: Straightforward news delivery

Structure:
- Hook (3-5 sec): Grab attention with the headline
- Context (12-15 sec): Background information
- Main (30-35 sec): Key facts and developments
- Close (8-10 sec): Impact and takeaway

Provide your response in the following JSON format:
{{
  "script_text": "<full script with timestamps like [0:00-0:05], [0:05-0:15], etc.>",
  "hook_text": "<first 3-5 seconds opening>",
  "visual_cues": ["<timestamp> - <visual description>", ...],
  "caption_segments": ["<key phrase 1>", "<key phrase 2>", ...]
}}

Respond ONLY with valid JSON, no additional text."""
            
        elif style == "B":
            # Engaging/Story Style
            style_prompt = f"""{base_context}

STYLE: Engaging/Story (Conversational Storytelling)

Hook: Relatable opening that draws viewers in
Tone: Friendly, approachable, human
Approach: Tell it like a narrative

Structure:
- Hook (3-5 sec): "So this just happened..." or "Here's a story..."
- Setup (12-15 sec): Set the scene
- Story (30-35 sec): Tell it like a narrative
- Wrap (8-10 sec): "And here's why it matters..."

Provide your response in the following JSON format:
{{
  "script_text": "<full script with timestamps like [0:00-0:05], [0:05-0:15], etc.>",
  "hook_text": "<first 3-5 seconds opening>",
  "visual_cues": ["<timestamp> - <visual description>", ...],
  "caption_segments": ["<key phrase 1>", "<key phrase 2>", ...]
}}

Respond ONLY with valid JSON, no additional text."""
            
        else:  # style == "C"
            # Provocative/Debate Style
            style_prompt = f"""{base_context}

STYLE: Provocative/Debate (Attention-Grabbing)

Hook: Surprising or question-based opening
Tone: Edgy, creates tension or curiosity
Approach: Bold, controversial angle

Structure:
- Hook (3-5 sec): "Wait... what?!" or "Is this even legal?"
- Tension (12-15 sec): Build intrigue
- Reveal (30-35 sec): Deliver the story with impact
- Debate (8-10 sec): Leave with a question or controversy

Provide your response in the following JSON format:
{{
  "script_text": "<full script with timestamps like [0:00-0:05], [0:05-0:15], etc.>",
  "hook_text": "<first 3-5 seconds opening>",
  "visual_cues": ["<timestamp> - <visual description>", ...],
  "caption_segments": ["<key phrase 1>", "<key phrase 2>", ...]
}}

Respond ONLY with valid JSON, no additional text."""
        
        return style_prompt
    
    def _call_llm_for_script(self, prompt: str, temperature: float = 0.8) -> str:
        """Call LLM for script generation (higher token limit).
        
        Args:
            prompt: The prompt to send
            temperature: Sampling temperature (0.0 to 1.0)
            
        Returns:
            LLM response text
        """
        if self.provider == "openai":
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert viral content script writer. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,  # More creative for script generation
                max_tokens=1000
            )
            return response.choices[0].message.content
        
        elif self.provider == "anthropic":
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return response.content[0].text
            
        elif self.provider == "groq":
            # Reuses Groq method with higher word limits
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert viral content script writer. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=1000
            )
            return response.choices[0].message.content
    
    def _parse_script_response(self, response: str) -> Dict[str, Any]:
        """Parse script generation response.
        
        Args:
            response: Raw LLM response
            
        Returns:
            Parsed script dictionary
        """
        try:
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx == -1 or end_idx == 0:
                raise ValueError("No JSON found in response")
            
            json_str = response[start_idx:end_idx]
            script_data = json.loads(json_str, strict=False)
            
            # Validate required fields
            required_keys = ['script_text', 'hook_text']
            if not all(key in script_data for key in required_keys):
                raise ValueError(f"Missing required keys in script response")
            
            # Ensure optional fields exist
            if 'visual_cues' not in script_data:
                script_data['visual_cues'] = []
            if 'caption_segments' not in script_data:
                script_data['caption_segments'] = []
            
            return script_data
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse script response: {e}")
            logger.debug(f"Raw response: {response}")
            raise
    
    def evaluate_variation(self, variation_data: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a script variation on human-likeness and attention-grabbing.
        
        Args:
            variation_data: Dictionary with variation script and metadata
            
        Returns:
            Dictionary with evaluation scores and reasoning
        """
        prompt = self._build_evaluation_prompt(variation_data)
        
        try:
            response = self._call_llm(prompt)
            evaluation = self._parse_evaluation_response(response)
            return evaluation
        except Exception as e:
            logger.error(f"Error evaluating variation: {e}")
            raise
    
    def _build_evaluation_prompt(self, variation: Dict[str, Any]) -> str:
        """Build the variation evaluation prompt.
        
        Args:
            variation: Variation data with script_text, style, etc.
            
        Returns:
            Formatted prompt string
        """
        script_text = variation.get('script_text', 'No script')
        style = variation.get('style', 'Unknown')
        
        style_names = {
            "A": "Direct/Informative",
            "B": "Engaging/Story",
            "C": "Provocative/Debate"
        }
        style_name = style_names.get(style, style)
        
        return f"""You are an expert in viral short-form content. Evaluate this reel script on two critical dimensions.

SCRIPT (Style: {style_name}):
{script_text}

EVALUATION:

1. HUMAN-LIKENESS (1-10)
How natural and human does this sound?
- Does it sound like a real person talking?
- Is the language conversational and authentic?
- Are there any AI-tells or robotic phrases?
- Does it have personality?

Score: __/10
Reasoning: [explain]

2. ATTENTION-GRABBING (1-10)
How effective is this at capturing and keeping attention?
- Hook strength (first 3 seconds)
- Scroll-stopping power
- Maintains interest throughout
- Creates curiosity or emotion
- Likelihood of watching till end

Score: __/10
Reasoning: [explain]

OVERALL ASSESSMENT:
- Strengths: [list 2-3 key strengths]
- Weaknesses: [list 2-3 areas for improvement]
- Recommendation: EXCELLENT (9-10) / GOOD (7-8) / AVERAGE (5-6) / POOR (<5)

Provide your response in the following JSON format:
{{
  "human_likeness": <1-10>,
  "attention_grabbing": <1-10>,
  "reasoning": "<1-2 sentences combining both evaluations>",
  "strengths": ["<strength1>", "<strength2>", ...],
  "weaknesses": ["<weakness1>", "<weakness2>", ...],
  "recommendation": "<EXCELLENT|GOOD|AVERAGE|POOR>"
}}

Respond ONLY with valid JSON, no additional text."""
    
    def _parse_evaluation_response(self, response: str) -> Dict[str, Any]:
        """Parse variation evaluation response.
        
        Args:
            response: Raw LLM response
            
        Returns:
            Parsed evaluation dictionary
        """
        try:
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx == -1 or end_idx == 0:
                raise ValueError("No JSON found in response")
            
            json_str = response[start_idx:end_idx]
            evaluation = json.loads(json_str, strict=False)
            
            # Validate required fields
            required_keys = ['human_likeness', 'attention_grabbing', 'recommendation']
            if not all(key in evaluation for key in required_keys):
                raise ValueError(f"Missing required keys in evaluation response")
            
            # Ensure optional fields exist
            if 'reasoning' not in evaluation:
                evaluation['reasoning'] = "No reasoning provided"
            if 'strengths' not in evaluation:
                evaluation['strengths'] = []
            if 'weaknesses' not in evaluation:
                evaluation['weaknesses'] = []
            
            return evaluation
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse evaluation response: {e}")
            logger.debug(f"Raw response: {response}")
            raise

