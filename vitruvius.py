# ---------------------------------------------------------------------------
# vitruvius.py
#
# Feng Shui & Bio-Architecture full-report generation + its own Flask route,
# following the same file-structure convention as faraday.py: logic and
# blueprint live together in one file.
#
# ARCHITECTURAL NOTE:
# Kua number, group, trigram, and favorable/unfavorable directions are all
# computed in Python (calculate_kua + KUA_TRIGRAMS below) — deterministic,
# not left to the model. The Kua Profile section of the report is built as
# a literal Python string and the model is instructed to insert it VERBATIM,
# not paraphrase it. This is deliberately stricter than just "telling" the
# model the verified number: an earlier version did that and the model
# still silently recomputed its own Kua number using a different (also
# real, but different) convention — same East/West group, so the favorable/
# unfavorable directions still matched and the error wasn't obvious at a
# glance, but the stated number and trigram were wrong. _kua_number_present()
# below is a second line of defense that checks the model actually kept the
# verified number in its output.
#
# Bagua zone mapping onto an actual floor plan, Flying Star analysis, and
# recommendations stay model-generated, since those genuinely require
# interpretation, not just arithmetic.
#
# CONVENTION NOTE — read before trusting the numbers for a real client:
# calculate_kua sums ALL FOUR digits of the birth year (e.g. 1988 ->
# 1+9+8+8=26 -> 2+6=8), matching the convention this system already
# produced and had reviewed in an earlier live test. A second convention
# exists in circulation (summing only the last two digits), which gives
# DIFFERENT Kua numbers for the same birth year. If Ocean 8's own reference
# handbook specifies that version, update calculate_kua to match it exactly.
#
# The draft NEVER reaches a client directly — every report goes through
# cyborg.run_full_audit() first, the same gate Faraday's reports use — but
# only AFTER passing the Kua-number sanity check, since a wrong number is a
# factual-accuracy bug, not a compliance issue, and SAUL isn't checking for it.
# ---------------------------------------------------------------------------

from flask import Blueprint, request, jsonify
from anthropic import Anthropic
import os

from cyborg import run_full_audit
from db import log_interaction

vitruvius_bp = Blueprint('vitruvius', __name__)

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
_client = Anthropic(api_key=ANTHROPIC_API_KEY, timeout=30.0) if ANTHROPIC_API_KEY else None

REPORT_MODEL = 'claude-haiku-4-5-20251001'

EAST_GROUP = {1, 3, 4, 9}

KUA_TRIGRAMS = {
    1: {'name_en': 'Kan (Water)',    'symbol': '\u2635', 'element': 'Water'},
    2: {'name_en': 'Kun (Earth)',    'symbol': '\u2637', 'element': 'Earth'},
    3: {'name_en': 'Zhen (Thunder)', 'symbol': '\u2633', 'element': 'Wood'},
    4: {'name_en': 'Xun (Wind)',     'symbol': '\u2634', 'element': 'Wood'},
    6: {'name_en': 'Qian (Heaven)',  'symbol': '\u2630', 'element': 'Metal'},
    7: {'name_en': 'Dui (Lake)',     'symbol': '\u2631', 'element': 'Metal'},
    8: {'name_en': 'Gen (Mountain)', 'symbol': '\u2636', 'element': 'Earth'},
    9: {'name_en': 'Li (Fire)',      'symbol': '\u2632', 'element': 'Fire'},
}


def calculate_kua(birth_year, gender):
    """Returns (kua_number, group, favorable_directions, unfavorable_directions).
    Deterministic Eight Mansions (BaZhai) calculation — see the convention
    note at the top of this file before relying on it for a real client."""
    digit_sum = sum(int(d) for d in str(birth_year))
    while digit_sum > 9:
        digit_sum = sum(int(d) for d in str(digit_sum))

    gender_norm = (gender or '').strip().lower()
    is_female = gender_norm in ('f', 'female', 'زن', 'خانم', 'مونث')

    if birth_year >= 2000:
        kua = (digit_sum + 6) if is_female else (9 - digit_sum)
    else:
        kua = (digit_sum + 5) if is_female else (10 - digit_sum)

    while kua > 9:
        kua = sum(int(d) for d in str(kua))
    if kua == 0:
        kua = 9
    if kua == 5:
        kua = 8 if is_female else 2

    if kua in EAST_GROUP:
        group = 'East'
        favorable = ['East', 'Southeast', 'South', 'North']
        unfavorable = ['West', 'Northwest', 'Southwest', 'Northeast']
    else:
        group = 'West'
        favorable = ['West', 'Northwest', 'Southwest', 'Northeast']
        unfavorable = ['East', 'Southeast', 'South', 'North']

    return kua, group, favorable, unfavorable


