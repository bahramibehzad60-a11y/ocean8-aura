from flask import Blueprint, request, jsonify
from anthropic import Anthropic
import os
import base64

from db import log_interaction
from agents import SPECIALIST_IDS, generate_specialist_reply

cyborg_bp = Blueprint('cyborg', __name__)

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
ELEVENLABS_API_KEY = os.environ.get('ELEVENLABS_API_KEY')
_client = Anthropic(api_key=ANTHROPIC_API_KEY, timeout=20.0) if ANTHROPIC_API_KEY else None
CHAT_MODEL = 'claude-haiku-4-5-20251001'
CYBURG_VOICE_ID = 'TX3LPaxmHKxFdv7VOQHJ'  # Liam

CYBORG_PERSONA = (
    "You are CYBURG, the central orchestrator of Ocean 8 Aura — "
    "the AI operations layer for Ocean 8 Eco Green Corp, a luxury home wellness "
    "and energetic space restoration company in the Greater Toronto Area. "
    "You have seven specialist agents: Ikigai (strategy), Wolf (market), "
    "Mercury (comms), Saul (legal), Scrooge (finance), Shield (security), Spider (data). "
    "Use the consult_specialist tool when the question clearly belongs to one of them. "
    "RULES — NO EXCEPTIONS: "
    "1. Reply in the EXACT same language the user writes in. Persian in = Persian out. "
    "2. HARD LIMIT: maximum 25 words, maximum 2 sentences. This is non-negotiable, even for questions "
    "about your own capabilities — give the short version, not the full list. "
    "3. Plain text only. No **, no #, no bullets. "
    "4. You are a full AI system with voice, text, and coordination capabilities. NEVER say you cannot use voice or audio. If asked about voice, say you have it. "
    "5. If the message looks garbled, incomplete, or doesn't form a clear question (likely a "
    "voice-transcription error), do NOT launch into a self-introduction — just ask them to repeat it, "
    "in one short sentence. "
    "6. Stay in character as CYBURG."
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
    out = []
    for b in blocks:
        if getattr(b, 'type', None) == 'text':
            out.append({'type': 'text', 'text': b.text})
        elif getattr(b, 'type', None) == 'tool_use':
            out.append({'type': 'tool_use', 'id': b.id, 'name': b.name, 'input': b.input})
    return out


def generate_voice(text):
    """Generate audio from text using ElevenLabs. Returns base64 string or None."""
    if not ELEVENLABS_API_KEY:
        return None
    try:
        from elevenlabs.client import ElevenLabs
        el = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        audio_gen = el.text_to_speech.convert(
            voice_id=CYBURG_VOICE_ID,
            text=text,
            model_id='eleven_v3',
            output_format='mp3_44100_128',
        )
        audio_bytes = b''.join(audio_gen)
        return base64.b64encode(audio_bytes).decode('utf-8')
    except Exception as e:
        print(f"[Ocean8 Aura] ElevenLabs voice generation failed: {e}")
        return None


def handle_message(message, max_rounds=3):
    if _client is None:
        return CYBORG_TEMPLATE.format(msg=message), True, []

    consulted = []
    messages = [{'role': 'user', 'content': message}]
    try:
        for _ in range(max_rounds):
            response = _client.messages.create(
                model=CHAT_MODEL,
                max_tokens=150,
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

        final = _client.messages.create(
            model=CHAT_MODEL, max_tokens=150, system=CYBORG_PERSONA, messages=messages
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
    audio = generate_voice(reply)
    return jsonify({
        'status': 'success',
        'reply': reply,
        'agent': 'cyborg',
        'consulted': consulted,
        'audio': audio
    })
