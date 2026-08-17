from flask import Flask, render_template, render_template_string, request, jsonify, redirect, url_for
import time
from datetime import datetime, timedelta

from agent_registry import AGENT_META
from db import get_db, init_db, log_interaction
from agents import agents_bp
from cyborg import cyborg_bp, handle_message as cyborg_handle_message
from faraday import faraday_bp
from vitruvius import vitruvius_bp

app = Flask(__name__)
init_db()
app.register_blueprint(agents_bp)
app.register_blueprint(cyborg_bp)
app.register_blueprint(faraday_bp)
app.register_blueprint(vitruvius_bp)


# ---------------------------------------------------------------------------
# Primary interface — the Synapse HUD (templates/index.html)
# ---------------------------------------------------------------------------
@app.route('/')
def home():
    return render_template('index.html')


# ---------------------------------------------------------------------------
# Live agent telemetry — the HUD polls this every 20s. Deliberately still
# ONE endpoint for all 8 agents (not split per-agent like the chat routes):
# splitting this would mean 8 HTTP requests every 20 seconds instead of 1,
# which is strictly worse for a dashboard. "One endpoint per agent" was
# about the *action* routes (agents.py, cyborg.py) — status polling is a
# different kind of read and stays batched.
# status/latency/load/interactions are all derived from real rows in
# agent_logs, not simulated: an agent is "standby" until you actually talk
# to it at least once, "online" after a normal reply, "warning" if its most
# recent interaction was flagged not-ok.
# ---------------------------------------------------------------------------
@app.route('/api/report')
def api_report():
    conn = get_db()
    agents = {}
    one_hour_ago = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')

    for agent_id, meta in AGENT_META.items():
        if agent_id == 'cyborg':
            continue
        t0 = time.time()
        rows = conn.execute(
            'SELECT timestamp, message, response, ok FROM agent_logs WHERE agent_name = ? ORDER BY id DESC LIMIT 5',
            (agent_id,)
        ).fetchall()
        latency_ms = round((time.time() - t0) * 1000, 1)
        recent = conn.execute(
            'SELECT COUNT(*) FROM agent_logs WHERE agent_name = ? AND timestamp >= ?',
            (agent_id, one_hour_ago)
        ).fetchone()[0]
        total = conn.execute(
            'SELECT COUNT(*) FROM agent_logs WHERE agent_name = ?', (agent_id,)
        ).fetchone()[0]

        if not rows:
            status = 'standby'
        elif rows[0]['ok'] == 0:
            status = 'warning'
        else:
            status = 'online'

        agents[agent_id] = {
            'status': status,
            'role': meta['role'],
            'interactions': total,
            'latency': f'{latency_ms}ms',
            'load': f'{min(100, recent * 12)}%',
            'lastAction': rows[0]['response'] if rows else 'No interactions yet — send it a message to activate it.',
            'log': [r['message'] for r in rows[:3]] if rows else [],
        }

    total_all = conn.execute('SELECT COUNT(*) FROM agent_logs').fetchone()[0]
    agents['cyborg'] = {
        'status': 'online',
        'role': AGENT_META['cyborg']['role'],
        'interactions': total_all,
        'lastAction': 'Central orchestrator — coordinating all connected agents.',
    }
    conn.close()
    return jsonify({'agents': agents})


# Legacy form endpoint — kept working for the classic dashboard's <form>, unchanged behavior.
# Delegates to the same cyborg.handle_message() the real /api/cyborg/chat route uses,
# instead of duplicating a second copy of the Anthropic-calling code here.
@app.route('/chat', methods=['POST'])
def chat_legacy():
    message = request.form.get('message', '').strip()
    if message:
        reply, ok, _consulted = cyborg_handle_message(message)
        log_interaction('cyborg', message, reply, ok=1 if ok else 0)
    return redirect(url_for('classic_dashboard'))