def _build_kua_profile_block(kua, group, favorable, unfavorable):
    """Builds the Kua Profile section as a fixed, literal string. The model
    is instructed to insert this verbatim rather than compose it, so there
    is nothing left for it to "helpfully" recompute or rephrase."""
    t = KUA_TRIGRAMS[kua]
    return (
        "## Kua Profile\n\n"
        f"Kua number: {kua} ({group} group)\n"
        f"Personal trigram: {t['symbol']} {t['name_en']}\n"
        f"Element: {t['element']}\n\n"
        f"Favorable directions: {', '.join(favorable)}\n"
        f"Unfavorable directions: {', '.join(unfavorable)}"
    )


def _kua_number_present(draft_text, kua):
    """Sanity check: does the model's draft literally contain the verified
    Kua number? Catches the model silently recomputing its own number
    instead of using the fixed block it was given — a factual-accuracy
    bug, checked separately from (and before) the SAUL compliance audit."""
    return str(kua) in draft_text


VITRUVIUS_REPORT_PERSONA = (
    "You are the Feng Shui & Bio-Architecture specialist inside Ocean 8 Aura, a "
    "luxury home wellness and energetic sanctuary restoration practice serving "
    "affluent homeowners across the Greater Toronto Area. Your assessments are "
    "read directly by clients.\n\n"
    "Brand voice: quiet luxury, not new-age mysticism. Write the way a trusted "
    "advisor speaks to a discerning client — precise, warm, confident, never "
    "breathless or overselling. Ground every recommendation in classical "
    "methodology, not vague intuition.\n\n"
    "CRITICAL: the user message will include a Kua Profile block that was "
    "computed in Python. You MUST insert that block verbatim, character-for-"
    "character, unchanged, as the Kua Profile section of your report. Do not "
    "paraphrase it, translate the numbers, recompute anything in it, or "
    "'correct' it — even if it looks inconsistent with your own general "
    "knowledge of feng shui. The Python calculation is authoritative.\n\n"
    "Around that fixed block, you produce:\n"
    "1. One line, in your own words, on what the Kua Profile means "
    "practically for the client.\n"
    "2. Bagua zone mapping — overlay the eight life-areas plus the center "
    "onto the client's floor plan as described, anchored to the main "
    "entrance's facing direction.\n"
    "3. Flying Star chart — only if the property's construction or last "
    "major renovation year is known. If it isn't, state plainly that this "
    "piece is unavailable rather than estimating it.\n"
    "4. Placement recommendations — up to 5, tied specifically to the "
    "client's unfavorable zones and any flagged concern, prioritizing "
    "practical changes (furniture, mirrors, color, decluttering) over "
    "renovation-level changes.\n\n"
    "Guardrails — non-negotiable: never state or imply a feng shui adjustment "
    "will cure, treat, prevent, or diagnose any physical or mental health "
    "condition, and never claim a direct causal effect on cognitive or "
    "professional outcomes (e.g. 'this will improve your focus/career'). Use "
    "'traditionally associated with' / 'may support' / 'is intended to' / "
    "'aligns with traditional feng shui principles' — never a bare causal "
    "claim. Never override medical, legal, or structural-engineering advice.\n\n"
    "Structure the report as: Kua Profile (the fixed block), Bagua Zone Map, "
    "Flying Star Notes (or a note that it's unavailable), and Top "
    "Recommendations. Keep it under ~600 words. Respond in whichever "
    "language the client data is written in."
)


