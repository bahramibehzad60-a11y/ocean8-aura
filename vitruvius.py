# ---------------------------------------------------------------------------
# vitruvius.py
#
# Feng Shui & Bio-Architecture full-report generation + its own Flask route,
# following the same file-structure convention as faraday.py: logic and
# blueprint live together in one file.
#
# ARCHITECTURAL NOTE — read before editing VITRUVIUS_REPORT_PERSONA:
# Unlike faraday.py, this file does NOT compute anything in Python. Kua
# number, Bagua zone mapping, and Flying Star analysis follow classical
# methodology that varies somewhat by school/region, so the calculation
# itself is delegated to the model, using the well-documented Eight
# Mansions (BaZhai) system as the stated convention below.
#
# This is a placeholder until Ocean 8's own Feng Shui Handbook content is
# available to embed directly — at that point, replace the methodology
# paragraph in VITRUVIUS_REPORT_PERSONA with the handbook's exact formulas
# so every report follows your specific reference, not general convention.
#
# The draft NEVER reaches a client directly — every report goes through
# cyborg.run_full_audit() first, the same gate Faraday's reports use.
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

VITRUVIUS_REPORT_PERSONA = (
    "You are the Feng Shui & Bio-Architecture specialist inside Ocean 8 Aura, a "
    "luxury home wellness and energetic sanctuary restoration practice serving "
    "affluent homeowners across the Greater Toronto Area. Your assessments are "
    "read directly by clients.\n\n"
    "Brand voice: quiet luxury, not new-age mysticism. Write the way a trusted "
    "advisor speaks to a discerning client — precise, warm, confident, never "
    "breathless or overselling. Ground every recommendation in classical "
    "methodology, not vague intuition.\n\n"
    "Methodology: use the classical Eight Mansions (BaZhai) system for Kua "
    "number and favorable/unfavorable directions, standard compass-based Bagua "
    "zone mapping anchored to the main entrance's facing direction, and "
    "standard Flying Star (Xuan Kong) theory when the construction year is "
    "known. If any required input is missing, say so plainly rather than "
    "guessing or estimating.\n\n"
    "What you calculate:\n"
    "1. Kua number & personal trigram — from the client's birth year and gender.\n"
    "2. Four favorable / four unfavorable directions, derived from the Kua number.\n"
    "3. Bagua zone mapping — overlay the eight life-areas plus the center onto "
    "the client's floor plan.\n"
    "4. Flying Star chart — only if the property's construction or last major "
    "renovation year is known. If it isn't, state plainly that this piece is "
    "unavailable.\n"
    "5. Placement recommendations — tied specifically to the client's "
    "unfavorable zones and any flagged concern, prioritizing practical changes "
    "(furniture, mirrors, color, decluttering) over renovation-level changes.\n\n"
    "Guardrails — non-negotiable: never state or imply a feng shui adjustment "
    "will cure, treat, prevent, or diagnose any physical or mental health "
    "condition. Use 'traditionally associated with' / 'may support' / 'is "
    "intended to' — never 'will heal', 'will cure', 'will fix'. Never override "
    "medical, legal, or structural-engineering advice.\n\n"
    "Structure the report as: Kua Profile, Bagua Zone Map, Flying Star Notes "
    "(or a note that it's unavailable), and up to 5 Top Recommendations, each "
    "with a one-line 'what' and one-line 'why'. Keep it under ~600 words. "
    "Respond in whichever language the client data is written in."
)


def draft_report(client_name, property_address, birth_date, gender,
                  facing_direction, room_layout, construction_year=None):
    """Calls Claude with the Vitruvius report persona to produce a draft
    Feng Shui / Bio-Architecture report. The calculation happens inside the
    model call, not in Python — see the architectural note above. Returns
    the draft text ONLY; never sends anything. The route below is
    responsible for passing this through run_full_audit() before any
    client ever sees it."""
    if _client is None:
        return (
            f"Vitruvius Feng Shui Report — {client_name}\n"
            f"Property: {property_address}\n\n"
            "No Anthropic API client is configured — this is a placeholder, "
            "not a real assessment."
        )
    user_content = (
        f"Client: {client_name}\n"
        f"Property: {property_address}\n"
        f"Birth date: {birth_date}\n"
        f"Gender: {gender}\n"
        f"Home facing direction: {facing_direction}\n"
        f"Room layout: {room_layout}\n"
        f"Construction/renovation year: {construction_year or 'not provided'}\n\n"
        "Produce the full assessment now."
    )
    try:
        response = _client.messages.create(
            model=REPORT_MODEL,
            max_tokens=1200,
            system=VITRUVIUS_REPORT_PERSONA,
            messages=[{'role': 'user', 'content': user_content}],
        )
        text = ''.join(b.text for b in response.content if getattr(b, 'type', None) == 'text').strip()
        return text or f"Vitruvius Feng Shui Report — {client_name}\n(model returned an empty response)"
    except Exception as e:
        print(f"[Ocean8 Aura] Vitruvius draft_report failed: {e}")
        return f"Vitruvius Feng Shui Report — {client_name}\n\nDraft generation failed: {e}"


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

    draft = draft_report(client_name, property_address, birth_date, gender,
                          facing_direction, room_layout, construction_year)
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
