from langchain.chat_models import init_chat_model
from tools.flight_tool import search_flight


llm = init_chat_model(
    "groq:openai/gpt-oss-120b"
)

flight_llm = llm.bind_tools([search_flight])
