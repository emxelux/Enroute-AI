# main.py
import atexit
import argparse
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from agents.graph import create_travel_graph, create_postgres_checkpointer

travel_graph = None
_postgres_context = None
_postgres_entered = False


def _close_postgres_checkpointer():
    global _postgres_context, _postgres_entered
    if _postgres_context is not None and _postgres_entered:
        _postgres_context.__exit__(None, None, None)
    _postgres_context = None
    _postgres_entered = False

def get_graph():
    global travel_graph, _postgres_context, _postgres_entered
    if travel_graph is not None:
        return travel_graph
    
    try:
        # from_conn_string() returns a context manager; keep it open for the
        # lifetime of the compiled graph and close it during interpreter exit.
        _postgres_context = create_postgres_checkpointer()
        checkpointer = _postgres_context.__enter__()
        _postgres_entered = True
        checkpointer.setup()
        travel_graph = create_travel_graph(checkpointer)
        atexit.register(_close_postgres_checkpointer)
        print("✅ Using PostgreSQL checkpointer")
    except Exception as e:
        _close_postgres_checkpointer()
        print(f"⚠️ PostgreSQL unavailable ({e}); using in-memory checkpoints")
        travel_graph = create_travel_graph()
    
    return travel_graph

def run_chat(message: str, thread_id: str = "default", user_country: str = "US"):
    graph = get_graph()
    
    initial_state = {
        "messages": [HumanMessage(content=message)],
        "user_id": "cli_user",
        "user_country": user_country,
    }

    config = {"configurable": {"thread_id": thread_id}}
    
    result = graph.invoke(initial_state, config=config)
    
    # Get the last user-facing AI message (not an internal tool response).
    messages = result.get("messages", [])
    tool_messages = [msg for msg in messages if isinstance(msg, ToolMessage)]
    last_ai_msg = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            last_ai_msg = msg.content
            break
            
    print(f"\n--- Agent: {result.get('current_agent')} ---")
    print(last_ai_msg)
    # print("\n--- State ---")
    # print(f"trip_complete: {bool(result.get('trip_complete'))}")
    # print(f"flight_selected: {result.get('flight_selected') is not None}")
    # print(f"hotel_selected: {result.get('hotel_selected') is not None}")
    flight_options_found = result.get("flight_results") is not None or any(
        msg.name == "search_flight" for msg in tool_messages
    )
    hotel_options_found = result.get("hotel_results") is not None or any(
        msg.name == "search_hotels" for msg in tool_messages
    )
    print(f"flight_options_found: {flight_options_found}")
    print(f"hotel_options_found: {hotel_options_found}")
    print(f"trip_details: {result.get('trip_details')}")

    return result


def run_interactive_chat(thread_id: str = "default", user_country: str = "US"):
    """Keep accepting human responses on the same checkpointed conversation."""
    print("TripMate CLI - Type 'exit' or press Ctrl+C to quit")
    while True:
        try:
            message = input("\nYou: ").strip()
            if not message:
                continue
            if message.lower() in {"exit", "quit"}:
                print("Bye!")
                return
            run_chat(message, thread_id=thread_id, user_country=user_country)
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            return

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TripMate CLI")
    parser.add_argument("message", nargs="?", help="Your travel request e.g. 'I want to go to Paris'")
    parser.add_argument("--thread-id", default="default", help="Conversation thread ID to keep memory")
    parser.add_argument("--country", default="US", help="User country for currency")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process the supplied message and exit without prompting for follow-ups",
    )

    args = parser.parse_args()

    if not args.message:
        run_interactive_chat(thread_id=args.thread_id, user_country=args.country)
    else:
        run_chat(args.message, thread_id=args.thread_id, user_country=args.country)
        if not args.once:
            run_interactive_chat(thread_id=args.thread_id, user_country=args.country)