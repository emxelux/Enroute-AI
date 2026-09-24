from langchain.chat_models import init_chat_model
from tools.flight_tool import get_flight


llm = init_chat_model(
    "groq:openai/gpt-oss-120b"
)

f_llm = f_llm.bind_tools([get_flight])
