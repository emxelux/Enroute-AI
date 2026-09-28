"""
Flight Sub-Agent - Handles flight search, selection, and booking.
"""
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


FLIGHT_AGENT_PROMPT = """You are the Flight Sub-Agent. Help users find and book flights.

Your capabilities:
1. Search for flights using the search_flight tool
2. Convert prices to user's currency using convert_currency
3. Present options clearly with all relevant details

Required information for search:
- origin_airport: 3-letter IATA code (e.g., "LOS", "JFK", "LHR")
- destination_airport: 3-letter IATA code
- departure_date: YYYY-MM-DD format
- cabin_class: economy, premium_economy, business, or first
- no_of_adult: number of adults (optional)
- no_of_children: number of children (optional)

If user provides city names instead of airport codes, ask for clarification or use common airports.

When presenting results:
- Show airline, departure/arrival times, duration, price
- Convert price to user's currency if known (from state.user_country)
- Ask user to select a flight by providing the offer ID or details

After user selects a flight, store the selection in state.flight_selected and return to supervisor."""


def flight_agent_node(state: TravelState) -> Command[Literal["flight_tools", "supervisor"]]:
    """
    Flight agent node - processes flight-related queries.
    """
    messages = state.get("messages", [])
    user_country = state.get("user_country", "US")

    # Add system prompt with context
    system_msg = SystemMessage(content=FLIGHT_AGENT_PROMPT + f"\n\nUser's country: {user_country}")

    # Prepare messages for LLM
    llm_messages = [system_msg] + messages

    # Invoke LLM with tools
    response = flight_llm_with_tools.invoke(llm_messages)

    # Check if LLM wants to use tools
    if response.tool_calls:
        return Command(
            goto="flight_tools",
            update={"messages": [response]}
        )

    # No tool calls - check if flight was selected
    if _is_flight_selected(response.content, state):
        return Command(
            goto="supervisor",
            update={"messages": [response], "current_agent": "supervisor"}
        )

    # Just responding to user
    return Command(
        goto="supervisor",
        update={"messages": [response], "current_agent": "supervisor"}
    )


def flight_tools_node(state: TravelState) -> Command[Literal["flight_agent"]]:
    """
    Execute flight tools and return to flight agent.
    """
    result = flight_tool_node.invoke(state)
    return Command(
        goto="flight_agent",
        update=result
    )


def _is_flight_selected(response_text: str, state: TravelState) -> bool:
    """Check if user selected a flight in their response."""
    # Simple heuristic - in production, use structured output
    flight_selected = state.get("flight_selected")
    return flight_selected is not None