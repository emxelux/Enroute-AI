# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AI Travel Agent (TripMate)** - A travel-only conversational agent built with LangGraph. Users sign in, describe a trip in natural language, and a supervisor agent delegates to specialised flight and hotel sub-agents. When enough information has been gathered, HITL allows user to confirm bookings, and then the user is taken to payment.

**Key constraint**: It is deliberately *not* a general-purpose chatbot - non-travel queries are turned away.

## Architecture

```
User → Authentication (JWT) → Scope Check (travel only?) → Supervisor Agent
                                                          ↓
                                              Flight Sub-Agent ←→ Duffel API
                                              Hotel Sub-Agent ←→ SerpAPI (Google Hotels)
                                                          ↓
                                                    Payment
```

### Layers
| Layer | Responsibility |
|-------|---------------|
| Authentication | Account creation, sign-in, JWT issuance |
| PostgreSQL | Persistent storage of user accounts & conversation state |
| Travel Agent | Scope check, orchestration, flight/hotel search & booking |
| Payment | Handoff once supervisor has all information |
| External services | Duffel (flights), SerpAPI (hotels), payment provider |

## Tech Stack

| Concern | Technology |
|---------|------------|
| Language | Python 3.13 |
| Agent Orchestration | LangGraph 1.2.2, LangChain 1.3.2 |
| LLM | Groq (openai/gpt-oss-120b) |
| Flights API | Duffel (custom client in `Duffel/duffelpy.py`) |
| Hotels API | SerpAPI (Google Hotels engine) |
| Web Search | Tavily |
| Database | PostgreSQL (Neon) with psycopg |
| Auth | JWT (python-jose/PyJWT), passlib/bcrypt |
| Web Framework | FastAPI 0.136.3, Uvicorn 0.48.0 |
| Env Management | python-dotenv |

## Key Files

```
.
├── main.py                    # FastAPI app with /chat, /health endpoints
├── state.py                   # TravelState TypedDict for LangGraph
├── utils.py                   # City coordinate lookup via Nominatim
├── pyproject.toml             # Project config, dependencies, uv build
├── requirements.txt           # Same deps as pyproject.toml
├── .env                       # API keys (NEVER commit real keys)
├── README.md                  # System design documentation
├── llm/
│   ├── flight_llm.py          # Flight LLM with search_flight tool bound
│   └── hotel_llm.py           # Hotel LLM with search_hotels tool bound
├── tools/
│   ├── flight_tool.py         # search_flight tool using Duffel API
│   ├── hotel_tool.py          # search_hotels tool using SerpAPI (@tool decorated)
│   ├── tavily_tool.py         # tavily_search function for web search
│   └── currency_tool.py       # Currency conversion tools (Frankfurter API)
├── agents/
│   ├── __init__.py            # Package exports
│   ├── supervisor.py          # Supervisor agent - classifies & routes
│   ├── flight_agent.py        # Flight sub-agent with tools
│   ├── hotel_agent.py         # Hotel sub-agent with tools
│   ├── payment_agent.py       # Payment agent (placeholder)
│   └── graph.py               # LangGraph workflow wiring
├── Duffel/
│   └── duffelpy.py            # Custom Duffel API v2 client
└── src/ai_travel/             # Package root (minimal)
```

## Common Commands

### Development
```bash
# Install dependencies (using uv)
uv sync

# Run the FastAPI server
uv run uvicorn main:app --reload

# Test the graph directly
uv run python -c "from agents.graph import run_travel_agent; print(run_travel_agent('I want to fly from Lagos to Abuja'))"

# Run a single test (pytest not yet configured)
# uv run pytest <test_file>::<test_function> -v
```

### Linting/Type Checking (not yet configured)
```bash
# uv run ruff check .
# uv run mypy .
```

## Environment Variables

Required in `.env`:
- `DATABASE_URL` - PostgreSQL connection string
- `GROQ_API_KEY` - Groq API key for LLM
- `DUFFEL_ACCESS_TOKEN` - Duffel API token for flights
- `SERPAPI_KEY` - SerpAPI key for hotel search
- `TAVILY_API_KEY` - Tavily API key for web search
- `AVIATIONSTACK_API_KEY` - AviationStack API key
- `HOTELBEDS_API_KEY` - HotelBeds API key
- `GEMINI_API_KEY` - Google Gemini API key
- `LANGSMITH_*` - LangSmith tracing configuration
- `SECRET` - JWT secret key

## Agent Implementation Status

### ✅ Completed
1. **Duffel client** (`Duffel/duffelpy.py`) - Complete custom client for Duffel API v2
2. **Flight tool** (`tools/flight_tool.py`) - `search_flight` tool using Duffel
3. **Hotel tool** (`tools/hotel_tool.py`) - `search_hotels` tool using SerpAPI
4. **Tavily tool** (`tools/tavily_tool.py`) - `tavily_search` function for web search
5. **Currency tool** (`tools/currency_tool.py`) - Conversion + detection from text
6. **Flight LLM** (`llm/flight_llm.py`) - Groq LLM with `search_flight` bound
7. **Hotel LLM** (`llm/hotel_llm.py`) - Groq LLM with `search_hotels` bound
8. **State** (`state.py`) - Complete `TravelState` with all trip fields
9. **Supervisor agent** (`agents/supervisor.py`) - Classifies travel vs non-travel, routes to sub-agents
10. **Flight agent** (`agents/flight_agent.py`) - Searches flights, presents options, handles selection
11. **Hotel agent** (`agents/hotel_agent.py`) - Searches hotels, presents options, handles selection
12. **Payment agent** (`agents/payment_agent.py`) - Placeholder for payment integration
13. **LangGraph workflow** (`agents/graph.py`) - Wires all agents with PostgreSQL/Memory checkpointer
14. **FastAPI app** (`main.py`) - `/chat`, `/health`, `/threads/{id}/state` endpoints

### ⏳ Remaining Work
1. **Authentication layer** - JWT validation, user management, PostgreSQL users table
2. **Payment integration** - Duffel Payments, Stripe, or other provider
3. **Structured output** - Use Pydantic models for agent responses instead of text parsing
4. **Error handling** - Retry logic, graceful degradation for API failures
5. **Tests** - Unit tests for tools, integration tests for graph
6. **Booking confirmation** - Explicit user confirmation before any booking call

## Development Notes

- The project uses **uv** for package management (see `pyproject.toml` with `uv_build`)
- Python version is **3.13** (see `.python-version`)
- LangGraph checkpointer uses PostgreSQL (`langgraph-checkpoint-postgres`) in production, `MemorySaver` for dev
- The system design in `README.md` is the source of truth for architecture decisions
- Open questions from README: verified field, JWT details, out-of-scope behavior, supervisor loop criteria, booking safety, state management, payment provider

## Running the Application

```bash
# Start the server
uv run uvicorn main:app --reload

# Test chat endpoint
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-token" \
  -d '{"message": "I want to fly from Lagos to Abuja next Friday", "user_country": "NG"}'
```

## Graph Flow

```
START → supervisor → flight_agent ↔ flight_tools
                ↘ hotel_agent ↔ hotel_tools
                ↘ payment_agent → END
```

The supervisor uses `Command` to route dynamically based on trip state.