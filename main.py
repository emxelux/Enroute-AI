"""
FastAPI application for AI Travel Agent (TripMate).
"""
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, AIMessage

from agents.graph import create_travel_graph, create_postgres_checkpointer
from state import TravelState


# Global graph instance
travel_graph = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - initialize graph on startup."""
    global travel_graph
    try:
        # Try PostgreSQL checkpointer for production
        travel_graph = create_travel_graph(create_postgres_checkpointer())
        print("✅ Travel agent initialized with PostgreSQL checkpointer")
    except Exception as e:
        print(f"⚠️ PostgreSQL checkpointer failed, using memory: {e}")
        travel_graph = create_travel_graph()  # Uses MemorySaver
    yield
    # Cleanup on shutdown
    print("Shutting down...")


app = FastAPI(
    title="TripMate AI Travel Agent",
    description="Travel-only conversational agent for flights and hotels",
    version="0.1.0",
    lifespan=lifespan,
)


# Request/Response models
class ChatRequest(BaseModel):
    message: str = Field(..., description="User's message")
    thread_id: str = Field(default="default", description="Conversation thread ID")
    user_country: str = Field(default="US", description="User's country for currency")


class ChatResponse(BaseModel):
    response: str
    thread_id: str
    current_agent: Optional[str] = None
    trip_complete: bool = False
    flight_booked: bool = False
    hotel_booked: bool = False


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "0.1.0"


# Dependency for user authentication (placeholder)
async def get_current_user(authorization: Optional[str] = Header(None)):
    """
    Extract user from JWT token.
    Placeholder - implement actual JWT validation.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    # TODO: Validate JWT and extract user_id
    # For now, return a dummy user_id
    return "user_123"


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse()


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user_id: str = Depends(get_current_user),
):
    """
    Main chat endpoint - process user message through travel agent.
    """
    if not travel_graph:
        raise HTTPException(status_code=503, detail="Travel agent not initialized")

    try:
        # Prepare initial state
        initial_state = {
            "messages": [HumanMessage(content=request.message)],
            "user_id": user_id,
            "user_country": request.user_country,
        }

        config = {"configurable": {"thread_id": request.thread_id}}

        # Invoke graph
        result = travel_graph.invoke(initial_state, config=config)

        # Extract last AI message
        messages = result.get("messages", [])
        last_ai_msg = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                last_ai_msg = msg.content
                break

        return ChatResponse(
            response=last_ai_msg or "I'm processing your request...",
            thread_id=request.thread_id,
            current_agent=result.get("current_agent"),
            trip_complete=result.get("trip_complete", False),
            flight_booked=result.get("flight_selected") is not None,
            hotel_booked=result.get("hotel_selected") is not None,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")


@app.get("/threads/{thread_id}/state")
async def get_thread_state(thread_id: str, user_id: str = Depends(get_current_user)):
    """Get current state of a conversation thread."""
    if not travel_graph:
        raise HTTPException(status_code=503, detail="Travel agent not initialized")

    config = {"configurable": {"thread_id": thread_id}}
    state = travel_graph.get_state(config)

    if not state:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Return relevant state (exclude full message history for brevity)
    return {
        "thread_id": thread_id,
        "current_agent": state.values.get("current_agent"),
        "trip_complete": state.values.get("trip_complete"),
        "flight_booked": state.values.get("flight_selected") is not None,
        "hotel_booked": state.values.get("hotel_selected") is not None,
        "trip_details": state.values.get("trip_details"),
    }


@app.delete("/threads/{thread_id}")
async def clear_thread(thread_id: str, user_id: str = Depends(get_current_user)):
    """Clear a conversation thread."""
    if not travel_graph:
        raise HTTPException(status_code=503, detail="Travel agent not initialized")

    # Note: LangGraph doesn't have built-in thread deletion
    # This would require custom checkpointer method
    return {"message": "Thread clearing not yet implemented"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)