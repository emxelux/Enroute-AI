from langchain.chat_models import init_chat_model
from tools.flight_tool import search_flight
from dotenv import load_dotenv


load_dotenv()

flight_llm = init_chat_model(
    "groq:openai/gpt-oss-20b"
    # "google_genai:gemini-2.5-flash"
)

# flight_llm = llm.bind_tools([search_flight])
