import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, Response, request, jsonify, render_template, redirect, stream_with_context, url_for, send_file
from agents.triage_agent import triage_complaint
from agents.sql_agent import get_customer_data, check_network_in_location
from agents.resolution_agent import generate_resolution
import sqlite3, uuid, json
from datetime import datetime, timedelta
from groq import Groq
from prompts import templates
import re

from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics

app = Flask(__name__, template_folder='templates', static_folder='static')
DB_PATH = "db/telecom.db"
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def qdb(sql, args=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(sql, args) 
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

# ── PORTAL PAGES ─────────────────────────────────────
@app.route('/')
def index():
    return redirect(url_for('customer_portal'))

@app.route('/customer')
def customer_portal():
    return render_template('customer.html')

@app.route('/agent')
def agent_portal():
    return render_template('agent.html')

@app.route('/reports')
def reports_page():
    return render_template('reports.html')

@app.route('/analyst')
def analyst_portal():
    return render_template('analyst.html')

# ── API: CUSTOMERS ────────────────────────────────────
@app.route('/api/customers')
def get_customers():
    return jsonify(qdb("SELECT * FROM customers"))

@app.route('/api/customer/<customer_id>')
def get_customer(customer_id):
    rows = qdb("SELECT * FROM customers WHERE customer_id=?", (customer_id,))
    if not rows:
        return jsonify({'error': 'Customer not found'}), 404
    return jsonify(rows[0])

# ── API: TICKETS ──────────────────────────────────────
@app.route('/api/tickets')
def get_tickets():
    rows = qdb("""
        SELECT t.*, c.name, c.location, c.plan, c.phone, c.account_status
        FROM tickets t JOIN customers c ON t.customer_id = c.customer_id
        ORDER BY t.created_at DESC
    """)
    return jsonify(rows)

@app.route('/api/tickets/<customer_id>')
def get_customer_tickets(customer_id):
    return jsonify(qdb(
        "SELECT * FROM tickets WHERE customer_id=? ORDER BY created_at DESC",
        (customer_id,)
    ))

@app.route('/api/tickets/create', methods=['POST'])
def create_ticket():
    d = request.get_json()
    tid = 'T' + str(uuid.uuid4())[:6].upper()
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO tickets VALUES (?,?,?,?,?,?,?)",
        (tid, d['customer_id'], d['issue_type'], d['description'], 'Open', now, None))
    conn.commit(); conn.close()
    return jsonify({'ticket_id': tid, 'status': 'created'})

@app.route('/api/tickets/close/<ticket_id>', methods=['POST'])
def close_ticket(ticket_id):
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE tickets SET status='Resolved', resolved_at=? WHERE ticket_id=?", (now, ticket_id))
    conn.commit(); conn.close()
    return jsonify({'status': 'closed'})

# ── API: NETWORK EVENTS ───────────────────────────────
@app.route('/api/network-events')
def get_network_events():
    return jsonify(qdb("SELECT * FROM network_events ORDER BY severity"))

# ── API: USAGE ────────────────────────────────────────
@app.route('/api/usage/<customer_id>')
def get_usage(customer_id):
    return jsonify(qdb("SELECT * FROM usage_data WHERE customer_id=?", (customer_id,)))

# ── API: AI ANALYZE ───────────────────────────────────
@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        d = request.get_json()
        cid, complaint = d.get('customer_id'), d.get('complaint')
        if not cid or not complaint:
            return jsonify({'error': 'Missing fields'}), 400
        triage = triage_complaint(complaint)
        db_data = get_customer_data(cid)
        customer = db_data.get('customer')
        if not customer:
            return jsonify({'error': f'Customer {cid} not found'}), 404
        network_events = []
        if triage.get('needs_network_check'):
            network_events = check_network_in_location(customer['location'])
        resolution = generate_resolution(customer, triage, network_events)
        return jsonify({'customer': customer, 'triage': triage,
                        'network_events': network_events, 'resolution': resolution})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/agent/chat', methods=['POST'])
