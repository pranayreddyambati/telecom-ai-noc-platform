import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, Response, request, jsonify, render_template, redirect, stream_with_context, url_for
from agents.triage_agent import triage_complaint
from agents.sql_agent import get_customer_data, check_network_in_location
from agents.resolution_agent import generate_resolution
import sqlite3, uuid, datetime, json
from groq import Groq
from prompts import templates
import re

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

@app.route('/noc')
def noc_portal():
    return render_template('noc.html')

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
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO tickets VALUES (?,?,?,?,?,?,?)",
        (tid, d['customer_id'], d['issue_type'], d['description'], 'Open', now, None))
    conn.commit(); conn.close()
    return jsonify({'ticket_id': tid, 'status': 'created'})

@app.route('/api/tickets/close/<ticket_id>', methods=['POST'])
def close_ticket(ticket_id):
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
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

    system_prompt = templates.SYSTEM_PROMPT + datetime.datetime.now().strftime("%B %d, %Y %H:%M")

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
                        h = (datetime.datetime.now() - datetime.datetime.fromisoformat(r["created_at"].replace(" ","T"))).total_seconds()/3600
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
                    h = (datetime.datetime.now() - datetime.datetime.fromisoformat(r["created_at"].replace(" ","T"))).total_seconds()/3600
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
                now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
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
                now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
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



if __name__ == '__main__':
    app.run(debug=True, port=5000)