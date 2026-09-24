from langchain.chat_models import init_chat_model
from tools.hotel_tool import search_hotels


llm = init_chat_model(
    "groq:openai/gpt-oss-120b"
)

h_llm = h_llm.bind_tools([search_hotels])
