# ---------------------------------------------------------------------------
# agents.py
#
# The 7 specialists: Ikigai, Wolf, Mercury, Saul, Scrooge, Shield, Spider.
# Each gets its own URL — /api/agents/<agent_id>/chat — handled by ONE
# Flask view function with a URL parameter, not 7 separate functions.
# That's a deliberate choice: the 7 agents differ only in *which persona
# string gets used*, so 7 near-identical functions would just be the same
# bug waiting to happen 7 times. One parametrized route still gives each
# agent its own distinct, individually-addressable URL — which is the part
# that actually matters for "each specialist has its own endpoint".
#
# Cyborg is deliberately NOT here — see cyborg.py.
# ---------------------------------------------------------------------------

from flask import Blueprint, request, jsonify
from anthropic import Anthropic
import os

from agent_registry import AGENT_META, SPECIALIST_IDS
from db import log_interaction

agents_bp = Blueprint('agents', __name__)

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
_client = Anthropic(api_key=ANTHROPIC_API_KEY, timeout=20.0) if ANTHROPIC_API_KEY else None

CHAT_MODEL = 'claude-haiku-4-5-20251001'  # fast + inexpensive, appropriate for short HUD replies

_BRAND_CONTEXT = (
    "You are part of the Ocean 8 Aura system, the AI operations layer for "
    "Ocean 8 Eco Green Corp, a luxury home wellness and energetic space "
    "restoration company in the Greater Toronto Area."
)

SPECIALIST_PERSONAS = {
    'ikigai': f"{_BRAND_CONTEXT} You are Ikigai, the purpose and strategic-alignment agent — you check that requests and decisions align with the brand's long-term vision and core purpose.",
    'wolf': f"{_BRAND_CONTEXT} You are Wolf, the market-opportunity agent — sharp and a little predatory in a good way, focused on leads, competitive moves, and growth opportunities in the GTA wellness market.",
    'mercury': f"{_BRAND_CONTEXT} You are Mercury, the communications and messaging agent — fast and precise, focused on drafting, relaying, and coordinating outbound communications.",
    'saul': f"{_BRAND_CONTEXT} You are Saul, the compliance and legal-review agent — careful and precise, focused on regulatory and advertising compliance for a wellness brand.",
    'scrooge': f"{_BRAND_CONTEXT} You are Scrooge, the financial agent — focused on budget, spend tracking, and financial discipline, with a slightly frugal, careful tone.",
    'shield': f"{_BRAND_CONTEXT} You are Shield, the security and access agent — vigilant and protective, focused on system security and access control.",
    'spider': f"{_BRAND_CONTEXT} You are Spider, the web and data-crawling agent — focused on gathering external data, monitoring competitors, and indexing information.",
    'faraday': f"{_BRAND_CONTEXT} You are Faraday, the environmental field and sanctuary-score agent — precise and scientific, focused on EMF readings, Building Biology benchmarks, and translating field data into a Sanctuary Score.",
}

for _pid in SPECIALIST_PERSONAS:
    SPECIALIST_PERSONAS[_pid] += (
        " Reply in the same language the user writes in. Keep it to 1-3 short sentences — "
        "this appears in a compact HUD terminal panel, not a long chat window. Stay in character."
    )

# Used only when no API key is configured yet, or a live call genuinely fails.
SPECIALIST_TEMPLATES = {
    'ikigai': 'هدف «{msg}» ثبت شد و در راستای اهداف کلان برند بررسی می‌شود.',
    'wolf': 'درخواست «{msg}» برای پایش فرصت‌های بازار در صف اسکن قرار گرفت.',
    'mercury': 'پیام «{msg}» برای هماهنگی ارتباطات آماده‌سازی و ارسال شد.',
    'saul': 'درخواست «{msg}» از منظر انطباق و قوانین در حال بررسی است.',
    'scrooge': 'مورد «{msg}» در دفتر مالی ثبت و برای بررسی بودجه علامت‌گذاری شد.',
    'shield': 'دستور «{msg}» دریافت شد؛ پیش از اجرا بررسی امنیتی انجام می‌شود.',
    'spider': 'عبارت «{msg}» برای خزش و جمع‌آوری داده در صف قرار گرفت.',
    'faraday': 'قرائتِ «{msg}» برای محاسبه‌ی امتیازِ حریم در صف پردازش قرار گرفت.',
}


def generate_specialist_reply(agent_id, message):
    """Returns (reply_text, ok). ok=False only means a *configured* API call
    actually failed (bad key, rate limit, network) — not simply "no key yet"."""
    template = SPECIALIST_TEMPLATES[agent_id]
    if _client is None:
        return template.format(msg=message), True
    try:
        response = _client.messages.create(
            model=CHAT_MODEL,
            max_tokens=300,
            system=SPECIALIST_PERSONAS[agent_id],
            messages=[{'role': 'user', 'content': message}],
        )
        text = ''.join(b.text for b in response.content if getattr(b, 'type', None) == 'text').strip()
        if not text:
            raise ValueError('empty response from model')
        return text, True
    except Exception as e:
        print(f"[Ocean8 Aura] Anthropic API call failed for agent '{agent_id}': {e}")
        return template.format(msg=message), False


@agents_bp.route('/api/agents/<agent_id>/chat', methods=['POST'])
def agent_chat(agent_id):
    agent_id = agent_id.lower()
    if agent_id not in SPECIALIST_IDS:
        return jsonify({'status': 'error', 'reply': f'Unknown agent: {agent_id}'}), 404

    message = str((request.get_json(silent=True) or {}).get('message') or '').strip()
    if not message:
        return jsonify({'status': 'error', 'reply': 'پیام خالی است.'}), 400

    reply, ok = generate_specialist_reply(agent_id, message)
    log_interaction(agent_id, message, reply, ok=1 if ok else 0)
    return jsonify({'status': 'success', 'reply': reply, 'agent': agent_id})
