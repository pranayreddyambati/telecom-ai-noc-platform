import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify, render_template_string
from agents.triage_agent import triage_complaint
from agents.sql_agent import get_customer_data, check_network_in_location
from agents.resolution_agent import generate_resolution

app = Flask(__name__)

HTML_PAGE = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>TelecomAI Analyst</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&family=Exo+2:wght@300;400;600&display=swap" rel="stylesheet"/>
<style>
  :root {
    --bg: #030b14;
    --surface: #071628;
    --border: #0a3a5c;
    --accent: #00d4ff;
    --accent2: #ff6b35;
    --green: #00ff88;
    --red: #ff3366;
    --yellow: #ffd700;
    --text: #c8e6f5;
    --muted: #4a7a99;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Exo 2', sans-serif;
    min-height: 100vh;
    overflow-x: hidden;
  }

  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background:
      radial-gradient(ellipse 80% 50% at 50% -10%, rgba(0,212,255,0.08) 0%, transparent 60%),
      repeating-linear-gradient(0deg, transparent, transparent 60px, rgba(0,212,255,0.02) 60px, rgba(0,212,255,0.02) 61px),
      repeating-linear-gradient(90deg, transparent, transparent 60px, rgba(0,212,255,0.02) 60px, rgba(0,212,255,0.02) 61px);
    pointer-events: none;
    z-index: 0;
  }

  .container { max-width: 1100px; margin: 0 auto; padding: 0 24px; position: relative; z-index: 1; }

  /* HEADER */
  header {
    padding: 28px 0 20px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 40px;
    position: relative;
  }
  header::after {
    content: '';
    position: absolute;
    bottom: -1px; left: 0;
    width: 200px; height: 2px;
    background: linear-gradient(90deg, var(--accent), transparent);
  }
  .header-inner { display: flex; align-items: center; gap: 18px; }
  .logo-icon {
    width: 48px; height: 48px;
    border: 2px solid var(--accent);
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 22px;
    box-shadow: 0 0 20px rgba(0,212,255,0.3), inset 0 0 10px rgba(0,212,255,0.05);
    animation: pulse-border 3s ease-in-out infinite;
  }
  @keyframes pulse-border {
    0%,100% { box-shadow: 0 0 20px rgba(0,212,255,0.3), inset 0 0 10px rgba(0,212,255,0.05); }
    50% { box-shadow: 0 0 35px rgba(0,212,255,0.6), inset 0 0 15px rgba(0,212,255,0.1); }
  }
  .header-text h1 {
    font-family: 'Orbitron', monospace;
    font-size: 22px; font-weight: 900;
    color: var(--accent);
    letter-spacing: 3px;
    text-transform: uppercase;
  }
  .header-text p {
    font-family: 'Share Tech Mono', monospace;
    font-size: 11px; color: var(--muted);
    letter-spacing: 2px; margin-top: 3px;
  }
  .status-bar {
    margin-left: auto;
    display: flex; gap: 16px; align-items: center;
  }
  .status-dot {
    display: flex; align-items: center; gap: 6px;
    font-family: 'Share Tech Mono', monospace;
    font-size: 11px; color: var(--muted);
  }
  .dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 8px var(--green);
    animation: blink 2s ease-in-out infinite;
  }
  @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }

  /* MAIN GRID */
  .main-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 32px; }

  /* PANELS */
  .panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
    position: relative;
    overflow: hidden;
  }
  .panel::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
    opacity: 0.5;
  }
  .panel-title {
    font-family: 'Orbitron', monospace;
    font-size: 11px; font-weight: 700;
    color: var(--accent);
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-bottom: 20px;
    display: flex; align-items: center; gap: 8px;
  }
  .panel-title::before {
    content: '';
    width: 3px; height: 14px;
    background: var(--accent);
    border-radius: 2px;
    box-shadow: 0 0 8px var(--accent);
  }

  /* FORM ELEMENTS */
  .form-group { margin-bottom: 18px; }
  label {
    display: block;
    font-family: 'Share Tech Mono', monospace;
    font-size: 11px; color: var(--muted);
    letter-spacing: 2px; text-transform: uppercase;
    margin-bottom: 8px;
  }
  select, textarea {
    width: 100%;
    background: rgba(0,212,255,0.03);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-family: 'Exo 2', sans-serif;
    font-size: 14px;
    padding: 12px 16px;
    transition: border-color 0.2s, box-shadow 0.2s;
    outline: none;
    appearance: none;
  }
  select:focus, textarea:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(0,212,255,0.1);
  }
  textarea { resize: vertical; min-height: 110px; line-height: 1.6; }

  .btn-analyze {
    width: 100%;
    padding: 15px;
    background: linear-gradient(135deg, rgba(0,212,255,0.15), rgba(0,212,255,0.05));
    border: 1px solid var(--accent);
    border-radius: 8px;
    color: var(--accent);
    font-family: 'Orbitron', monospace;
    font-size: 13px; font-weight: 700;
    letter-spacing: 3px;
    cursor: pointer;
    transition: all 0.2s;
    text-transform: uppercase;
    margin-top: 6px;
  }
  .btn-analyze:hover {
    background: linear-gradient(135deg, rgba(0,212,255,0.25), rgba(0,212,255,0.1));
    box-shadow: 0 0 30px rgba(0,212,255,0.2);
    transform: translateY(-1px);
  }
  .btn-analyze:disabled {
    opacity: 0.4; cursor: not-allowed; transform: none;
  }

  /* QUICK CASES */
  .quick-cases { display: flex; flex-direction: column; gap: 10px; }
  .case-btn {
    padding: 12px 16px;
    background: rgba(255,107,53,0.05);
    border: 1px solid rgba(255,107,53,0.2);
    border-radius: 8px;
    color: var(--text);
    font-family: 'Exo 2', sans-serif;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;
    text-align: left;
    display: flex; align-items: center; gap: 10px;
  }
  .case-btn:hover {
    border-color: var(--accent2);
    background: rgba(255,107,53,0.1);
    transform: translateX(4px);
  }
  .case-tag {
    font-family: 'Share Tech Mono', monospace;
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 4px;
    flex-shrink: 0;
  }
  .tag-network { background: rgba(0,212,255,0.15); color: var(--accent); }
  .tag-billing { background: rgba(255,211,0,0.15); color: var(--yellow); }
  .tag-service { background: rgba(0,255,136,0.15); color: var(--green); }

  /* RESULTS */
  .results-panel { grid-column: 1 / -1; display: none; }
  .results-panel.visible { display: block; }

  .loading-state {
    display: none;
    text-align: center;
    padding: 50px 20px;
  }
  .loading-state.visible { display: block; }
  .spinner {
    width: 50px; height: 50px;
    border: 3px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin: 0 auto 20px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .loading-text {
    font-family: 'Share Tech Mono', monospace;
    font-size: 13px; color: var(--accent);
    letter-spacing: 2px;
  }
  .loading-steps { margin-top: 16px; }
  .loading-step {
    font-family: 'Share Tech Mono', monospace;
    font-size: 11px; color: var(--muted);
    padding: 4px 0;
    opacity: 0;
    animation: fadeIn 0.5s forwards;
  }
  @keyframes fadeIn { to { opacity: 1; } }

  /* RESULT CARDS */
  .result-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 20px; }

  .result-card {
    background: rgba(0,0,0,0.3);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 18px;
  }
  .result-card-label {
    font-family: 'Share Tech Mono', monospace;
    font-size: 10px; color: var(--muted);
    letter-spacing: 2px; text-transform: uppercase;
    margin-bottom: 10px;
  }
  .result-card-value {
    font-family: 'Orbitron', monospace;
    font-size: 16px; font-weight: 700;
  }
  .val-network { color: var(--accent); }
  .val-billing { color: var(--yellow); }
  .val-high { color: var(--red); }
  .val-medium { color: var(--yellow); }
  .val-low { color: var(--green); }
  .val-yes { color: var(--red); }
  .val-no { color: var(--green); }

  .keywords-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
  .keyword-chip {
    font-family: 'Share Tech Mono', monospace;
    font-size: 10px;
    padding: 3px 10px;
    background: rgba(0,212,255,0.08);
    border: 1px solid rgba(0,212,255,0.2);
    border-radius: 20px;
    color: var(--accent);
  }

  /* RESOLUTION BOX */
  .resolution-box {
    background: rgba(0,0,0,0.4);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 24px;
    font-size: 14px;
    line-height: 1.8;
    white-space: pre-wrap;
    font-family: 'Exo 2', sans-serif;
    color: var(--text);
  }
  .resolution-box strong, .resolution-box b {
    color: var(--accent);
    font-weight: 600;
  }

  /* NETWORK EVENTS */
  .network-alert {
    background: rgba(255,51,102,0.08);
    border: 1px solid rgba(255,51,102,0.3);
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 12px;
    font-family: 'Share Tech Mono', monospace;
    font-size: 12px;
    color: var(--red);
    display: flex; align-items: center; gap: 10px;
  }
  .network-ok {
    background: rgba(0,255,136,0.05);
    border: 1px solid rgba(0,255,136,0.2);
    border-radius: 8px;
    padding: 12px 16px;
    margin-bottom: 12px;
    font-family: 'Share Tech Mono', monospace;
    font-size: 12px;
    color: var(--green);
    display: flex; align-items: center; gap: 10px;
  }

  /* CUSTOMER INFO */
  .customer-row {
    display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px;
  }
  .info-chip {
    font-family: 'Share Tech Mono', monospace;
    font-size: 11px;
    padding: 5px 12px;
    background: rgba(0,212,255,0.06);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
  }
  .info-chip span { color: var(--accent); margin-right: 4px; }

  /* ERROR */
  .error-box {
    background: rgba(255,51,102,0.08);
    border: 1px solid rgba(255,51,102,0.3);
    border-radius: 8px;
    padding: 20px;
    color: var(--red);
    font-family: 'Share Tech Mono', monospace;
    font-size: 13px;
    display: none;
  }
  .error-box.visible { display: block; }

  @media (max-width: 700px) {
    .main-grid { grid-template-columns: 1fr; }
    .result-grid { grid-template-columns: 1fr 1fr; }
    .status-bar { display: none; }
  }
