from typing import Optional, Literal, Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
)
from langgraph.types import Command, interrupt
from typing_extensions import TypedDict
from tools.tavily_tool import tavily_search
from state import TravelState
from dotenv import load_dotenv
from langchain.agents import create_agent

load_dotenv()

base_llm = init_chat_model(
    "groq:qwen/qwen3.8-27b"
    # "google_genai:gemini-2.5-flash"
)


with open(
    "prompts/travel_classifier.md",
    "r",
    encoding="utf-8",
) as f:
    TRAVEL_CLASSIFIER_PROMPT = f.read()

with open(
    "prompts/travel_extractor.md",
    "r",
    encoding="utf-8",
) as f:
    TRAVEL_EXTRACTOR_PROMPT = f.read()

with open(
    "prompts/supervisor_prompt.md",
    "r",
    encoding="utf-8",
) as f:
    SUPERVISOR_PROMPT = f.read()

class ClassigyQuery(TypedDict):
    is_travel: Annotated[bool, ..., "Classify whether the user's message is travel-related."]


class NeedHotel(TypedDict):
    MISSING: Annotated[bool, ..., "Whether it's a missing information"]
    accomodation_needed: Annotated[bool, ..., "Whether hotel is actually needed or not"]

class TravelInfo(TypedDict):
    needs_flight: Annotated[bool, ..., "Whether the user needs a flight."]
    needs_hotel: NeedHotel
    flight_origin: Annotated[Optional[str], ..., "The IATA code of the origin airport"]
    flight_destination: Annotated[Optional[str], ..., "The IATA code of the destination airport"]
    hotel_check_in: Annotated[Optional[str], ..., "The check-in date of the hotel. Format: YYYY-MM-DD"]
    hotel_check_out: Annotated[Optional[str], ..., "The check-out date of the hotel. Format: YYYY-MM-DD"]
    missing_information: Annotated[Optional[str], ..., "The missing information required to complete the travel request."]
    flight_departure_date: Annotated[Optional[str], ..., "The departure date of the flight. Format: YYYY-MM-DD"]
    flight_return_date: Annotated[Optional[str], ..., "The return date of the flight. Format: YYYY-MM-DD"]
    hotel_location: Annotated[Optional[str], ..., "The location of the hotel."]



def classify_travel_query(query:str) -> bool:
    classifier = base_llm.with_structured_output(ClassifyQuery)
    messages = [
        SystemMessage(content=TRAVEL_CLASSIFIER_PROMPT),
        HumanMessage(content=query),
    ]
    response = classifier.invoke(messages)
    return response["is_travel"]


def get_today_date() -> str:
    """Return today's date in YYYY-MM-DD format."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d")

def extract_travel_information(messages: list):
    extractor = create_agent(
        model=llm,
        tools=[get_today_date, tavily_search],
        response_format=TravelInfo,
        system_prompt=TRAVEL_EXTRACTOR_PROMPT
    )
    resp = extractor.invoke({"messages": messages})
    return resp["structured_response"]



def supervisor_node(state: TravelState):
    is_travel = classify_travel_query(state["messages"][-1]["content"])

    if not is_travel:
        ai_msg = AIMessage(content = "Sorry!, I'm a travel only assistant, please ask travel related requests.")
        return {
            "messages": [
                state["messages"][-1],
                ai_msg
            ]
        }

    try:
        travel_info = extract_travel_information(state["messages"])

        needs_flight = travel_info["needs_flight"]
        needs_hotel = travel_info["needs_hotel"]
        
        if ("MISSING" in list(travel_info.values())) or ("MISSING" in list(travel_info["needs_hotel"].values())):
            missing_info = travel_info["missing_information"]

            # HITL: pause the workflow and ask the user for the missing info.
            interrupt({
                "type": "missing_information",
                "question": missing_info,
            })

            ai_msg = AIMessage(content=missing_info)
            return {
                "messages": state["messages"] + [ai_msg],
            }
        if needs_hotel["needs_accomodation"]:
            return {
                "messages": state["messages"] + [AIMessage(content="Travel information extracted successfully.")],
                "flight_origin": travel_info["flight_origin"],
                "flight_destination": travel_info["flight_destination"],
                "flight_departure_date": travel_info["flight_departure_date"],
                "flight_return_date": travel_info["flight_return_date"],
                "hotel_location": travel_info["hotel_location"],
                "hotel_check_in": travel_info["hotel_check_in"],
                "hotel_check_out": travel_info["hotel_check_out"],
            }

    except Exception as e:
        pass








# class ClassifyQuery(TypedDict):
#     """
#     Result returned by the travel classifier.
#     """

