from tools.hotel_tool import search_hotels
from llm.provider import create_chat_model_pair


llm, fallback_llm = create_chat_model_pair(
    "hotel",
    groq_default="openai/gpt-oss-120b",
)

hotel_llm = llm.bind_tools([search_hotels])
hotel_fallback_llm = fallback_llm.bind_tools([search_hotels])