def agent_chat():
    data = request.get_json()
    messages = data.get('messages', [])

    system_prompt = (
        templates.SYSTEM_PROMPT
        + datetime.now().strftime("%B %d, %Y %H:%M")
    )

    TOOLS = [
        {"type":"function","function":{"name":"get_customer","description":"Fetch full customer profile by ID","parameters":{"type":"object","properties":{"customer_id":{"type":"string"}},"required":["customer_id"]}}},
        {"type":"function","function":{"name":"get_tickets","description":"Get support tickets, optionally filter by customer_id, status (Open/Resolved/All), or location","parameters":{"type":"object","properties":{"customer_id":{"type":["string","null"]},"status":{"type":"string","enum":["Open","Resolved","All"]},"location":{"type":["string","null"]}},"required":[]}}},
        {"type":"function","function":{"name":"get_network_events","description":"Get network outages and events, optionally filter by location or active_only","parameters":{"type":"object","properties":{"location":{"type":["string","null"]},"active_only":{"type":["boolean","null"]}},"required":[]}}},
        {"type":"function","function":{"name":"get_usage","description":"Get data/call/SMS usage for a customer","parameters":{"type":"object","properties":{"customer_id":{"type":"string"}},"required":["customer_id"]}}},
        {"type":"function","function":{"name":"run_sql","description":"Run a custom SELECT SQL query. Tables: customers(customer_id,name,phone,email,plan,location,account_status), tickets(ticket_id,customer_id,issue_type,description,status,created_at,resolved_at), network_events(event_id,location,event_type,severity,start_time,end_time,affected_customers), usage_data(usage_id,customer_id,month,data_used_gb,call_minutes,sms_count)","parameters":{"type":"object","properties":{"query":{"type":"string"},"explanation":{"type":"string"}},"required":["query","explanation"]}}},
        {"type":"function","function":{"name":"check_sla_breaches","description":"Find all open tickets breaching or at risk of breaching SLA (24h threshold)","parameters":{"type":"object","properties":{}}}},
        {"type":"function","function":{"name":"draft_bulk_sms","description":"Draft personalized SMS messages for a list of customers. Use {name} for first name, {plan} for plan name in the template","parameters":{"type":"object","properties":{"customer_ids":{"type":"array","items":{"type":"string"}},"event_type":{"type":"string"},"message_template":{"type":"string"}},"required":["customer_ids","event_type","message_template"]}}},
        {"type":"function","function":{"name":"create_ticket","description":"Create a new support ticket for a customer","parameters":{"type":"object","properties":{"customer_id":{"type":"string"},"issue_type":{"type":"string"},"description":{"type":"string"}},"required":["customer_id","issue_type","description"]}}},
        {"type":"function","function":{"name":"close_ticket","description":"Mark a ticket as resolved","parameters":{"type":"object","properties":{"ticket_id":{"type":"string"}},"required":["ticket_id"]}}},
    ]

    def execute_tool(name, args):
        try:
            if name == "get_customer":
                rows = qdb("SELECT * FROM customers WHERE UPPER(customer_id)=UPPER(?)", (args["customer_id"],))
                if not rows: return {"error": f"Customer {args['customer_id']} not found"}
                c = rows[0]
                c["open_tickets"] = len(qdb("SELECT 1 FROM tickets WHERE UPPER(customer_id)=UPPER(?) AND status='Open'", (args["customer_id"],)))
                return c
            elif name == "get_tickets":
                sql = "SELECT t.*, c.name, c.location, c.plan FROM tickets t JOIN customers c ON t.customer_id=c.customer_id WHERE 1=1"
                params = []
                if args.get("customer_id"): sql += " AND UPPER(t.customer_id)=UPPER(?)"; params.append(args["customer_id"])
                if args.get("status") and args["status"] != "All": sql += " AND t.status=?"; params.append(args["status"])
                if args.get("location"): sql += " AND c.location LIKE ?"; params.append(f"%{args['location']}%")
                sql += " ORDER BY t.created_at DESC LIMIT 20"
                rows = qdb(sql, params)
                for r in rows:
                    if r.get("created_at"):
                        h = (datetime.now() - datetime.fromisoformat(r["created_at"].replace(" ","T"))).total_seconds()/3600
                        r["hours_open"] = round(h,1)
                return {
                    "success": True,
                    "count": len(rows),
                    "results": rows
                }
            elif name == "get_network_events":
                sql = "SELECT * FROM network_events WHERE 1=1"
                params = []
                if args.get("location"): sql += " AND location LIKE ?"; params.append(f"%{args['location']}%")
                if args.get("active_only"): sql += " AND end_time IS NULL"
                rows = qdb(sql + " ORDER BY severity DESC", params)
                return {
                    "success": True,
                    "count": len(rows),
                    "results": rows
                }
            elif name == "get_usage":
                rows = qdb("SELECT * FROM usage_data WHERE customer_id=? ORDER BY month DESC LIMIT 3", (args["customer_id"],))
                return {
                    "success": True,
                    "count": len(rows),
                    "results": rows
                }
            elif name == "run_sql":
                q = args["query"].strip()
                if not q.upper().startswith("SELECT"): return {"error": "Only SELECT queries allowed"}
                rows = qdb(q)
                return {"explanation": args.get("explanation",""), "row_count": len(rows), "results": rows}
            elif name == "check_sla_breaches":
                rows = qdb("SELECT t.*, c.name, c.location, c.plan FROM tickets t JOIN customers c ON t.customer_id=c.customer_id WHERE t.status='Open' ORDER BY t.created_at ASC")
                breached, warning, ok = [], [], []
                for r in rows:
                    h = (datetime.now() - datetime.fromisoformat(r["created_at"].replace(" ","T"))).total_seconds()/3600
                    r["hours_open"] = round(h,1)
                    if h >= 24: breached.append(r)
                    elif h >= 18: warning.append(r)
                    else: ok.append(r)
                return {"breached": breached, "warning": warning, "ok": ok, "summary": f"{len(breached)} breached, {len(warning)} at risk, {len(ok)} healthy"}
            elif name == "draft_bulk_sms":
                messages_out = []
                for cid in args.get("customer_ids", []):
                    rows = qdb("SELECT * FROM customers WHERE customer_id=?", (cid,))
                    if rows:
                        c = rows[0]
                        msg = args["message_template"].replace("{name}", c["name"].split()[0]).replace("{plan}", c["plan"]).replace("{id}", cid)
                        messages_out.append({"customer_id": cid, "name": c["name"], "phone": c["phone"], "message": msg})
                return {"event_type": args["event_type"], "count": len(messages_out), "messages": messages_out}
            
            elif name == "create_ticket":
                tid = 'T' + str(uuid.uuid4())[:6].upper()
                now = datetime.now().strftime('%Y-%m-%d %H:%M')
                conn = sqlite3.connect(DB_PATH)
                conn.execute("INSERT INTO tickets VALUES (?,?,?,?,?,?,?)",(tid,args["customer_id"],args["issue_type"],args["description"],"Open",now,None))

                conn.commit()
                conn.close()

                return {
                    "success": True,
                    "ticket_id": tid,
                    "customer_id": args["customer_id"],
                    "issue_type": args["issue_type"],
                    "description": args["description"],
                    "status": "Open",
                    "created_at": now
                }
            
            elif name == "close_ticket":
                tid = args["ticket_id"]
                now = datetime.now().strftime('%Y-%m-%d %H:%M')
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute("UPDATE tickets SET status='Resolved', resolved_at=? WHERE ticket_id=?", (now, tid))
                conn.commit() 
                updated = cur.rowcount
                conn.close()
                if updated == 0:
                    return {
                        "success": False,
                        "error": f"Ticket {tid} not found"
                    }

                return {
                    "success": True,
                    "ticket_id": tid,
                    "status": "Resolved",
                    "resolved_at": now
                }
        except Exception as e:
            return {"error": str(e)}
    
    def generate():
        msgs = [{"role": "system", "content": system_prompt}] + messages

        for iteration in range(8):
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                # model="llama-3.3-70b-versatile",
                messages=msgs,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=2000,
                temperature=0.3
            )
            msg = response.choices[0].message

            if msg.tool_calls:
                # ✅ ONE assistant message with ALL tool calls — append ONCE before the loop
                msgs.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                })

                # ✅ Now execute each tool and append only tool result messages
                for tc in msg.tool_calls:
                    fn_name = tc.function.name
                    fn_args = json.loads(tc.function.arguments)

                    # Stream tool call to frontend
                    yield f"data: {json.dumps({'type': 'tool_call', 'name': fn_name, 'args': fn_args})}\n\n"

                    # Execute
                    result = execute_tool(fn_name, fn_args)

                    # Stream tool result to frontend
                    yield f"data: {json.dumps({'type': 'tool_result', 'name': fn_name, 'result': result})}\n\n"

                    # ✅ Only tool result message here — NO assistant message inside loop
                    msgs.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result)
                    })

            else:
                # AI is done — stream final response
                final_text = msg.content or ""
                final_text = re.sub(r'<function=\w+>.*?</function>', '', final_text, flags=re.DOTALL).strip()
                final_text = re.sub(r'</?function.*?>', '', final_text).strip()

                # ── Check if model skipped prose and only returned NEXT_ACTIONS ──
                prose = re.sub(r'\[NEXT_ACTIONS\][\s\S]*?\[\/NEXT_ACTIONS\]', '', final_text).strip()

                if not prose:
                    # Model skipped writing a summary — force one using the tool results in context
                    print("[ARIA] No prose detected — forcing summary call...")
                    summary_msgs = msgs + [{
                        "role": "user",
                        "content": (
                            "You forgot to write your answer. Look at the tool results above and write "
                            "a clear 2-5 line summary of ONLY what the tools actually returned. "
                            "Copy IDs, names, and numbers exactly as they appear in the tool results — "
                            "do not invent, add, or change any values. "
                            "Do NOT call any tools. Do NOT include [NEXT_ACTIONS]. Just the summary."
                        )
                    }]
                    summary_resp = client.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        messages=summary_msgs,
                        max_tokens=400,
                        temperature=0.2
                    )
                    prose = summary_resp.choices[0].message.content or "Investigation complete."
                    # Rebuild final_text with the forced prose + original actions block
                    actions_match = re.search(r'\[NEXT_ACTIONS\][\s\S]*?\[\/NEXT_ACTIONS\]', final_text)
                    actions_block = actions_match.group(0) if actions_match else ""
                    final_text = prose.strip() + ("\n\n" + actions_block if actions_block else "")

                # print("\n" + "="*60)
                # print("ARIA FINAL RESPONSE:")
                # print("="*60)
                # print(repr(final_text))
                # print("="*60 + "\n")

                yield f"data: {json.dumps({'type': 'final', 'text': final_text})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

        # ✅ Max iterations hit — send a fallback message instead of silent done
        yield f"data: {json.dumps({'type': 'final', 'text': 'I reached the maximum reasoning steps. Please try a more specific query.'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
)