#     is_travel: bool


# class TravelExtract(TypedDict, total=False):
#     needs_flight: bool
#     needs_hotel: bool

#     origin_country: str

#     flight_origin: str
#     flight_destination: str
#     flight_departure_date: str
#     flight_return_date: str
#     flight_cabin_class: str

#     adults: int
#     children: int
#     infants: int

#     hotel_location: str
#     hotel_check_in: str
#     hotel_check_out: str
#     hotel_guests: int


# classifier_llm = base_llm.with_structured_output(
#     ClassifyQuery, method="json_mode"
# )


# # JSON mode avoids Groq's tool-call argument validation rejecting partial
# # TravelExtract objects before LangChain can parse them.
# travel_extractor_llm = base_llm.with_structured_output(
#     TravelExtract,
#     method="json_mode",
# )


# def update_user_query(
#     previous_query: str,
#     clarification: str,
# ) -> str:
#     """Fold a HITL answer into the complete query for extraction."""

#     response = base_llm.invoke([
#         SystemMessage(
#             content=(
#                 """Combine the travel request and the user's clarification into 
#                 one concise, standalone travel request. Preserve every stated
#                 fact; do not infer missing details. Return only the combined request."""
#             )
#         ),
#         HumanMessage(
#             content=(
#                 f"Existing request:\n{previous_query}\n\n"
#                 f"User's clarification:\n{clarification}"
#             )
#         ),
#     ])

#     combined = response.content
#     if not isinstance(combined, str):
#         combined = str(combined)
#     if combined:
#         print(f"\n--- CONSOLIDATED QUERY ---\n{combined}\n")
#     return (
#         f"Consolidated request: {combined}"
#     )

# def get_latest_human_message(
#     messages: list,
# ) -> Optional[str]:
   
#     for message in reversed(messages):

#         if isinstance(message, HumanMessage):

#             content = message.content

#             if isinstance(content, str):
#                 return content

#     return None


# def get_trip_context(
#     state: TravelState,
# ) -> dict[str, Any]:
#     """
#     Extract the relevant existing trip information from state.

#     This context is passed to the extraction LLM so it can
#     understand clarification messages such as:

#         User:
#         "I want to fly Lagos to London next Tuesday."

#         Supervisor:
#         "How many passengers?"

#         User:
#         "Two adults."

#     The latest message alone does not contain enough context.

#     The existing TravelState does.
#     """

#     return {
#         "needs_flight": state.get(
#             "needs_flight",
#             False,
#         ),

#         "needs_hotel": state.get(
#             "needs_hotel",
#             False,
#         ),

#         "origin_country": state.get(
#             "user_country"
#         ),

#         "flight": {
#             "origin": state.get(
#                 "flight_origin"
#             ),

#             "destination": state.get(
#                 "flight_destination"
#             ),

#             "departure_date": state.get(
#                 "flight_departure_date"
#             ),

#             "return_date": state.get(
#                 "flight_return_date"
#             ),

#             "cabin_class": state.get(
#                 "flight_cabin_class"
#             ),

#             "passengers": state.get(
#                 "flight_passengers"
#             ),
#         },

#         "hotel": {
#             "location": state.get(
#                 "hotel_location"
#             ),

#             "check_in": state.get(
#                 "hotel_check_in"
#             ),

#             "check_out": state.get(
#                 "hotel_check_out"
#             ),

#             "guests": state.get(
#                 "hotel_guests"
#             ),
#         },
#     }




# def classify_travel_query(
#     query: str,
# ) -> bool:
#     """
#     Determine whether the latest user message is
#     travel-related.
#     """

#     messages = [
#         SystemMessage(
#             content=TRAVEL_CLASSIFIER_PROMPT
#         ),
#         HumanMessage(
#             content=query
#         ),
#     ]

#     response = classifier_llm.invoke(
#         messages
#     )

#     return response["is_travel"]


# def extract_travel_information(
#     user_message: str,
#     state: TravelState,
#     is_consolidated: bool = False,
# ) -> TravelUpdate:
#     """
#     Extract NEW information from the user's message
#     while considering the existing TravelState.

#     The LLM is explicitly instructed to return only information
#     that is present in the latest message.

#     Existing information is NOT reconstructed by the LLM.
#     """

#     current_trip = get_trip_context(
#         state
#     )

