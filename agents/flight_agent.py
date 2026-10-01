
from typing import Literal
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.types import Command
from langgraph.prebuilt import ToolNode

from state import TravelState
from llm.flight_llm import flight_llm
from tools.flight_tool import search_flight
from tools.currency_tool import convert_currency, convert_detected_currencies


# Tools available to flight agent
flight_tools = [search_flight, convert_currency, convert_detected_currencies]
flight_tool_node = ToolNode(flight_tools)

# Bind tools to LLM
flight_llm_with_tools = flight_llm.bind_tools(flight_tools)

with open("prompts/flight_agent_prompt.md", "r") as f:
    FLIGHT_AGENT_PROMPT = f.read()

def flight_agent_node(state: TravelState):
    """
    Flight agent node - processes flight-related queries.
    """
    