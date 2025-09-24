from ai_search.config.settings import settings

GOOGLE_API_KEY = settings.google_api_key
OPENAI_API_KEY = settings.openai_api_key
TAVILY_API_KEY = settings.tavily_api_key
MODEL = settings.model_name

__all__ = [
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "TAVILY_API_KEY",
    "MODEL",
    "settings",
]
