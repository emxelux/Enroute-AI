from tools.flight_tool import search_flight
from llm.provider import create_chat_model_pair


flight_llm, flight_fallback_llm = create_chat_model_pair(
    "flight",
    groq_default="openai/gpt-oss-20b",
)

# flight_llm = llm.bind_tools([search_flight])