</style>
</head>
<body>
<div class="container">

  <header>
    <div class="header-inner">
      <div class="logo-icon">📡</div>
      <div class="header-text">
        <h1>TelecomAI Analyst</h1>
        <p>NETWORK OPERATIONS CENTER // AI-POWERED SUPPORT SYSTEM</p>
      </div>
      <div class="status-bar">
        <div class="status-dot"><div class="dot"></div> AI ONLINE</div>
        <div class="status-dot"><div class="dot" style="background:var(--green);box-shadow:0 0 8px var(--green)"></div> DB CONNECTED</div>
      </div>
    </div>
  </header>

  <div class="main-grid">

    <!-- INPUT PANEL -->
    <div class="panel">
      <div class="panel-title">New Support Request</div>
      <div class="form-group">
        <label>Customer ID</label>
        <select id="customerId">
          <option value="C001">C001 — Ravi Kumar (Hyderabad)</option>
          <option value="C002">C002 — Priya Sharma (Mumbai)</option>
          <option value="C003">C003 — John Doe (Delhi)</option>
          <option value="C004">C004 — Anjali Singh (Bangalore)</option>
          <option value="C005">C005 — Mohammed Ali (Chennai)</option>
        </select>
      </div>
      <div class="form-group">
        <label>Customer Complaint</label>
        <textarea id="complaint" placeholder="Describe the customer's issue in detail..."></textarea>
      </div>
      <button class="btn-analyze" id="analyzeBtn" onclick="analyze()">
        ⚡ Analyze &amp; Resolve
      </button>
    </div>

    <!-- QUICK CASES PANEL -->
    <div class="panel">
      <div class="panel-title">Quick Test Cases</div>
      <div class="quick-cases">
        <button class="case-btn" onclick="loadCase('C001', 'My 5G signal has been gone since this morning, I cannot make calls!')">
          <span class="case-tag tag-network">NETWORK</span>
          5G signal loss — unable to make calls
        </button>
        <button class="case-btn" onclick="loadCase('C002', 'Internet is extremely slow, videos keep buffering and I cannot work from home')">
          <span class="case-tag tag-network">NETWORK</span>
          Slow internet — buffering issues
        </button>
        <button class="case-btn" onclick="loadCase('C003', 'I was charged twice on my bill this month, please refund immediately')">
          <span class="case-tag tag-billing">BILLING</span>
          Duplicate charge on monthly bill
        </button>
        <button class="case-btn" onclick="loadCase('C004', 'My calls keep dropping every 2-3 minutes, very frustrating')">
          <span class="case-tag tag-network">NETWORK</span>
          Call dropping frequently
        </button>
        <button class="case-btn" onclick="loadCase('C005', 'No internet connection for the past 2 days, I need it urgently')">
          <span class="case-tag tag-service">SERVICE</span>
          Complete internet outage — 2 days
        </button>
      </div>
    </div>

    <!-- RESULTS PANEL -->
    <div class="panel results-panel" id="resultsPanel">
      <div class="panel-title">Analysis Report</div>

      <!-- Loading -->
      <div class="loading-state" id="loadingState">
        <div class="spinner"></div>
        <div class="loading-text">PROCESSING REQUEST</div>
        <div class="loading-steps" id="loadingSteps"></div>
      </div>

      <!-- Error -->
      <div class="error-box" id="errorBox"></div>

      <!-- Results -->
      <div id="resultContent" style="display:none">

        <div class="customer-row" id="customerRow"></div>

        <div id="networkEventsDiv"></div>

        <div class="result-grid" id="triageGrid"></div>

        <div class="panel-title" style="margin-bottom:14px; margin-top:4px;">Resolution Plan</div>
        <div class="resolution-box" id="resolutionBox"></div>
      </div>
    </div>

  </div>
