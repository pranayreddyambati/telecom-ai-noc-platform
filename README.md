# TelecomAI Analyst

A Flask-based telecom operations demo platform powered by Groq and SQLite. TelecomAI Analyst combines customer self-service, support agent tooling, operational reporting, and AI-driven workflows through **ARIA** — an intelligent assistant that inspects customers, tickets, usage, outages, and SLA risk in real time.

---

## Features

**Customer Self-Service Portal**
- Account lookup and usage review
- Ticket tracking and ticket creation

**Agent Workspace**
- AI chat with tool calling via ARIA
- Covers customer lookup, tickets, network events, usage, SLA checks, SQL queries, and ticket actions

**Reports & Analytics Dashboard**
- Ticket and outage trends, severity breakdowns, SLA compliance
- AI-generated insights and forecast metrics
- PDF export via ReportLab

**AI & Data**
- Multi-agent flow for complaint triage, customer/network lookup, and resolution generation
- SQLite-backed dataset: customers, tickets, usage records, and network events
- Optional realistic data population using Faker

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask |
| Database | SQLite |
| AI / LLM | Groq API, Llama 3.1 |
| PDF Generation | ReportLab |
| Data Generation | Faker |
| Frontend | HTML, CSS, JavaScript, Chart.js |

---

## Prerequisites

- Python 3.10 or newer
- A [Groq API key](https://console.groq.com)

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key_here
```

---

## Installation

**1. Create and activate a virtual environment:**

```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS / Linux
```

**2. Install dependencies:**

```bash
pip install flask groq python-dotenv reportlab faker
```

---

## Database Setup

**Create the database with starter seed data:**

```bash
python db/schema_and_seed.py
```

**Optionally populate a larger realistic dataset:**

```bash
python db/populate_realistic_data.py
```

The database is created at `db/telecom.db`.

---

## Running the App

Start the Flask development server:

```bash
python app/flask_app.py
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

| Page | URL |
|---|---|
| Customer self-service portal | `http://127.0.0.1:5000/customer` |
| Agent AI workspace | `http://127.0.0.1:5000/agent` |
| Reports and analytics | `http://127.0.0.1:5000/reports` |

> **Note:** Run the app from the project root so relative paths like `db/telecom.db` resolve correctly.

---

## API Reference

### Customer & Ticket Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/customers` | List all customers |
| GET | `/api/customer/<customer_id>` | Get a single customer |
| GET | `/api/tickets` | List all tickets |
| GET | `/api/tickets/<customer_id>` | Get tickets for a customer |
| POST | `/api/tickets/create` | Create a new ticket |
| POST | `/api/tickets/close/<ticket_id>` | Close a ticket |

### Network, Usage & AI Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/network-events` | List network events |
| GET | `/api/usage/<customer_id>` | Get usage for a customer |
| POST | `/api/analyze` | Run an AI analysis |
| POST | `/api/agent/chat` | Send a message to the ARIA agent |

### Reports Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/reports/overview?range=7` | Last 7 days overview |
| GET | `/api/reports/overview?range=30` | Last 30 days overview |
| GET | `/api/reports/overview?range=month` | Current month overview |
| GET | `/api/reports/overview?range=overall` | All-time overview |
| GET | `/api/reports/export?range=7` | Export report as PDF |

---

## ARIA Agent Workflow

The agent chat follows this flow:

1. The frontend sends the full chat history to `/api/agent/chat`.
2. ARIA decides which tools to call — customer lookup, tickets, outages, usage, SQL, SLA checks, ticket creation, or ticket closure.
3. The Flask backend executes the selected tool against SQLite.
4. Tool calls, tool results, and the final answer are streamed back to the UI using server-sent events (SSE).

---

## Sample Customer IDs

The starter seed data includes the following customers:

| Customer ID | Name |
|---|---|
| C001 | Ravi Kumar |
| C002 | Priya Sharma |
| C003 | John Doe |
| C004 | Anjali Singh |
| C005 | Mohammed Ali |

If you run `populate_realistic_data.py`, additional customers follow the format `C0001`, `C0002`, and so on.

---

## Notes

- Groq-backed features (ARIA, AI insights, multi-agent flow) require a valid `GROQ_API_KEY` in your `.env` file.
- There is no pinned `requirements.txt` — install the packages listed in the Installation section before running.
- PDF reports are exported as `TelecomAI_Report.pdf`.