def draft_report(client_name, property_address, birth_date, gender,
                  facing_direction, room_layout, construction_year=None):
    """Computes the Kua profile in Python (deterministic), then calls Claude
    with that fixed block plus the qualitative inputs to produce the full
    narrative report. Returns (draft_text, kua, kua_ok). kua_ok is True if
    no birth year was given (nothing to validate) or if the verified number
    actually appears in the model's draft; False if the model likely
    recomputed its own. Never sends anything — the route below is
    responsible for that, after checking kua_ok and passing run_full_audit()."""
    try:
        birth_year = int(str(birth_date).strip()[:4])
    except (ValueError, TypeError):
        birth_year = None

    kua = None
    kua_profile_block = "No valid birth year was provided — Kua profile cannot be computed."
    if birth_year:
        kua, group, favorable, unfavorable = calculate_kua(birth_year, gender)
        kua_profile_block = _build_kua_profile_block(kua, group, favorable, unfavorable)

    if _client is None:
        text = (
            f"Vitruvius Feng Shui Report — {client_name}\n"
            f"Property: {property_address}\n\n{kua_profile_block}\n\n"
            "No Anthropic API client is configured — this is a placeholder, "
            "not a real assessment."
        )
        return text, kua, True

    user_content = (
        f"Client: {client_name}\n"
        f"Property: {property_address}\n"
        f"Home facing direction: {facing_direction}\n"
        f"Room layout: {room_layout}\n"
        f"Construction/renovation year: {construction_year or 'not provided'}\n\n"
        f"Insert this EXACT block verbatim as your Kua Profile section:\n\n"
        f"{kua_profile_block}\n\n"
        "Now write the rest of the report around this fixed block, in the "
        "client's language."
    )
    try:
        response = _client.messages.create(
            model=REPORT_MODEL,
            max_tokens=1200,
            temperature=0,
            system=VITRUVIUS_REPORT_PERSONA,
            messages=[{'role': 'user', 'content': user_content}],
        )
        text = ''.join(b.text for b in response.content if getattr(b, 'type', None) == 'text').strip()
        if not text:
            return f"Vitruvius Feng Shui Report — {client_name}\n(model returned an empty response)", kua, False
        kua_ok = (kua is None) or _kua_number_present(text, kua)
        if not kua_ok:
            print(f"[Ocean8 Aura] Vitruvius: draft did NOT contain verified Kua number {kua} — likely recomputed independently")
        return text, kua, kua_ok
    except Exception as e:
        print(f"[Ocean8 Aura] Vitruvius draft_report failed: {e}")
        return f"Vitruvius Feng Shui Report — {client_name}\n\nDraft generation failed: {e}", kua, False


@vitruvius_bp.route('/api/vitruvius/feng-shui-report', methods=['POST'])
def feng_shui_report():
    body = request.get_json(silent=True) or {}
    client_name = str(body.get('client_name') or '').strip()
    property_address = str(body.get('property_address') or '').strip()
    birth_date = str(body.get('birth_date') or '').strip()
    gender = str(body.get('gender') or '').strip()
    facing_direction = str(body.get('facing_direction') or '').strip()
    room_layout = str(body.get('room_layout') or '').strip()
    construction_year = body.get('construction_year')

    if not client_name or not birth_date or not gender or not facing_direction or not room_layout:
        return jsonify({
            'status': 'error',
            'reply': 'client_name، birth_date، gender، facing_direction و room_layout الزامی هستند.'
        }), 400

    draft, kua, kua_ok = draft_report(client_name, property_address, birth_date, gender,
                                       facing_direction, room_layout, construction_year)

    if kua is not None and not kua_ok:
        log_interaction('vitruvius', f'report request for {client_name}', draft, ok=0)
        return jsonify({
            'status': 'held',
            'agent': 'vitruvius',
            'audit_status': 'Needs Human Review',
            'flagged': f'Model draft did not contain the verified Kua number ({kua}) — likely recomputed it independently. Factual-accuracy issue, caught before the compliance check.',
            'suggested': 'n/a',
            'draft': draft,
        }), 202

    status, flagged, suggested, ok = run_full_audit(draft, 'feng_shui')
    log_interaction('vitruvius', f'report request for {client_name}', draft, ok=1 if ok else 0)

    if status == 'Clear':
        return jsonify({'status': 'success', 'agent': 'vitruvius', 'audit_status': status, 'report': draft})

    return jsonify({
        'status': 'held',
        'agent': 'vitruvius',
        'audit_status': status,
        'flagged': flagged,
        'suggested': suggested,
        'draft': draft,
    }), 202