# ---------------------------------------------------------------------------
# Classic dashboard — your original design, preserved at /classic.
# Products now read from SQLite instead of being hardcoded in the template.
# ---------------------------------------------------------------------------
CLASSIC_TEMPLATE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>Ocean 8 Aura Management Dashboard</title>
    <style>
        body { font-family: Tahoma, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }
        .container { max-width: 950px; margin: 0 auto; background: #1e293b; padding: 30px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.6); }
        h1 { color: #38bdf8; text-align: center; margin-bottom: 5px; }
        .subtitle { text-align: center; color: #94a3b8; font-size: 14px; margin-bottom: 20px; }
        .status { background: #065f46; color: #34d399; padding: 10px; border-radius: 6px; text-align: center; font-weight: bold; margin-bottom: 20px; }
        .hudlink { display:block; text-align:center; margin-bottom:20px; }
        .hudlink a { color:#38bdf8; font-size:13px; text-decoration:none; border:1px solid #334155; padding:8px 14px; border-radius:6px; }
        .hudlink a:hover { border-color:#38bdf8; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; margin-bottom: 30px; }
        th, td { border: 1px solid #334155; padding: 12px; text-align: right; }
        th { background: #0f172a; color: #38bdf8; }
        .console { background: #090d16; padding: 20px; border-radius: 8px; border: 1px solid #334155; }
        input[type="text"] { width: 72%; padding: 12px; border-radius: 6px; border: 1px solid #475569; background: #1e293b; color: #fff; font-size: 14px; }
        button { padding: 12px 20px; background: #0284c7; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 14px; }
        button:hover { background: #0369a1; }
        .log-box { background: #111827; padding: 10px 15px; border-radius: 6px; margin-top: 10px; border-right: 4px solid #38bdf8; font-size: 13px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Ocean 8 Aura Management Dashboard</h1>
        <div class="subtitle">سیستم یکپارچه مدیریت برند و ارتباط هوشمند</div>
        <div class="status">System Status: Online &amp; Secure (Core Active)</div>
        <div class="hudlink"><a href="/">&larr; بازگشت به رابط سه‌بعدی Synapse HUD</a></div>

        <h2>Products Catalogue</h2>
        <table>
            <tr><th>نام محصول</th><th>دسته‌بندی</th><th>وضعیت سیستم</th></tr>
            {% for p in products %}
            <tr><td>{{ p['name'] }}</td><td>{{ p['category'] }}</td><td>{{ p['status'] }}</td></tr>
            {% endfor %}
        </table>

        <div class="console">
            <h3>Cyborg Agent Neural Link &amp; Console</h3>
            <p style="color: #94a3b8; font-size: 13px;">دستور یا پرسش خود را به ایجنت ارسال کنید تا در پایگاه داده ثبت و پردازش شود:</p>
            <form method="POST" action="/chat">
                <input type="text" name="message" placeholder="دستور خود را اینجا بنویسید..." required>
                <button type="submit">ارسال به ایجنت</button>
            </form>
            <h3 style="margin-top: 25px; font-size: 16px; color: #38bdf8;">آخرین فعالیت‌ها و لاگ‌های ثبت‌شده:</h3>
            {% if logs %}
                {% for log in logs %}
                    <div class="log-box">
                        <strong>زمان:</strong> {{ log['timestamp'] }}<br>
                        <strong>دستور شما:</strong> {{ log['message'] }}<br>
                        <strong style="color: #34d399;">پاسخ سایبرگ:</strong> {{ log['response'] }}
                    </div>
                {% endfor %}
            {% else %}
                <p style="color: #64748b; font-size: 13px;">هنوز دستوری ثبت نشده است.</p>
            {% endif %}
        </div>
    </div>
</body>
</html>
"""


@app.route('/classic')
def classic_dashboard():
    conn = get_db()
    logs = conn.execute(
        'SELECT timestamp, message, response FROM agent_logs ORDER BY id DESC LIMIT 5'
    ).fetchall()
    products = conn.execute('SELECT name, category, status FROM products').fetchall()
    conn.close()
    return render_template_string(CLASSIC_TEMPLATE, logs=logs, products=products)


# ---------------------------------------------------------------------------
# Drafts — every piece of customer-facing content Mercury has generated,
# newest first. Reads the same agent_logs table that's already being written
# to; no new storage. This is a review surface, not an editor — the approve/
# send workflow is a separate future step.
# ---------------------------------------------------------------------------
DRAFTS_TEMPLATE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<title>Ocean 8 Aura — پیش‌نویس‌ها</title>
<style>
  body{ background:#050b0f; color:#dff4f7; font-family:'Segoe UI', Tahoma, sans-serif; margin:0; padding:32px 24px; }
  .top{ display:flex; align-items:baseline; justify-content:space-between; margin-bottom:24px; border-bottom:1px solid #0e2a30; padding-bottom:16px; }
  .top h1{ font-size:1.3rem; margin:0; color:#5eead4; letter-spacing:.03em; }
  .top a{ color:#5eead4; font-size:.85rem; text-decoration:none; }
  .empty{ color:#5b7b81; padding:40px 0; text-align:center; }
  .draft{ background:#0a161a; border:1px solid #123138; border-radius:12px; padding:18px 20px; margin-bottom:14px; }
  .draft-meta{ display:flex; justify-content:space-between; font-size:.75rem; color:#5b7b81; margin-bottom:10px; }
  .draft-req{ font-size:.8rem; color:#7fb8bf; margin-bottom:8px; }
  .draft-req b{ color:#a8e6ec; }
  .draft-body{ font-size:.95rem; line-height:1.8; white-space:pre-wrap; }
  .badge{ display:inline-block; padding:2px 9px; border-radius:20px; font-size:.68rem; }
  .badge.ok{ background:rgba(94,234,212,.12); color:#5eead4; }
  .badge.fail{ background:rgba(244,63,94,.12); color:#f43f5e; }
</style>
</head>
<body>
  <div class="top">
    <h1>◈ پیش‌نویس‌های Mercury</h1>
    <a href="/">↩ بازگشت به HUD</a>
  </div>
  {% if drafts %}
    {% for d in drafts %}
    <div class="draft">
      <div class="draft-meta">
        <span>{{ d['timestamp'] }}</span>
        <span class="badge {{ 'ok' if d['ok'] else 'fail' }}">{{ 'واقعی' if d['ok'] else 'fallback' }}</span>
      </div>
      <div class="draft-req"><b>درخواست:</b> {{ d['message'] }}</div>
      <div class="draft-body">{{ d['response'] }}</div>
    </div>
    {% endfor %}
  {% else %}
    <p class="empty">هنوز هیچ پیش‌نویسی ساخته نشده. از سایبرگ بخواه یه پست یا ایمیل بنویسه.</p>
  {% endif %}
</body>
</html>
"""


@app.route('/drafts')
def drafts_page():
    conn = get_db()
    drafts = conn.execute(
        "SELECT timestamp, message, response, ok FROM agent_logs WHERE agent_name = 'mercury' ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return render_template_string(DRAFTS_TEMPLATE, drafts=drafts)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