#     if is_consolidated:
#         query_scope_instruction = (
#             "The message is the complete consolidated request, including "
#             "the original request and HITL clarifications. Return every "
#             "travel fact explicitly stated in it, even if it is already "
#             "present in the state."
#         )
#     else:
#         query_scope_instruction = (
#             "Extract only information added, changed, or clarified in the "
#             "latest user message."
#         )

#     extraction_prompt = f"""
# {SUPERVISOR_PROMPT}

# --------------------------------------------------
# EXISTING TRAVEL STATE
# --------------------------------------------------

# {current_trip}

# --------------------------------------------------
# LATEST USER MESSAGE
# --------------------------------------------------

# {user_message}

# --------------------------------------------------
# IMPORTANT
# --------------------------------------------------

# The existing travel state above is already known.

# {query_scope_instruction}

# Do NOT erase existing information.

# Return null for fields that the user did not provide
# or change in this latest message.

# Return only a JSON object. Use these exact field names when
# the information is available, and omit fields that are not
# available: needs_flight, needs_hotel, origin_country,
# flight_origin, flight_destination, flight_departure_date,
# flight_return_date, flight_cabin_class, adults, children,
# infants, hotel_location, hotel_check_in, hotel_check_out,
# hotel_guests. Use null for unknown values when included.

# Examples:

# Existing state:

# flight_origin = "Lagos"
# flight_destination = "London"
# flight_departure_date = "next Tuesday"

# Latest user message:

# "Two adults."

# Return:

# adults = 2

# Do NOT return:

# flight_origin = null
# flight_destination = null
# flight_departure_date = null

# Those fields were not changed.

# Another example:

# Existing state:

# flight_cabin_class = "economy"

# Latest user message:

# "Actually, make it business class."

# Return:

# flight_cabin_class = "business"

# Another example:

# Existing state:

# flight_origin = "Lagos"
# flight_destination = "London"

# Latest user message:

# "Actually, Paris instead."

# Return:

# flight_destination = "Paris"

# Do not invent information that is not present.
# """

#     messages = [
#         SystemMessage(
#             content=extraction_prompt
#         ),
#         HumanMessage(
#             content=user_message
#         ),
#     ]

#     response = travel_extractor_llm.invoke(
#         messages
#     )

#     return response


# # ============================================================
# # State merging
# # ============================================================

# def build_state_update(
#     extraction: TravelUpdate,
#     state: TravelState,
# ) -> dict:
#     """
#     Convert the LLM extraction into a LangGraph state update.

#     IMPORTANT:

#     This function merges information with the existing state.

#     The LLM does NOT control the entire state.

#     Only values explicitly provided by the user are written.
#     """

#     update: dict[str, Any] = {}

#     # --------------------------------------------------------
#     # Intent
#     # --------------------------------------------------------

#     if extraction.get("needs_flight") is not None:

#         update["needs_flight"] = (
#             extraction["needs_flight"]
#         )

#     if extraction.get("needs_hotel") is not None:

#         update["needs_hotel"] = (
#             extraction["needs_hotel"]
#         )

#     # --------------------------------------------------------
#     # User country
#     # --------------------------------------------------------

#     if extraction.get("origin_country"):

#         update["user_country"] = (
#             extraction["origin_country"]
#         )

#     # --------------------------------------------------------
#     # Flight
#     # --------------------------------------------------------

#     if extraction.get("flight_origin"):

#         update["flight_origin"] = (
#             extraction["flight_origin"]
#         )

#     if extraction.get("flight_destination"):

#         update["flight_destination"] = (
#             extraction["flight_destination"]
#         )

#     if extraction.get("flight_departure_date"):

#         update["flight_departure_date"] = (
#             extraction["flight_departure_date"]
#         )

#     if extraction.get("flight_return_date"):

#         update["flight_return_date"] = (
#             extraction["flight_return_date"]
#         )

#     if extraction.get("flight_cabin_class"):

#         update["flight_cabin_class"] = (
#             extraction["flight_cabin_class"]
#         )

#     # --------------------------------------------------------
#     # Passengers
#     # --------------------------------------------------------

#     existing_passengers = (
#         state.get("flight_passengers")
#         or {}
#     )

#     passengers = dict(
#         existing_passengers
#     )

#     if extraction.get("adults") is not None:

#         passengers["adults"] = (
#             extraction["adults"]
#         )

#     if extraction.get("children") is not None:

#         passengers["children"] = (
#             extraction["children"]
#         )

#     if extraction.get("infants") is not None:

#         passengers["infants"] = (
#             extraction["infants"]
#         )

#     if passengers:

#         update["flight_passengers"] = (
#             passengers
#         )

