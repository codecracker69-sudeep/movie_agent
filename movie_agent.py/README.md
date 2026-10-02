# Multi-Model Movie Ticket Booking Agent

A multi-model movie ticket booking prototype in Python that coordinates distinct models for **movie discovery** and **ticket booking**, complete with dynamic seat availability checks, price calculations, simulated handoffs, and deterministic booking confirmation.

## Architecture Flow

```text
User → Discovery Model (e.g. gpt-4.1-mini)
          ↓ (handoff_to_booking)
       Booking Model (e.g. gpt-4.1)
          ↓ (prepare_booking)
       Seat & Price Validation
          ↓
       User Confirms Quote ("CONFIRM <quote_id>")
          ↓
       Demo Booking Finalized
```

### Key Highlights
- **Multi-Model Orchestration**: Leverages `DISCOVERY_MODEL` (`gpt-4.1-mini` by default) for natural language discovery and recommendations, and transfers to `BOOKING_MODEL` (`gpt-4.1` by default) when ready to book.
- **Function Calling with Responses API**: Models invoke strictly typed tools (`list_shows`, `handoff_to_booking`, `prepare_booking`).
- **Deterministic Transaction Isolation**: Seat validation, unconfirmed quotes, and final booking confirmations are executed deterministically by application code—preventing hallucinated reservations or fake bookings.
- **Simulated Inventory**: Tracks real-time seat availability across rows A–C (seats 1–6) per showtime. No payment is collected.

---

## Getting Started

### 1. Prerequisites & Virtual Environment

Python 3.10+ is recommended.

```bash
# Optional: Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies (use python3 -m pip if pip is not in PATH)
python3 -m pip install -r requirements.txt
```

### 2. Configure Environment Variables

Export your OpenAI API key and optionally override the models:

```bash
# macOS / Linux
export OPENAI_API_KEY="your-api-key"
export DISCOVERY_MODEL="gpt-4.1-mini"  # or gpt-4o-mini
export BOOKING_MODEL="gpt-4.1"         # or gpt-4o

# Windows PowerShell
# $env:OPENAI_API_KEY="your-api-key"
# $env:DISCOVERY_MODEL="gpt-4.1-mini"
# $env:BOOKING_MODEL="gpt-4.1"
```

You can copy [.env.example](file:///Users/sudeep/movie_agent.py/.env.example) to `.env` if using a dotenv loader.

---

## Running the Agent

Run the interactive CLI:

```bash
python movie_agent.py
```

### Example Interaction Flow

1. **Discovery**:
   ```text
   You: What movies are playing tomorrow?
   Agent: We have 3 shows tomorrow at Demo Cinema:
          1. "Journey to Saturn" (Sci-Fi) at 18:30 ($14.00)
          2. "The Last Laugh" (Comedy) at 19:00 ($12.00)
          3. "Midnight Mystery" (Thriller) at 21:00 ($15.00)
   ```

2. **Booking Handoff & Seat Selection**:
   ```text
   You: I'd like to book 2 tickets for Journey to Saturn in seats A1 and A2.
   Agent: Demo booking quote a1b2c3d4e5f6
          Journey to Saturn at Demo Cinema, New York
          2026-10-03 at 18:30 (America/New_York)
          Seats: A1, A2
          Total: $28.00 USD (demo total; no extra fees)
          Seats are not reserved yet.
          Type CONFIRM a1b2c3d4e5f6 to book, or CANCEL.
   ```

3. **Confirmation**:
   ```text
   You: CONFIRM a1b2c3d4e5f6
   Agent: Demo booking confirmed: DEMO-9876543210ab
          Journey to Saturn — 2026-10-03 18:30
          Seats: A1, A2
          Total: $28.00 USD
          No payment was collected.
   ```

4. **Canceling or Modifying**:
   - Type `CANCEL` to clear any pending quote.
   - Any new search/request automatically replaces an unconfirmed quote.
   - Type `exit` or `quit` to exit the application.
