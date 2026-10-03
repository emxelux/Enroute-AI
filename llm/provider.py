"""Shared Groq/Gemini model setup with rate-limit-only fallback."""

import logging
import os
from typing import Any

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

load_dotenv()

logger = logging.getLogger(__name__)

# langchain-google-genai reads GOOGLE_API_KEY. Accept GEMINI_API_KEY as well.
if os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]


def create_chat_model_pair(task: str, groq_default: str):
    """Create primary and fallback chat models for a task.

    Groq is primary by default. Set LLM_PRIMARY_PROVIDER=gemini to reverse
    provider order. Task model overrides are GROQ_<TASK>_MODEL and
    GEMINI_<TASK>_MODEL; GEMINI_MODEL is the shared Gemini override.
    """
    task = task.upper()
    groq_model = os.getenv(f"GROQ_{task}_MODEL", groq_default)
    gemini_model = os.getenv(
        f"GEMINI_{task}_MODEL",
        os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    )

    groq = init_chat_model(f"groq:{groq_model}")
    gemini = init_chat_model(f"google_genai:{gemini_model}")

    if os.getenv("LLM_PRIMARY_PROVIDER", "groq").strip().lower() == "gemini":
        return gemini, groq
    return groq, gemini


def is_rate_limit_error(error: BaseException) -> bool:
    """Recognize common 429/quota errors from provider SDKs and HTTP clients."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        status = getattr(current, "status_code", None)
        if status is None:
            status = getattr(current, "code", None)
        response = getattr(current, "response", None)
        if status is None and response is not None:
            status = getattr(response, "status_code", None)
        if str(status) == "429":
            return True

        message = str(current).lower().replace("_", " ")
        if any(term in message for term in (
            "rate limit",
            "rate-limit",
            "too many requests",
            "resource exhausted",
            "quota exceeded",
            "quota has been exceeded",
        )):
            return True
        current = current.__cause__ or current.__context__
    return False


def invoke_with_rate_limit_fallback(
    primary: Any,
    fallback: Any,
    input: Any,
    **kwargs: Any,
) -> Any:
    """Invoke primary; retry once on the fallback only for rate-limit errors."""
    try:
        return primary.invoke(input, **kwargs)
    except Exception as error:
        if not is_rate_limit_error(error):
            raise
        logger.warning(
            "Primary LLM provider was rate limited; retrying with the fallback provider."
        )
        return fallback.invoke(input, **kwargs)