#     # --------------------------------------------------------
#     # Hotel
#     # --------------------------------------------------------

#     if extraction.get("hotel_location"):

#         update["hotel_location"] = (
#             extraction["hotel_location"]
#         )

#     if extraction.get("hotel_check_in"):

#         update["hotel_check_in"] = (
#             extraction["hotel_check_in"]
#         )

#     if extraction.get("hotel_check_out"):

#         update["hotel_check_out"] = (
#             extraction["hotel_check_out"]
#         )

#     if extraction.get("hotel_guests") is not None:

#         update["hotel_guests"] = (
#             extraction["hotel_guests"]
#         )

#     return update


# # ============================================================
# # Missing information
# # ============================================================

# def get_missing_information(
#     state: TravelState,
# ) -> list[str]:
#     """
#     Determine whether enough information exists for the
#     domain agents to execute.

#     This function does NOT call an LLM.
#     """

#     missing: list[str] = []

    
#     if state.get("needs_flight"):

#         if not state.get("flight_origin"):

#             missing.append(
#                 "flight departure location"
#             )

#         if not state.get("flight_destination"):

#             missing.append(
#                 "flight destination"
#             )

#         if not state.get("flight_departure_date"):

#             missing.append(
#                 "flight departure date"
#             )

#         passengers = state.get(
#             "flight_passengers"
#         )

#         if not passengers:

#             missing.append(
#                 "number of passengers"
#             )

#     # ========================================================
#     # Hotel
#     # ========================================================

#     if state.get("needs_hotel"):

#         if not state.get("hotel_location"):

#             missing.append(
#                 "hotel location"
#             )

#         if not state.get("hotel_check_in"):

#             missing.append(
#                 "hotel check-in date"
#             )

#         if not state.get("hotel_check_out"):

#             missing.append(
#                 "hotel check-out date"
#             )

#         if not state.get("hotel_guests"):

#             missing.append(
#                 "number of hotel guests"
#             )

#     return missing


# # ============================================================
# # HITL
# # ============================================================

# def request_missing_information(
#     missing: list[str],
# ):
#     """
#     Pause the graph and ask the user for missing information.

#     IMPORTANT:

#     interrupt() pauses the graph.

#     When the graph resumes using:

#         Command(resume=user_answer)

#     execution continues immediately after interrupt().

#     Therefore, the caller should process the returned answer
#     rather than routing back through the supervisor unnecessarily.
#     """

#     question = (
#         "I need a few more details before I can continue:\n\n"
#         + "\n".join(
#             f"- {item}"
#             for item in missing
#         )
#         + "\n\nPlease provide the missing information."
#     )

#     response = interrupt(
#         {
#             "type": "missing_travel_information",
#             "missing": missing,
#             "question": question,
#         }
#     )

#     return response


# # ============================================================
# # Routing
# # ============================================================

# def determine_next_agent(
#     state: TravelState,
# ) -> Literal[
#     "flight_agent",
#     "hotel_agent",
#     "payment_agent",
#     "__end__",
# ]:
#     """
#     Decide which agent should execute next.

#     This function only looks at state.

#     It does not call an LLM.
#     """

#     needs_flight = state.get(
#         "needs_flight",
#         False,
#     )

#     needs_hotel = state.get(
#         "needs_hotel",
#         False,
#     )

#     flight_done = (
#         not needs_flight
#         or state.get("flight_selected")
#         is not None
#     )

#     hotel_done = (
#         not needs_hotel
#         or state.get("hotel_selected")
#         is not None
#     )

#     # --------------------------------------------------------
#     # Both domains complete
#     # --------------------------------------------------------

#     if flight_done and hotel_done:

#         if needs_flight or needs_hotel:

#             return "payment_agent"

#         return "__end__"

#     # --------------------------------------------------------
#     # Flight still needs work
#     # --------------------------------------------------------

#     if (
#         needs_flight
#         and not state.get("flight_selected")
#     ):

#         return "flight_agent"

#     # --------------------------------------------------------
#     # Hotel still needs work
#     # --------------------------------------------------------

#     if (
#         needs_hotel
#         and not state.get("hotel_selected")
#     ):

#         return "hotel_agent"

#     return "__end__"


# # ============================================================
# # Supervisor node
# # ============================================================

# def supervisor_node(
#     state: TravelState,
# ):
#     """
#     Main supervisor node.

#     Workflow:

#         latest message
#               ↓
#         classify travel
#               ↓
#         extract NEW information
#               ↓
#         merge into state
#               ↓
#         validate
#               ↓
#         HITL if necessary
#     """
#             #   ↓
#         # route to domain agent