</div>

<script>
  function loadCase(customerId, complaint) {
    document.getElementById('customerId').value = customerId;
    document.getElementById('complaint').value = complaint;
    document.getElementById('complaint').focus();
  }

  const loadingMessages = [
    "🔍 Triage Agent classifying complaint...",
    "🗄️  SQL Agent querying customer database...",
    "📡 Checking network events in region...",
    "🛠️  Resolution Agent generating fix plan...",
    "📊 Compiling final report..."
  ];

  function showLoadingSteps() {
    const container = document.getElementById('loadingSteps');
    container.innerHTML = '';
    loadingMessages.forEach((msg, i) => {
      const div = document.createElement('div');
      div.className = 'loading-step';
      div.textContent = msg;
      div.style.animationDelay = `${i * 0.7}s`;
      container.appendChild(div);
    });
  }

  function priorityClass(p) {
    const m = {'High':'val-high','Medium':'val-medium','Low':'val-low'};
    return m[p] || 'val-medium';
  }
  function categoryClass(c) {
    return c === 'Network' ? 'val-network' : c === 'Billing' ? '' : 'val-no';
  }

  async function analyze() {
    const customerId = document.getElementById('customerId').value;
    const complaint = document.getElementById('complaint').value.trim();
    if (!complaint) { alert('Please enter a complaint!'); return; }

    const btn = document.getElementById('analyzeBtn');
    btn.disabled = true;
    btn.textContent = '⏳ Analyzing...';

    // Show panel + loading
    const panel = document.getElementById('resultsPanel');
    panel.classList.add('visible');
    document.getElementById('loadingState').classList.add('visible');
    document.getElementById('resultContent').style.display = 'none';
    document.getElementById('errorBox').classList.remove('visible');
    showLoadingSteps();
    panel.scrollIntoView({behavior:'smooth', block:'start'});

    try {
      const res = await fetch('/analyze', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({customer_id: customerId, complaint})
      });
      const data = await res.json();

      if (data.error) throw new Error(data.error);

      // Hide loading
      document.getElementById('loadingState').classList.remove('visible');
      document.getElementById('resultContent').style.display = 'block';

      // Customer info
      const c = data.customer;
      document.getElementById('customerRow').innerHTML = `
        <div class="info-chip"><span>ID</span>${c.customer_id}</div>
        <div class="info-chip"><span>NAME</span>${c.name}</div>
        <div class="info-chip"><span>PLAN</span>${c.plan}</div>
        <div class="info-chip"><span>LOCATION</span>${c.location}</div>
        <div class="info-chip"><span>STATUS</span>${c.account_status}</div>
      `;

      // Network events
      const ne = data.network_events;
      const neDiv = document.getElementById('networkEventsDiv');
      if (ne && ne.length > 0) {
        neDiv.innerHTML = ne.map(e => `
          <div class="network-alert">
            ⚠️ ${e.event_type} — Severity: ${e.severity} — ${e.affected_customers} customers affected
          </div>`).join('');
      } else {
        neDiv.innerHTML = `<div class="network-ok">✅ No active network events detected in ${c.location}</div>`;
      }

      // Triage grid
      const t = data.triage;
      const keywords = (t.keywords || []).map(k => `<span class="keyword-chip">${k}</span>`).join('');
      document.getElementById('triageGrid').innerHTML = `
        <div class="result-card">
          <div class="result-card-label">Issue Category</div>
          <div class="result-card-value ${categoryClass(t.issue_category)}">${t.issue_category}</div>
        </div>
        <div class="result-card">
          <div class="result-card-label">Priority Level</div>
          <div class="result-card-value ${priorityClass(t.priority)}">${t.priority}</div>
        </div>
        <div class="result-card">
          <div class="result-card-label">Network Check</div>
          <div class="result-card-value ${t.needs_network_check ? 'val-yes':'val-no'}">${t.needs_network_check ? 'REQUIRED':'SKIPPED'}</div>
        </div>
        <div class="result-card" style="grid-column:1/-1">
          <div class="result-card-label">Detected Keywords</div>
          <div class="keywords-row">${keywords}</div>
        </div>
      `;

      // Resolution
      document.getElementById('resolutionBox').innerHTML =
        data.resolution.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    } catch(err) {
      document.getElementById('loadingState').classList.remove('visible');
      const eb = document.getElementById('errorBox');
      eb.textContent = '❌ Error: ' + err.message;
      eb.classList.add('visible');
    }

    btn.disabled = false;
    btn.textContent = '⚡ Analyze & Resolve';
  }
</script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        data = request.get_json()
        customer_id = data.get('customer_id')
        complaint = data.get('complaint')

        if not customer_id or not complaint:
            return jsonify({'error': 'Missing customer_id or complaint'}), 400

        # Run the pipeline
        triage_result = triage_complaint(complaint)
        db_data = get_customer_data(customer_id)
        customer = db_data.get('customer')

        if not customer:
            return jsonify({'error': f'Customer {customer_id} not found'}), 404

        network_events = []
        if triage_result.get('needs_network_check'):
            network_events = check_network_in_location(customer['location'])

        resolution = generate_resolution(customer, triage_result, network_events)

        return jsonify({
            'customer': customer,
            'triage': triage_result,
            'network_events': network_events,
            'resolution': resolution
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)