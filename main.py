import os
import uuid

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

from agents.graph import create_travel_graph

load_dotenv()


def _print_interrupt(interrupt_value: dict) -> None:
    """Display an interrupt prompt and any options supplied by a graph node."""
    print(f"\n{interrupt_value.get('question', 'More information is needed.')}")

    options = interrupt_value.get("options")
    if not options:
        return

    if isinstance(options, dict):
        option_items = options.items()
    elif isinstance(options, list):
        option_items = enumerate(options, start=1)
    else:
        print(options)
        return

    for option_id, option in option_items:
        if interrupt_value.get("type") == "flight_selection" and isinstance(option, dict):
            route_parts = []
            for slice_info in option.get("slices", []):
                origin = slice_info.get("origin", {}).get("code", "?")
                destination = slice_info.get("destination", {}).get("code", "?")
                departure = slice_info.get("departure") or "time unavailable"
                arrival = slice_info.get("arrival") or "time unavailable"
                route_parts.append(
                    f"{origin} → {destination} ({departure}–{arrival})"
                )

            route = "; ".join(route_parts) or "Route unavailable"
            price = (
                f"{option.get('total_amount', '?')} "
                f"{option.get('total_currency', '')}"
            ).strip()

            print(f"- {option_id}: {route} | {price}")
        elif isinstance(option, dict):
            description = (
                option.get("label")
                or option.get("name")
                or option.get("description")
                or option
            )
            print(f"- {option_id}: {description}")
        else:
            print(f"- {option_id}: {option}")


def _print_result(result: dict) -> None:
    """Print the latest assistant response and selected flight, if present."""
    print("\n--- TRIP PLANNING RESULT ---")

    for message in reversed(result.get("messages", [])):
        content = getattr(message, "content", None)
        if content and message.__class__.__name__ == "AIMessage":
            print(content)
            break

    selected = result.get("flight_selected")
    if selected:
        print("\nSelected flight:")
        print(f"Offer ID: {selected.get('offer_id', 'unknown')}")
        print(
            f"Price: {selected.get('total_amount', '?')} "
            f"{selected.get('total_currency', '')}"
        )


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured in the environment.")

    initial_request = input("What trip would you like to plan? ").strip()
    if not initial_request:
        print("Please enter a trip request to get started.")
        return

    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    with PostgresSaver.from_conn_string(database_url) as checkpointer:
        checkpointer.setup()
        graph = create_travel_graph(checkpointer=checkpointer)

        print("\n--- STARTING TRIP PLANNER ---")
        result = graph.invoke(
            {"messages": [HumanMessage(content=initial_request)]},
            config=config,
        )

        # Resume the same graph thread for each node interrupt.
        while result.get("__interrupt__"):
            interrupts = result["__interrupt__"]
            interrupt_info = interrupts[0].value
            _print_interrupt(interrupt_info)

            answer = input("\nYour response (or type 'quit' to stop): ").strip()
            if answer.casefold() == "quit":
                print(
                    "Trip planning paused. You can resume this thread using its "
                    f"thread ID: {config['configurable']['thread_id']}"
                )
                return
            if not answer:
                print("Please enter a response so I can continue.")
                continue

            result = graph.invoke(Command(resume=answer), config=config)

        _print_result(result)


if __name__ == "__main__":
    main()
