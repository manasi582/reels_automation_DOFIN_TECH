"""LangChain ChatModel factory — picks the right model from settings.

Used exclusively by the LangGraph pipeline. The existing LLMService
remains untouched for all other entry points.
"""

from langchain_core.language_models.chat_models import BaseChatModel
from src.config.settings import settings
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


def get_chat_model(temperature: float = 0.7, max_tokens: int = 1000) -> BaseChatModel:
    """Return a LangChain ChatModel based on ``settings.LLM_PROVIDER``.

    Supported providers: openai, anthropic, groq.
    API keys and model names are read from the existing ``.env`` config.
    """
    provider = settings.LLM_PROVIDER

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model=settings.OPENAI_MODEL,
            api_key=settings.OPENAI_API_KEY,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        logger.info(f"LangChain: using OpenAI ({settings.OPENAI_MODEL})")
        return model

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        model = ChatAnthropic(
            model=settings.ANTHROPIC_MODEL,
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        logger.info(f"LangChain: using Anthropic ({settings.ANTHROPIC_MODEL})")
        return model

    elif provider == "groq":
        from langchain_groq import ChatGroq

        model = ChatGroq(
            model=settings.GROQ_MODEL,
            api_key=settings.GROQ_API_KEY,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        logger.info(f"LangChain: using Groq ({settings.GROQ_MODEL})")
        return model

    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")