@app.route('/api/reports/overview')
def reports_overview():
    
    range_filter = request.args.get(
        "range",
        "7"
    )

    if range_filter == "30":

        days_back = 30

    elif range_filter == "month":

        days_back = datetime.now().day

    elif range_filter == "overall":

        days_back = 3650

    else:

        days_back = 7
    
    date_filter = f"-{days_back} day"

    import time

    start = time.time()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # ─────────────────────────────────────────
    # OPEN TICKETS
    # ─────────────────────────────────────────

    open_tickets = cursor.execute("""
        SELECT COUNT(*) as count
        FROM tickets
        WHERE status = 'Open'
        AND date(created_at) >= date('now', ?)
    """,(date_filter,)).fetchone()["count"]

    yesterday_open = cursor.execute("""
        SELECT COUNT(*) as count
        FROM tickets
        WHERE status = 'Open'
        AND date(created_at) <= date('now', '-1 day')
    """).fetchone()["count"]

    ticket_delta = open_tickets - yesterday_open

    # ─────────────────────────────────────────
    # ACTIVE OUTAGES
    # ─────────────────────────────────────────

    active_outages = cursor.execute("""
        SELECT COUNT(*) as count
        FROM network_events
        WHERE end_time IS NULL
    """).fetchone()["count"]

    # ─────────────────────────────────────────
    # PRIORITY + AGING METRICS
    # ─────────────────────────────────────────

    critical_tickets = cursor.execute("""
        SELECT COUNT(*) as count
        FROM tickets
        WHERE status = 'Open'
        AND (
            priority = 'Critical'
            OR severity = 'Critical'
        )
    """).fetchone()["count"]

    high_priority = cursor.execute("""
        SELECT COUNT(*) as count
        FROM tickets
        WHERE status = 'Open'
        AND (
            priority = 'High'
            OR severity = 'High'
        )
    """).fetchone()["count"]

    overdue_tickets = cursor.execute("""
        SELECT COUNT(*) as count
        FROM tickets
        WHERE status = 'Open'
        AND julianday('now') - julianday(created_at) > 2
    """).fetchone()["count"]

    # ─────────────────────────────────────────
    # SLA RISK
    # ─────────────────────────────────────────

    sla_risk_percent = round(
        min(
            92,
            (
                (critical_tickets * 3)
                + (high_priority * 1.2)
                + (overdue_tickets * 1.5)
                + (active_outages * 1.5)
                + (open_tickets * 0.18)
            )
        )
    )

    sla_risk_percent = max(8, sla_risk_percent)

    # ─────────────────────────────────────────
    # NETWORK HEALTH
    # ─────────────────────────────────────────

    critical_outages = cursor.execute("""
        SELECT COUNT(*) as count
        FROM network_events
        WHERE end_time IS NULL
        AND severity = 'Critical'
        AND date(start_time) >= date('now', ?)
    """, (date_filter,)).fetchone()["count"]

    major_outages = cursor.execute("""
        SELECT COUNT(*) as count
        FROM network_events
        WHERE end_time IS NULL
        AND severity = 'Major'
        AND date(start_time) >= date('now', ?)
    """, (date_filter,)).fetchone()["count"]

    minor_outages = cursor.execute("""
        SELECT COUNT(*) as count
        FROM network_events
        WHERE end_time IS NULL
        AND (
            severity = 'Minor'
            OR severity IS NULL
        )
        AND date(start_time) >= date('now', ?)
    """, (date_filter,)).fetchone()["count"]

    network_health = round(
        100
        - (critical_outages * 6)
        - (major_outages * 2)
        - (minor_outages * 0.5)
    )

    network_health = max(72, min(99, network_health))

    # ─────────────────────────────────────────
    # TREND DATA
    # ─────────────────────────────────────────

    days = []
    tickets_trend = []
    outage_trend = []

    for i in range(days_back - 1, -1, -1):

        dt = datetime.now() - timedelta(days=i)

        if days_back <= 7:
            day_label = dt.strftime('%a')
        else:
            day_label = dt.strftime('%d %b')

        days.append(day_label)

        ticket_count = cursor.execute("""
            SELECT COUNT(*)
            FROM tickets
            WHERE date(created_at) = date(?)
        """, (dt.strftime('%Y-%m-%d'),)).fetchone()[0]

        outage_count = cursor.execute("""
            SELECT COUNT(*)
            FROM network_events
            WHERE date(start_time) = date(?)
        """, (dt.strftime('%Y-%m-%d'),)).fetchone()[0]

        tickets_trend.append(ticket_count)
        outage_trend.append(outage_count)

    # ─────────────────────────────────────────
    # FORECASTS
    # ─────────────────────────────────────────

    avg_daily_tickets = (
        sum(tickets_trend) / max(len(tickets_trend), 1)
    )

    recent_avg = sum(tickets_trend[-3:]) / 3

    previous_avg = sum(tickets_trend[:3]) / 3

    recent_growth = (
        recent_avg - previous_avg
    ) / max(previous_avg, 1)

    predicted_tickets = round(
        avg_daily_tickets * 7
        + (recent_growth * 10)
    )

    affected = cursor.execute("""
        SELECT COALESCE(SUM(affected_customers), 0)
        FROM network_events
        WHERE end_time IS NULL
    """).fetchone()[0]

    churn_risk = round(
        (
            affected * 0.00025
        )
        + (overdue_tickets * 0.8)
        + (critical_tickets * 2)
    )

    # ─────────────────────────────────────────
    # TOP ISSUES
    # ─────────────────────────────────────────

    issue_rows = cursor.execute("""
        SELECT issue_type, COUNT(*) as total
        FROM tickets
        WHERE status = 'Open'
        AND date(created_at) >= date('now', ?)
        GROUP BY issue_type
        ORDER BY total DESC
        LIMIT 5
    """, (date_filter,)).fetchall()

    

    # ─────────────────────────────────────────
    # AI INSIGHTS
    # ─────────────────────────────────────────

    top_issues = [
        f"{row['issue_type']} ({row['total']})"
        for row in issue_rows
    ]

    ai_prompt = templates.REPORT_OVERVIEW_PROMPT.format(
        open_tickets=open_tickets,
        critical_tickets=critical_tickets,
        high_priority=high_priority,
        overdue_tickets=overdue_tickets,
        active_outages=active_outages,
        critical_outages=critical_outages,
        network_health=network_health,
        sla_risk_percent=sla_risk_percent,
        predicted_tickets=predicted_tickets,
        churn_risk=churn_risk,
        top_issues="\n".join(top_issues)
    )

    
    try:

        ai_response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert telecom operations AI."
                    )
                },
                {
                    "role": "user",
                    "content": ai_prompt
                }
            ],
            temperature=0.4,
            max_tokens=220,
            timeout=8
        )

        raw_text = (
            ai_response.choices[0]
            .message
            .content
            .strip()
        )

        ai_insights = [
            line.strip("-• ").strip()
            for line in raw_text.splitlines()
            if line.strip()
        ]

        if not ai_insights:

            ai_insights = [
                "No operational anomalies detected.",
                "Network operating within expected thresholds."
            ]

    except Exception as e:

        print("AI insight generation failed:", e)

        ai_insights = [
            "Operational insights temporarily unavailable."
        ]

    # ─────────────────────────────────────────
    # SEVERITY BREAKDOWN
    # ─────────────────────────────────────────

    severity_rows = cursor.execute("""
        SELECT
            COALESCE(severity, 'Medium') as severity,
            COUNT(*) as total
        FROM tickets
        WHERE status = 'Open'
        GROUP BY severity
    """).fetchall()

    severity_breakdown = [
        {
            "severity": row["severity"],
            "count": row["total"]
        }
        for row in severity_rows
    ]

    # ─────────────────────────────────────────
    # SLA COMPLIANCE
    # ─────────────────────────────────────────

    sla_rows = cursor.execute("""
        SELECT
            issue_type,

            ROUND(
                AVG(
                    CASE
                        WHEN resolved_within_sla = 1
                        THEN 100
                        ELSE 0
                    END
                )
            ) as sla_pct

        FROM tickets

        WHERE date(created_at) >= date('now', ?)

        GROUP BY issue_type
    """, (date_filter,)).fetchall()

    sla_compliance = []

    for row in sla_rows:

        pct = row["sla_pct"]

        if pct >= 95:
            status = "On Track"

        elif pct >= 80:
            status = "Warning"

        else:
            status = "At Risk"

        sla_compliance.append({
            "name": row["issue_type"],
            "pct": pct,
            "status": status
        })

    conn.close()

    # ─────────────────────────────────────────
    # META
    # ─────────────────────────────────────────

    response_ms = round(
        (time.time() - start) * 1000
    )

    # ─────────────────────────────────────────
    # RESPONSE
    # ─────────────────────────────────────────

    return jsonify({

        "days": days,

        "tickets": tickets_trend,

        "outages": outage_trend,

        "summary": {

            "total_open_tickets": open_tickets,

            "ticket_delta": ticket_delta,

            "active_outages": active_outages,

            "critical_outages": critical_outages,

            "sla_risk": sla_risk_percent,

            "network_health": network_health,

            "predicted_tickets": predicted_tickets,

            "churn_risk": churn_risk,

            "overdue_tickets": overdue_tickets
        },

        "top_issues": [
            {
                "name": row["issue_type"],
                "count": row["total"]
            }
            for row in issue_rows
        ],


        "severity_breakdown": severity_breakdown,

        "sla_compliance": sla_compliance,

        "ai_insights": ai_insights,

        "meta": {
            "response_ms": response_ms,
            "generated_at": datetime.now().isoformat()
        }
    })

