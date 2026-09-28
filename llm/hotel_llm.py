from langchain.chat_models import init_chat_model
from tools.hotel_tool import search_hotels


llm = init_chat_model(
    "groq:openai/gpt-oss-120b"
)

hotel_llm = llm.bind_tools([search_hotels])
