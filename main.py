import os
from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from agents.graph import create_travel_graph
import uuid
load_dotenv()

thread_id = uuid.uuid4()

DB_URL = os.getenv("DATABASE_URL")
config = {"configurable": {"thread_id": thread_id}}

# Open checkpointer cleanly — handles pool creation & table creation automatically
with PostgresSaver.from_conn_string(DB_URL) as checkpointer:
    # 1. Run setup once to create 'checkpoints' tables if they don't exist
    checkpointer.setup()

    # 2. Compile graph with active checkpointer
    graph = create_travel_graph(checkpointer=checkpointer)

    # 3. First execution
    result = graph.invoke(
        {"messages": [("user", "I want to travel to New York tomorrow, i'm located in Lagos, just me (1 adult)")]},
        config=config
    )


    # 4. Handle HITL Interrupt if triggered
    if "__interrupt__" in result and result["__interrupt__"]:
        interrupt_info = result["__interrupt__"][0].value
        print("\n--- INTERRUPTED ---")
        answer = input(f"\n {interrupt_info.get("question")}: \n")

        # Resume with response
        resumed_result = graph.invoke(
            Command(resume=answer),
            config=config
        )
        print("\n--- RESUMED RUN ---")
        print(resumed_result)
    else:
        import json
        with open("testing_flight.json", "w") as f:
            json.dump(result, f)