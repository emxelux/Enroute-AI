"""
Hotel Sub-Agent - Handles hotel search, selection, and booking.
"""
from typing import Literal
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.types import Command
from langgraph.prebuilt import ToolNode

from state import TravelState
from llm.hotel_llm import hotel_llm
from tools.hotel_tool import search_hotels
from tools.currency_tool import convert_currency, convert_detected_currencies


# Tools available to hotel agent
hotel_tools = [search_hotels, convert_currency, convert_detected_currencies]
hotel_tool_node = ToolNode(hotel_tools)

# Bind tools to LLM
hotel_llm_with_tools = hotel_llm.bind_tools(hotel_tools)


HOTEL_AGENT_PROMPT = """You are the Hotel Sub-Agent. Help users find and book hotels.

Your capabilities:
1. Search for hotels using the search_hotels tool
2. Convert prices to user's currency using convert_currency
3. Present options clearly with all relevant details

Required information for search:
- name: City name, location, or hotel name
- check_in_date: YYYY-MM-DD format
- check_out_date: YYYY-MM-DD format

When presenting results:
- Show hotel name, rating, nearby places, price (if available)
- Convert price to user's currency if known (from state.user_country)
- Ask user to select a hotel by name

After user selects a hotel, store the selection in state.hotel_selected and return to supervisor."""


def hotel_agent_node(state: TravelState) -> Command[Literal["hotel_tools", "supervisor"]]:
    """
    Hotel agent node - processes hotel-related queries.
    """
    messages = state.get("messages", [])
    user_country = state.get("user_country", "US")

    # Add system prompt with context
    system_msg = SystemMessage(content=HOTEL_AGENT_PROMPT + f"\n\nUser's country: {user_country}")

    # Prepare messages for LLM
    llm_messages = [system_msg] + messages

    # Invoke LLM with tools
    response = hotel_llm_with_tools.invoke(llm_messages)

    # Check if LLM wants to use tools
    if response.tool_calls:
        return Command(
            goto="hotel_tools",
            update={"messages": [response]}
        )

    # No tool calls - check if hotel was selected
    if _is_hotel_selected(response.content, state):
        return Command(
            goto="supervisor",
            update={"messages": [response], "current_agent": "supervisor"}
        )

    # Just responding to user
    return Command(
        goto="supervisor",
        update={"messages": [response], "current_agent": "supervisor"}
    )


def hotel_tools_node(state: TravelState) -> Command[Literal["hotel_agent"]]:
    """
    Execute hotel tools and return to hotel agent.
    """
    result = hotel_tool_node.invoke(state)
    return Command(
        goto="hotel_agent",
        update=result
    )


def _is_hotel_selected(response_text: str, state: TravelState) -> bool:
    """Check if user selected a hotel in their response."""
    hotel_selected = state.get("hotel_selected")
    return hotel_selected is not None