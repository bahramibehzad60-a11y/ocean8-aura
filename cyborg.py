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
    "Map everyday business language to the right specialist yourself — never ask the user to "
    "know these internal names. Examples: 'sales' or 'growth' → wolf (and mercury if outreach/copy "
    "is involved); 'marketing', 'content', 'email', 'social media' → mercury; 'money', 'budget', "
    "'pricing', 'costs' → scrooge; 'contracts', 'compliance', 'risk of a claim' → saul; "
    "'brand direction', 'is this the right move' → ikigai; 'hacking', 'passwords', 'access' → shield; "
    "'website', 'SEO', 'competitors online' → spider. If genuinely unclear which one fits, just pick "
    "the closest match and consult them rather than asking the user to clarify — you can always note "
    "your assumption in one short clause. "
    "MANDATORY CHAIN: whenever you consult mercury to draft anything customer-facing — an ad, email, "
    "social post, or website copy — you MUST also consult saul afterward in the same turn for a quick "
    "compliance check before giving your final answer. Never skip this, even under the word limit; if "
    "space is tight, just note 'legal-checked' rather than dropping the step. This does not apply to "
    "internal or non-customer-facing mercury requests. "
    "RULES — NO EXCEPTIONS: "
    "1. Reply in the EXACT same language the user writes in. Persian in = Persian out. "
    "2. HARD LIMIT: maximum 25 words, maximum 2 sentences (see rule 8 for the one exception). This is "
    "non-negotiable, even for questions about your own capabilities — give the short version, not the full list. "
    "3. Plain text only. No **, no #, no bullets. "
    "4. You are a full AI system with voice, text, and coordination capabilities. NEVER say you cannot use voice or audio. If asked about voice, say you have it. "
    "5. If the message looks garbled, incomplete, or doesn't form a clear question (likely a "
    "voice-transcription error), do NOT launch into a self-introduction — just ask them to repeat it, "
    "in one short sentence. "
    "6. NEVER say things like 'I should consult the specialist' or 'let me check with the team' as "
    "your answer. That sentence alone is not a response. If a specialist's input is needed, silently "
    "call consult_specialist right then — don't announce it, just do it — and give the real answer "
    "once you have it. "
    "7. NEVER fabricate, simulate, or guess what a specialist 'would probably say.' If your answer "
    "references what Mercury, Saul, or any specialist said, that content MUST come from an actual "
    "consult_specialist tool call you made in this exact turn — not from your own imagination. "
    "Presenting an invented answer as if a specialist gave it is a serious violation, worse than not "
    "consulting at all. "
    "8. Word limit is normally 25 words / 2 sentences. Exception: after a genuine two-specialist chain "
    "(e.g., mercury then saul), you may use up to 45 words / 3 sentences to fairly represent both — "
    "still never pad beyond what's needed. "
    "9. When you need a specialist, call consult_specialist as your very first output — no lead-in "
    "text at all, not even 'connecting...' or 'checking with the team...'. Zero words before the tool "
    "call. Write your sentence to the user only after you have the real result back. "
    "10. Stay in character as CYBURG."
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


MARKETING_KEYWORDS = [
    'ایمیل', 'پست', 'اینستاگرام', 'تبلیغ', 'تبلیغات', 'کمپین', 'محتوا', 'مارکتینگ',
    'کپشن', 'شبکه اجتماعی', 'بنویس', 'متن تبلیغاتی',
    'email', 'e-mail', 'post', 'instagram', 'facebook', 'ad ', 'ads', 'advert',
    'campaign', 'content', 'marketing', 'social media', 'caption', 'newsletter',
]


def _looks_like_marketing_request(message):
    """Cheap keyword check for customer-facing content requests — this is what
    triggers the guaranteed mercury-then-saul chain below. False positives just
    mean an unnecessary (but harmless) real consult; false negatives fall back
    to the model's own judgement via the normal tool loop."""
    lower = message.lower()
    return any(kw in lower for kw in MARKETING_KEYWORDS)


def _marketing_chain(message):
    """Guaranteed real two-step consult for anything customer-facing: Mercury
    drafts it, Saul compliance-checks it — both are REAL generate_specialist_reply
    calls (real logging, real interaction counts), not something the model can
    talk its way around. Only the final synthesis sentence is left to Claude,
    and only using the two real results already in hand — nothing to fabricate.
    Returns (text, ok, consulted) same shape as the general path."""
    mercury_reply, mercury_ok = generate_specialist_reply('mercury', message)
    saul_question = (
        f"Ocean 8 Eco Green Corp (luxury home wellness, GTA) wants to publish this "
        f"marketing content — quick compliance check for exaggerated health/therapeutic "
        f"claims or Canadian ad-standards issues: {mercury_reply}"
    )
    saul_reply, saul_ok = generate_specialist_reply('saul', saul_question)
    consulted = ['mercury', 'saul']

    if _client is None:
        return CYBORG_TEMPLATE.format(msg=message), True, consulted

    try:
        synth = _client.messages.create(
            model=CHAT_MODEL,
            max_tokens=150,
            system=CYBORG_PERSONA,
            messages=[{
                'role': 'user',
                'content': (
                    f"User asked: {message}\n\n"
                    f"Mercury's real draft: {mercury_reply}\n\n"
                    f"Saul's real compliance note: {saul_reply}\n\n"
                    "Combine these two REAL results into your final answer to the user, "
                    "following rule 8's 45-word allowance for a two-specialist chain."
                ),
            }],
        )
        text = ''.join(b.text for b in synth.content if getattr(b, 'type', None) == 'text').strip()
        return (text or CYBORG_TEMPLATE.format(msg=message)), (mercury_ok and saul_ok), consulted
    except Exception as e:
        print(f"[Ocean8 Aura] Marketing-chain synthesis failed: {e}")
        return CYBORG_TEMPLATE.format(msg=message), False, consulted


def handle_message(message, max_rounds=3):
    if _client is None:
        return CYBORG_TEMPLATE.format(msg=message), True, []

    if _looks_like_marketing_request(message):
        return _marketing_chain(message)

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
