#!/usr/bin/env python3
import json
import os
from datetime import date, timedelta
from uuid import uuid4

from openai import OpenAI, OpenAIError

# Load environment variables from .env if present
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.isfile(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

api_key = os.getenv("OPENAI_API_KEY", "")
is_groq = api_key.startswith("gsk_")

default_discovery = "openai/gpt-oss-20b" if is_groq else "gpt-4.1-mini"
default_booking = "openai/gpt-oss-120b" if is_groq else "gpt-4.1"

MODELS = {
    "discovery": os.getenv("DISCOVERY_MODEL", default_discovery),
    "booking": os.getenv("BOOKING_MODEL", default_booking),
}

_client = None

def get_client():
    global _client
    if _client is None:
        base_url = os.getenv("OPENAI_BASE_URL")
        if not base_url and os.getenv("OPENAI_API_KEY", "").startswith("gsk_"):
            base_url = "https://api.groq.com/openai/v1"
        _client = OpenAI(base_url=base_url) if base_url else OpenAI()
    return _client



# Fictional inventory for tomorrow, relative to the computer's local date.
show_date = (date.today() + timedelta(days=1)).isoformat()
SHOWS = {
    "S1": {
        "movie": "Journey to Saturn",
        "genre": "Science fiction",
        "date": show_date,
        "time": "18:30",
        "price_cents": 1400,
    },
    "S2": {
        "movie": "The Last Laugh",
        "genre": "Comedy",
        "date": show_date,
        "time": "19:00",
        "price_cents": 1200,
    },
    "S3": {
        "movie": "Midnight Mystery",
        "genre": "Thriller",
        "date": show_date,
        "time": "21:00",
        "price_cents": 1500,
    },
}

for show in SHOWS.values():
    show.update({
        "cinema": "Demo Cinema",
        "city": "New York",
        "timezone": "America/New_York",
        "currency": "USD",
        "available_seats": {
            f"{row}{number}"
            for row in "ABC"
            for number in range(1, 7)
        },
    })


def catalog():
    return [
        {
            "show_id": show_id,
            **{
                key: sorted(value) if isinstance(value, set) else value
                for key, value in show.items()
            },
        }
        for show_id, show in SHOWS.items()
    ]


def function_tool(name, description, properties=None):
    properties = properties or {}
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


LIST_SHOWS = function_tool(
    "list_shows",
    "Read all demo movies, showtimes, prices, and available seats.",
)

HANDOFF = function_tool(
    "handoff_to_booking",
    "Transfer to the booking specialist when the user wants tickets.",
)

PREPARE_BOOKING = function_tool(
    "prepare_booking",
    "Validate the selected show and seats and create an unconfirmed quote.",
    {
        "show_id": {"type": "string"},
        "seats": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
)

INSTRUCTIONS = """
You are a movie ticket assistant for a simulated cinema.
Use tools as the source of truth for inventory and prices.
Never invent movies, showtimes, seats, booking IDs, or successful actions.
All displayed showtimes use the cinema's timezone.

Discovery:
- Call list_shows to discover movies and make recommendations.
- Transfer to booking when the user wants to book tickets.

Booking:
- Read inventory before proposing a booking.
- Ask for missing details and clarify ambiguous show choices.
- Ask for specific seats, or permission to choose seats.
- Prepare a quote only after the user has requested booking.
- If seats are unavailable, explain and offer available alternatives.

The application handles confirmation separately.
Preparing a quote does not reserve seats or complete a booking.
Never claim payment was collected.
"""


class MovieAgent:
    def __init__(self):
        self.phase = "discovery"
        self.history = []
        self.pending = None
        self.bookings = {}

    def record_reply(self, text):
        self.history.append({"role": "assistant", "content": text})
        return text

    def prepare_booking(self, show_id, seats):
        if show_id not in SHOWS:
            return {"error": "Unknown show ID."}

        if (
            not isinstance(seats, list)
            or not seats
            or not all(isinstance(seat, str) for seat in seats)
        ):
            return {"error": "Select at least one valid seat."}

        seats = [seat.strip().upper() for seat in seats]
        if len(seats) != len(set(seats)):
            return {"error": "The same seat cannot be selected twice."}

        show = SHOWS[show_id]
        unavailable = set(seats) - show["available_seats"]
        if unavailable:
            return {
                "error": "Some seats do not exist or are unavailable.",
                "unavailable": sorted(unavailable),
                "available": sorted(show["available_seats"]),
            }

        self.pending = {
            "quote_id": uuid4().hex[:12],
            "show_id": show_id,
            "seats": sorted(seats),
            "total_cents": len(seats) * show["price_cents"],
        }
        return {"status": "awaiting_confirmation", **self.pending}

    def quote_text(self):
        quote = self.pending
        show = SHOWS[quote["show_id"]]
        return (
            f"Demo booking quote {quote['quote_id']}\n"
            f"{show['movie']} at {show['cinema']}, {show['city']}\n"
            f"{show['date']} at {show['time']} ({show['timezone']})\n"
            f"Seats: {', '.join(quote['seats'])}\n"
            f"Total: ${quote['total_cents'] / 100:.2f} USD "
            "(demo total; no extra fees)\n"
            "Seats are not reserved yet.\n"
            f"Type CONFIRM {quote['quote_id']} to book, or CANCEL.\n"
            "A new request replaces this quote."
        )

    def confirm(self, quote_id):
        # Repeated confirmation returns the existing booking.
        if quote_id in self.bookings:
            booking = self.bookings[quote_id]
            return f"Already booked. Demo booking ID: {booking['booking_id']}"

        if not self.pending or self.pending["quote_id"] != quote_id:
            return "No matching pending quote. Please request a new quote."

        quote = self.pending
        show = SHOWS[quote["show_id"]]

        # Recheck availability immediately before the simulated booking.
        if not set(quote["seats"]).issubset(show["available_seats"]):
            self.pending = None
            return "Those seats are no longer available. Select new seats."

        if quote["total_cents"] != len(quote["seats"]) * show["price_cents"]:
            self.pending = None
            return "The price changed. Please request a new quote."

        booking = {**quote, "booking_id": f"DEMO-{uuid4().hex[:12]}"}
        show["available_seats"].difference_update(quote["seats"])
        self.bookings[quote_id] = booking
        self.pending = None
        self.phase = "discovery"

        return (
            f"Demo booking confirmed: {booking['booking_id']}\n"
            f"{show['movie']} — {show['date']} {show['time']}\n"
            f"Seats: {', '.join(booking['seats'])}\n"
            f"Total: ${booking['total_cents'] / 100:.2f} USD\n"
            "No payment was collected."
        )

    def chat(self, text):
        self.history.append({"role": "user", "content": text})
        parts = text.strip().split()

        # Confirmation is handled by application code, outside the models.
        if parts and parts[0].upper() == "CONFIRM":
            reply = (
                self.confirm(parts[1])
                if len(parts) == 2
                else "Use CONFIRM followed by the quote ID."
            )
            return self.record_reply(reply)

        if text.strip().upper() == "CANCEL":
            self.pending = None
            return self.record_reply(
                "Pending quote cleared. Existing bookings are unchanged."
            )

        # Prevent an earlier quote from being confirmed after a new request.
        self.pending = None

        for _ in range(8):
            tools = [
                LIST_SHOWS,
                HANDOFF if self.phase == "discovery" else PREPARE_BOOKING,
            ]

            client = get_client()
            response = client.responses.create(
                model=MODELS[self.phase],
                instructions=INSTRUCTIONS + f"\nCurrent role: {self.phase}",
                input=self.history,
                tools=tools,
                parallel_tool_calls=False,
                store=False,
            )

            self.history.extend(response.output)
            calls = [
                item for item in response.output
                if item.type == "function_call"
            ]

            if not calls:
                return response.output_text or "Please rephrase your request."

            for call in calls:
                try:
                    arguments = json.loads(call.arguments)
                    if call.name == "list_shows":
                        result = {"shows": catalog()}
                    elif (
                        call.name == "handoff_to_booking"
                        and self.phase == "discovery"
                    ):
                        self.phase = "booking"
                        result = {"status": "Transferred to booking specialist."}
                    elif (
                        call.name == "prepare_booking"
                        and self.phase == "booking"
                    ):
                        result = self.prepare_booking(**arguments)
                    else:
                        result = {"error": "Tool is not available."}
                except (ValueError, TypeError):
                    result = {"error": "Invalid tool arguments. Try again."}

                self.history.append({
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result),
                })

            if self.pending:
                # Render transactional details directly from validated data.
                return self.record_reply(self.quote_text())

        return self.record_reply(
            "I couldn't finish that request. Please specify a show and seats."
        )


def main():
    if not os.getenv("OPENAI_API_KEY"):
        print("\n[!] OPENAI_API_KEY is not set.")
        print("Please set your OpenAI API key using one of the following methods:")
        print("  1. In terminal: export OPENAI_API_KEY=\"your-api-key\"")
        print("  2. In .env file: create a .env file with OPENAI_API_KEY=your-api-key\n")
        return

    agent = MovieAgent()
    print("Movie booking demo. Type 'exit' to quit.")
    print("Try: What movies are available tomorrow?")

    while True:
        try:
            text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if text.lower() in {"exit", "quit"}:
            break
        if not text:
            continue

        # Restore conversation state if an API request fails mid-turn.
        previous_history = list(agent.history)
        previous_phase = agent.phase

        try:
            print(f"\nAgent: {agent.chat(text)}")
        except OpenAIError as exc:
            agent.history = previous_history
            agent.phase = previous_phase
            agent.pending = None
            print(
                f"\nAPI request failed ({type(exc).__name__}). "
                "Check your API key, model access, and connection, then retry."
            )


if __name__ == "__main__":
    main()