#     messages = state.get(
#         "messages",
#         []
#     )

#     if not messages:

#         return Command(
#             goto="__end__",
#             update={
#                 "error": "No user message found."
#             },
#         )

#     # ========================================================
#     # 1. Get latest user message
#     # ========================================================

#     latest_user_message = get_latest_human_message(
#         messages
#     )

#     if not latest_user_message:

#         return Command(
#             goto="__end__",
#             update={
#                 "error": "No user message found."
#             },
#         )

#     saved_user_query = state.get("user_query")
#     is_consolidated_query = bool(
#         saved_user_query and latest_user_message in saved_user_query
#     )
#     if is_consolidated_query:
#         user_query = saved_user_query
#     else:
#         user_query = latest_user_message

#     # ========================================================
#     # 2. Classify the latest message
#     # ========================================================

#     is_travel = classify_travel_query(
#         user_query
#     )

#     if not is_travel:

#         return Command(
#             goto="__end__",
#             update={
#                 "messages": [
#                     AIMessage(
#                         content=(
#                             "I'm a travel-only assistant. "
#                             "I can help with flights, hotels, "
#                             "and trip planning."
#                         )
#                     )
#                 ]
#             },
#         )

#     # ========================================================
#     # 3. Extract information using existing state as context
#     # ========================================================

#     extraction = extract_travel_information(
#         user_message=user_query,
#         state=state,
#         is_consolidated=is_consolidated_query,
#     )

#     # ========================================================
#     # 4. Merge extracted information with existing state
#     # ========================================================

#     state_update = build_state_update(
#         extraction=extraction,
#         state=state,
#     )

#     # ========================================================
#     # 5. Build temporary validation state
#     # ========================================================

#     validation_state = {
#         **state,
#         **state_update,
#     }

#     # ========================================================
#     # 6. Validate required information
#     # ========================================================

#     missing = get_missing_information(
#         validation_state
#     )

#     # ========================================================
#     # 7. Missing information → HITL
#     # ========================================================

#     if missing:

#         user_response = request_missing_information(
#             missing
#         )


#         if user_response is None:

#             return Command(
#                 goto="__end__",
#                 update={
#                     **state_update,
#                     "error": (
#                         "No response received for "
#                         "missing travel information."
#                     ),
#                 },
#             )

#         clarification = str(
#             user_response
#         )

#         user_query = update_user_query(
#             previous_query=user_query,
#             clarification=clarification,
#         )

#         state_update["user_query"] = user_query

#         # ----------------------------------------------------
#         # Extract the clarification.
#         # ----------------------------------------------------

#         clarification_extraction = (
#             extract_travel_information(
#                 user_message=user_query,
#                 state=validation_state,
#                 is_consolidated=True,
#             )
#         )

#         # ----------------------------------------------------
#         # Merge clarification with the already-updated state.
#         # ----------------------------------------------------

#         clarification_update = (
#             build_state_update(
#                 extraction=clarification_extraction,
#                 state=validation_state,
#             )
#         )

#         # ----------------------------------------------------
#         # Combine both updates.
#         # ----------------------------------------------------

#         final_update = {
#             **state_update,
#             **clarification_update,
#         }

#         final_validation_state = {
#             **state,
#             **final_update,
#         }

#         # ----------------------------------------------------
#         # Validate again.
#         # ----------------------------------------------------

#         still_missing = (
#             get_missing_information(
#                 final_validation_state
#             )
#         )

#         # ----------------------------------------------------
#         # More information is still required.
#         #
#         # Return to supervisor with the updated state.
#         # The next invocation can ask another HITL question.
#         # ----------------------------------------------------

#         if still_missing:

#             return Command(
#                 goto="supervisor",
#                 update={
#                     **final_update,
#                 },
#             )

#         # ----------------------------------------------------
#         # Everything required is now available.
#         # ----------------------------------------------------

#         next_agent = determine_next_agent(
#             final_validation_state
#         )

#         final_update["current_agent"] = (
#             next_agent
#         )
#         return final_update
#         # return Command(
#         #     goto=next_agent,
#         #     update=final_update,
#         # )

#     # ========================================================
#     # 8. Everything required already exists
#     # ========================================================

#     next_agent = determine_next_agent(
#         validation_state
#     )

#     state_update["user_query"] = user_query
#     state_update["current_agent"] = (
#         next_agent
#     )


#     return Command(
#         goto=next_agent,
#         update=state_update,
#     )