@app.route('/api/reports/export')
def export_reports_pdf():

    range_filter = request.args.get('range', '7')

    if range_filter == '30':
        days_back = 30
        range_label = "Last 30 Days"

    elif range_filter == 'month':
        days_back = datetime.now().day
        range_label = "Current Month"

    elif range_filter == 'overall':
        days_back = 3650
        range_label = "Overall"

    else:
        days_back = 7
        range_label = "Last 7 Days"

    date_filter = f'-{days_back} day'

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # ─────────────────────────────────────────
    # CORE METRICS
    # ─────────────────────────────────────────

    open_tickets = cursor.execute("""
        SELECT COUNT(*)
        FROM tickets
        WHERE status = 'Open'
        AND date(created_at) >= date('now', ?)
    """, (date_filter,)).fetchone()[0]

    resolved_tickets = cursor.execute("""
        SELECT COUNT(*)
        FROM tickets
        WHERE status = 'Resolved'
        AND date(created_at) >= date('now', ?)
    """, (date_filter,)).fetchone()[0]

    active_outages = cursor.execute("""
        SELECT COUNT(*)
        FROM network_events
        WHERE end_time IS NULL
    """).fetchone()[0]

    critical_tickets = cursor.execute("""
        SELECT COUNT(*)
        FROM tickets
        WHERE status='Open'
        AND (
            priority='Critical'
            OR severity='Critical'
        )
    """).fetchone()[0]

    high_priority = cursor.execute("""
        SELECT COUNT(*)
        FROM tickets
        WHERE status='Open'
        AND (
            priority='High'
            OR severity='High'
        )
    """).fetchone()[0]

    overdue_tickets = cursor.execute("""
        SELECT COUNT(*)
        FROM tickets
        WHERE status='Open'
        AND julianday('now') - julianday(created_at) > 2
    """).fetchone()[0]

    # ─────────────────────────────────────────
    # NETWORK HEALTH
    # ─────────────────────────────────────────

    critical_outages = cursor.execute("""
        SELECT COUNT(*)
        FROM network_events
        WHERE end_time IS NULL
        AND severity='Critical'
    """).fetchone()[0]

    major_outages = cursor.execute("""
        SELECT COUNT(*)
        FROM network_events
        WHERE end_time IS NULL
        AND severity='Major'
    """).fetchone()[0]

    network_health = round(
        100
        - (critical_outages * 6)
        - (major_outages * 2)
    )

    network_health = max(72, min(99, network_health))

    sla_risk_percent = round(
        min(
            92,
            (
                (critical_tickets * 3)
                + (high_priority * 1.2)
                + (overdue_tickets * 1.5)
                + (active_outages * 1.5)
                + (open_tickets * 0.18)
            )
        )
    )

    sla_risk_percent = max(8, sla_risk_percent)

    # ─────────────────────────────────────────
    # TOP ISSUES
    # ─────────────────────────────────────────

    top_issues = cursor.execute("""
        SELECT issue_type, COUNT(*) as total
        FROM tickets
        WHERE status='Open'
        AND date(created_at) >= date('now', ?)
        GROUP BY issue_type
        ORDER BY total DESC
        LIMIT 6
    """, (date_filter,)).fetchall()

   

    # ─────────────────────────────────────────
    # RECENT TICKETS
    # ─────────────────────────────────────────

    recent_tickets = cursor.execute("""
        SELECT
            ticket_id,
            issue_type,
            priority,
            status,
            created_at

        FROM tickets

        ORDER BY created_at DESC

        LIMIT 10
    """).fetchall()

    # ─────────────────────────────────────────
    # AI INSIGHTS
    # ─────────────────────────────────────────

    top_issue_text = [
        f"{row['issue_type']} ({row['total']})"
        for row in top_issues
    ]

    ai_prompt = templates.REPORT_INSIGHTS_PROMPT.format(
        open_tickets=open_tickets,
        resolved_tickets=resolved_tickets,
        critical_tickets=critical_tickets,
        high_priority=high_priority,
        overdue_tickets=overdue_tickets,
        active_outages=active_outages,
        network_health=network_health,
        sla_risk_percent=sla_risk_percent,
        top_issues="\n".join(top_issue_text)
    )
            
    try:

        ai_response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": "You are an enterprise telecom operations AI."
                },
                {
                    "role": "user",
                    "content": ai_prompt
                }
            ],
            temperature=0.4,
            max_tokens=700
        )

        raw = ai_response.choices[0].message.content.strip()

        json_match = re.search(r'\{.*\}', raw, re.DOTALL)

        ai_data = json.loads(json_match.group()) if json_match else {}

    except Exception as e:

        print("AI PDF insight generation failed:", e)

        ai_data = {
            "summary": "Operational analytics temporarily unavailable.",
            "insights": [],
            "recommendations": []
        }

    conn.close()

    # ─────────────────────────────────────────
    # PDF BUILD
    # ─────────────────────────────────────────

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=40,
        bottomMargin=30
    )

    styles = getSampleStyleSheet()
    elements = []

    # ─────────────────────────────────────────
    # TITLE
    # ─────────────────────────────────────────

    title = Paragraph(
        """
        <font size="26" color="#111827">
        <b>TelecomAI Analytics Report</b>
        </font>
        """,
        styles['Title']
    )

    elements.append(title)

    elements.append(Spacer(1, 10))

    meta = Paragraph(
        f"""
        <font size="10" color="#6b7280">
        Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br/>
        Reporting Window: {range_label}
        </font>
        """,
        styles['Normal']
    )

    elements.append(meta)
    elements.append(Spacer(1, 28))

    # ─────────────────────────────────────────
    # EXECUTIVE SUMMARY
    # ─────────────────────────────────────────

    elements.append(
        Paragraph(
            '<font size="18"><b>Executive Summary</b></font>',
            styles['Heading2']
        )
    )

    elements.append(Spacer(1, 10))

    elements.append(
        Paragraph(
            ai_data.get("summary", ""),
            styles['BodyText']
        )
    )

    elements.append(Spacer(1, 26))

    # ─────────────────────────────────────────
    # SUMMARY TABLE
    # ─────────────────────────────────────────

    summary_data = [
        ['Metric', 'Value'],
        ['Open Tickets', str(open_tickets)],
        ['Resolved Tickets', str(resolved_tickets)],
        ['Critical Tickets', str(critical_tickets)],
        ['High Priority Tickets', str(high_priority)],
        ['Overdue Tickets', str(overdue_tickets)],
        ['Active Outages', str(active_outages)],
        ['Network Health', f'{network_health}%'],
        ['SLA Risk', f'{sla_risk_percent}%']
    ]

    summary_table = Table(summary_data, colWidths=[280, 180])

    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#d9482b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),

        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f9fafb')),

        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),

        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),

        ('BOTTOMPADDING', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 1), (-1, -1), 10),
    ]))

    elements.append(summary_table)

    elements.append(Spacer(1, 30))

    # ─────────────────────────────────────────
    # AI INSIGHTS
    # ─────────────────────────────────────────

    elements.append(
        Paragraph(
            '<font size="18"><b>AI Operational Insights</b></font>',
            styles['Heading2']
        )
    )

    elements.append(Spacer(1, 14))

    for insight in ai_data.get("insights", []):

        card = Table([[
            Paragraph(
                f"""
                <font color="#111827">
                <b>{insight['title']}</b><br/><br/>
                {insight['message']}
                </font>
                """,
                styles['BodyText']
            )
        ]], colWidths=[470])

        card.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f3f4f6')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),

            ('LEFTPADDING', (0, 0), (-1, -1), 18),
            ('RIGHTPADDING', (0, 0), (-1, -1), 18),
            ('TOPPADDING', (0, 0), (-1, -1), 14),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
        ]))

        elements.append(card)
        elements.append(Spacer(1, 12))

    # ─────────────────────────────────────────
    # TOP ISSUES
    # ─────────────────────────────────────────

    elements.append(Spacer(1, 16))

    elements.append(
        Paragraph(
            '<font size="18"><b>Top Issue Types</b></font>',
            styles['Heading2']
        )
    )

    elements.append(Spacer(1, 12))

    issue_data = [['Issue Type', 'Open Tickets']]

    for issue in top_issues:
        issue_data.append([
            issue['issue_type'],
            str(issue['total'])
        ])

    issue_table = Table(issue_data, colWidths=[320, 140])

    issue_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#111827')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),

        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),

        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f9fafb')),

        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
    ]))

    elements.append(issue_table)

    # ─────────────────────────────────────────
    # RECOMMENDATIONS
    # ─────────────────────────────────────────

    if ai_data.get("recommendations"):

        elements.append(Spacer(1, 28))

        elements.append(
            Paragraph(
                '<font size="18"><b>AI Recommendations</b></font>',
                styles['Heading2']
            )
        )

        elements.append(Spacer(1, 10))

        for rec in ai_data["recommendations"]:

            elements.append(
                Paragraph(
                    f"• {rec}",
                    styles['BodyText']
                )
            )

            elements.append(Spacer(1, 6))

    # ─────────────────────────────────────────
    # BUILD PDF
    # ─────────────────────────────────────────

    doc.build(elements)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name='TelecomAI_Report.pdf',
        mimetype='application/pdf'
    )


if __name__ == '__main__':
    app.run(debug=True, port=5000)