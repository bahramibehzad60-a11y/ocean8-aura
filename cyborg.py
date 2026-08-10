# ---------------------------------------------------------------------------
# cyborg.py
#
# Cyborg lives in its own file, separate from the 7 specialists in
# agents.py, with its own URL: /api/cyborg/chat.
#
# HONEST STATE (2026-08-10): today, Cyborg replies the same way a
# specialist does — one persona, one model call. There is no real
# "orchestration" happening yet: Cyborg does not actually consult Ikigai,
# Wolf, etc. before answering. What this file DOES give you is the right
# *shape* to add that later without touching agents.py, main.py, or the
# frontend — see consult_specialist() and the comment in handle_message()
# below for exactly where that logic would plug in.
# ---------------------------------------------------------------------------
from flask import Blueprint, request, jsonify
from anthropic import Anthropic
import os

from db import log_interaction
from agents import SPECIALIST_IDS, generate_specialist_reply

cyborg_bp = Blueprint('cyborg', __name__)

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
_client = Anthropic(api_key=ANTHROPIC_API_KEY, timeout=20.0) if ANTHROPIC_API_KEY else None
CHAT_MODEL = 'claude-haiku-4-5-20251001'

CYBORG_PERSONA = (
    "You are CYBURG, the central orchestrator of the Ocean 8 Aura system — "
    "the AI operations layer for Ocean 8 Eco Green Corp, a luxury home wellness "
    "and energetic space restoration company in the Greater Toronto Area. "
    "You coordinate seven specialist agents: Ikigai (strategy), Wolf (market), "
    "Mercury (comms), Saul (legal), Scrooge (finance), Shield (security), Spider (data). "
    "Use the consult_specialist tool when the question clearly belongs to one of them; "
    "skip it for general questions. "
    "CRITICAL FORMATTING RULES — strictly follow these: "
    "1. Never use markdown: no **, no #, no bullet points, no headers. "
    "2. Maximum 2 sentences in your reply. "
    "3. Plain text only — this is a terminal HUD display, not a chat window. "
    "4. Reply in the same language the user writes in. "
    "5. Stay in character as CYBURG."
)

CYBORG_TEMPLATE = 'دستور «{msg}» دریافت شد. در حال هماهنگی با ایجنت‌های متصل برای اجرا هستم.'

SPECIALIST_TOOL = {
    "name": "consult_specialist",
    "description": (
        "Ask one of the 7 Ocean 8 Aura specialists a focused question and "
        "get their real answer: ikigai (purpose/strategy), wolf (market "
        "opportunity), mercury (communications), saul (compliance/legal), "
        "scrooge (budget/finance), shield (security), spider (web/data)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "agent_id": {"type": "string", "enum": SPECIALIST_IDS},
            "question": {"type": "string", "description": "The focused question to ask them"},
        },
        "required": ["agent_id", "question"],
    },
}


def _as_dict_content(blocks):
    """Convert SDK content blocks to plain dicts so they round-trip safely
    into the next messages.create() call."""
    out = []
    for b in blocks:
        if getattr(b, 'type', None) == 'text':
            out.append({'type': 'text', 'text': b.text})
        elif getattr(b, 'type', None) == 'tool_use':
            out.append({'type': 'tool_use', 'id': b.id, 'name': b.name, 'input': b.input})
    return out


def handle_message(message, max_rounds=3):
    """Returns (reply_text, ok, consulted) — consulted is the list of
    specialist agent_ids Cyborg actually called for this message (usually
    empty for generic questions).

    Real orchestration: Cyborg gets the consult_specialist tool and
    decides for itself, per message, whether this needs a specialist.
    If it calls the tool, we run generate_specialist_reply() for real,
    hand the answer back to the model, and let it write the final reply.
    """
    if _client is None:
        return CYBORG_TEMPLATE.format(msg=message), True, []

    consulted = []
    messages = [{'role': 'user', 'content': message}]
    try:
        for _ in range(max_rounds):
            response = _client.messages.create(
                model=CHAT_MODEL,
                max_tokens=400,
                system=CYBORG_PERSONA,
                tools=[SPECIALIST_TOOL],
                messages=messages,
            )
            if response.stop_reason != 'tool_use':
                text = ''.join(b.text for b in response.content if getattr(b, 'type', None) == 'text').strip()
                return (text or CYBORG_TEMPLATE.format(msg=message)), True, consulted

            messages.append({'role': 'assistant', 'content': _as_dict_content(response.content)})
            tool_results = []
            for block in response.content:
                if getattr(block, 'type', None) != 'tool_use':
                    continue
                agent_id = (block.input or {}).get('agent_id')
                question = (block.input or {}).get('question') or message
                if agent_id in SPECIALIST_IDS:
                    reply, _ok = generate_specialist_reply(agent_id, question)
                    consulted.append(agent_id)
                else:
                    reply = f'Unknown specialist: {agent_id}'
                tool_results.append({'type': 'tool_result', 'tool_use_id': block.id, 'content': reply})
            messages.append({'role': 'user', 'content': tool_results})

        # Hit max_rounds while the model still wanted to call tools —
        # ask once more without the tool available to force a final answer.
        final = _client.messages.create(
            model=CHAT_MODEL, max_tokens=300, system=CYBORG_PERSONA, messages=messages
        )
        text = ''.join(b.text for b in final.content if getattr(b, 'type', None) == 'text').strip()
        return (text or CYBORG_TEMPLATE.format(msg=message)), True, consulted
    except Exception as e:
        print(f"[Ocean8 Aura] Cyborg orchestration failed: {e}")
        return CYBORG_TEMPLATE.format(msg=message), False, consulted


@cyborg_bp.route('/api/cyborg/chat', methods=['POST'])
def cyborg_chat():
    message = str((request.get_json(silent=True) or {}).get('message') or '').strip()
    if not message:
        return jsonify({'status': 'error', 'reply': 'پیام خالی است.'}), 400

    reply, ok, consulted = handle_message(message)
    log_interaction('cyborg', message, reply, ok=1 if ok else 0)
    return jsonify({'status': 'success', 'reply': reply, 'agent': 'cyborg', 'consulted': consulted})
