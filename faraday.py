# ---------------------------------------------------------------------------
# faraday.py
#
# Sanctuary Score domain logic + its own Flask route, following the same
# pattern as cyborg.py and agents.py: logic and blueprint live together in
# one file. Takes structured EMF readings from a home visit, benchmarks
# them against the Building Biology SBM-2015 Evaluation Guidelines for
# Sleeping Areas, computes a 0-100 Sanctuary Score with flagged zones, and
# drafts a client-readable report. The draft NEVER reaches a client directly
# — every report goes through cyborg.run_full_audit() first, the same gate
# the Feng Shui reports use.
#
# LANGUAGE NOTE: unlike vitruvius.py, the report text here is built entirely
# from fixed Python templates (REPORT_STRINGS below) rather than an LLM call
# — deliberate, since the content (a score plus a flagged-room list) doesn't
# need interpretation, only correct arithmetic. But a fixed template only
# speaks one language unless it's told which one: pass language='fa' for a
# Persian-language report, defaults to 'en' for backward compatibility with
# earlier requests that didn't specify it.
#
# Wired to db.py: every request creates/updates a client record (keyed by
# email), and a Clear report is permanently saved via save_sanctuary_report().
#
# CONVENTION NOTE — read before trusting the numbers for a real client:
# ac_magnetic_mg is transcribed directly from the official SBM-2015
# sleeping-area table. ac_electric_vm and rf_microwave_uwm2 are
# reconstructed from building-biology secondary sources and are NOT
# independently confirmed against the primary document. Before this scores
# a real client report, check these three against the primary PDF:
# https://buildingbiologyinstitute.org/wp-content/uploads/2023/03/SBM_2015-v1.pdf
# dirty_electricity_gs comes from the meter manufacturers' own published
# guidance (Stetzerizer / Greenwave), not from the SBM document itself,
# since GS units are meter-specific, not part of the SBM standard.
# ---------------------------------------------------------------------------

from flask import Blueprint, request, jsonify

from cyborg import run_full_audit
from db import log_interaction, get_or_create_client, save_sanctuary_report

faraday_bp = Blueprint('faraday', __name__)

SBM_THRESHOLDS = {
    'ac_magnetic_mg':      {'no_concern': 0.2, 'slight_concern': 1.0,  'severe_concern': 5.0},
    'ac_electric_vm':      {'no_concern': 1.5, 'slight_concern': 5.0,  'severe_concern': 10.0},
    'rf_microwave_uwm2':   {'no_concern': 0.1, 'slight_concern': 10.0, 'severe_concern': 1000.0},
    'dirty_electricity_gs':{'no_concern': 25.0,'slight_concern': 50.0,'severe_concern': 100.0},
}
# Anything above severe_concern's value falls into extreme_concern.

CONCERN_LEVELS = ['no_concern', 'slight_concern', 'severe_concern', 'extreme_concern']
CONCERN_PENALTY = {'no_concern': 0, 'slight_concern': 3, 'severe_concern': 8, 'extreme_concern': 15}

REPORT_STRINGS = {
    'en': {
        'title': 'Sanctuary Score Report — {client}',
        'property': 'Property: {address}',
        'score': 'Overall Sanctuary Score: {score}/100',
        'all_clear': (
            "All measured areas fell within the 'No Concern' band of the Building "
            "Biology SBM-2015 sleeping-area guidelines. No specific zones are "
            "flagged this visit."
        ),
        'flagged_header': 'Flagged areas, most significant first:',
        'flagged_line': "- {room}: {label} measured at {value}, in the '{level}' band.",
        'disclaimer': (
            "This assessment follows the Building Biology SBM-2015 precautionary "
            "framework. Findings on dirty electricity specifically reflect the least "
            "scientifically established of the four measured categories and are "
            "reported with that in mind."
        ),
        'levels': {
            'no_concern': 'no concern',
            'slight_concern': 'slight concern',
            'severe_concern': 'severe concern',
            'extreme_concern': 'extreme concern',
        },
        'metrics': {
            'ac_magnetic_mg': 'AC magnetic field',
            'ac_electric_vm': 'AC electric field',
            'rf_microwave_uwm2': 'RF / wireless radiation',
            'dirty_electricity_gs': 'Dirty electricity',
        },
    },
    'fa': {
        'title': 'گزارشِ امتیازِ حریم — {client}',
        'property': 'ملک: {address}',
        'score': 'امتیازِ کلیِ حریم: {score}/100',
        'all_clear': (
            "همه‌ی مناطقِ اندازه‌گیری‌شده در محدوده‌ی «بدونِ نگرانی»ِ دستورالعمل‌های "
            "Building Biology SBM-2015 قرار داشتند. هیچ منطقه‌ی خاصی در این بازدید "
            "پرچم‌گذاری نشده است."
        ),
        'flagged_header': 'مناطقِ پرچم‌خورده، از مهم‌ترین:',
        'flagged_line': "- {room}: {label} با مقدارِ {value}، در محدوده‌ی «{level}».",
        'disclaimer': (
            "این ارزیابی بر اساسِ چارچوبِ احتیاطیِ Building Biology SBM-2015 انجام "
            "شده است. یافته‌های مربوط به الکتریسیته‌ی کثیف، به‌طورِ خاص، کم‌تأییدشده‌ترین "
            "دسته از میانِ چهار دسته‌ی اندازه‌گیری‌شده است و با همین ملاحظه گزارش می‌شود."
        ),
        'levels': {
            'no_concern': 'بدون نگرانی',
            'slight_concern': 'نگرانیِ خفیف',
            'severe_concern': 'نگرانیِ جدی',
            'extreme_concern': 'نگرانیِ حاد',
        },
        'metrics': {
            'ac_magnetic_mg': 'میدانِ مغناطیسیِ متناوب',
            'ac_electric_vm': 'میدانِ الکتریکیِ متناوب',
            'rf_microwave_uwm2': 'امواجِ رادیویی/بی‌سیم',
            'dirty_electricity_gs': 'الکتریسیته‌ی کثیف',
        },
    },
}


def _classify(value, thresholds):
    if value is None:
        return None  # not measured in this room — skip, never penalize a gap
    if value <= thresholds['no_concern']:
        return 'no_concern'
    if value <= thresholds['slight_concern']:
        return 'slight_concern'
    if value <= thresholds['severe_concern']:
        return 'severe_concern'
    return 'extreme_concern'


def score_property(readings):
    """readings: list of per-room dicts, each with a 'room' name and up to
    four optional metric keys matching SBM_THRESHOLDS. Missing metrics are
    skipped, not penalized — a room lacking a Stetzerizer reading shouldn't
    score worse than one where it was actually measured clean.
    Returns (score, flagged_zones, metric_breakdown)."""
    score = 100
    flagged_zones = []
    metric_breakdown = []

    for room_reading in readings:
        room = room_reading.get('room', 'Unnamed area')
        for metric, thresholds in SBM_THRESHOLDS.items():
            value = room_reading.get(metric)
            level = _classify(value, thresholds)
            if level is None:
                continue
            metric_breakdown.append({'room': room, 'metric': metric, 'value': value, 'concern_level': level})
            score -= CONCERN_PENALTY[level]
            if level != 'no_concern':
                flagged_zones.append({'room': room, 'metric': metric, 'concern_level': level, 'value': value})

    return max(0, min(100, score)), flagged_zones, metric_breakdown


def draft_report(client_name, property_address, readings, language='en'):
    """Runs score -> flag -> draft narrative, in the requested language
    (falls back to English for anything not in REPORT_STRINGS). Returns
    draft text ONLY — never sends anything. The route below is responsible
    for passing this through run_full_audit() before any client ever sees it."""
    if language not in REPORT_STRINGS:
        language = 'en'
    s = REPORT_STRINGS[language]

    score, flagged_zones, _ = score_property(readings)

    lines = [
        s['title'].format(client=client_name),
        s['property'].format(address=property_address),
        "",
        s['score'].format(score=score),
        "",
    ]

    if not flagged_zones:
        lines.append(s['all_clear'])
    else:
        lines.append(s['flagged_header'])
        for fz in sorted(flagged_zones, key=lambda z: CONCERN_LEVELS.index(z['concern_level']), reverse=True):
            label = s['metrics'].get(fz['metric'], fz['metric'])
            level_label = s['levels'].get(fz['concern_level'], fz['concern_level'])
            lines.append(s['flagged_line'].format(room=fz['room'], label=label, value=fz['value'], level=level_label))

    lines.append("")
    lines.append(s['disclaimer'])
    return "\n".join(lines)


@faraday_bp.route('/api/faraday/sanctuary-report', methods=['POST'])
def sanctuary_report():
    body = request.get_json(silent=True) or {}
    client_name = str(body.get('client_name') or '').strip()
    email = str(body.get('email') or '').strip()
    phone = str(body.get('phone') or '').strip()
    property_address = str(body.get('property_address') or '').strip()
    readings = body.get('readings') or []
    language = str(body.get('language') or 'en').strip().lower()

    if not client_name or not email or not readings:
        return jsonify({'status': 'error', 'reply': 'client_name، email و readings الزامی هستند.'}), 400

    client_id = get_or_create_client(client_name, email, phone=phone, property_address=property_address)

    draft = draft_report(client_name, property_address, readings, language=language)
    status, flagged, suggested, ok = run_full_audit(draft, 'sanctuary_score')
    log_interaction('faraday', f'report request for {client_name}', draft, ok=1 if ok else 0)

    if status == 'Clear':
        score, flagged_zones, _ = score_property(readings)
        report_id = save_sanctuary_report(client_id, property_address, score, flagged_zones, readings, draft, status)
        return jsonify({
            'status': 'success',
            'agent': 'faraday',
            'audit_status': status,
            'report': draft,
            'client_id': client_id,
            'report_id': report_id,
        })

    return jsonify({
        'status': 'held',
        'agent': 'faraday',
        'audit_status': status,
        'flagged': flagged,
        'suggested': suggested,
        'draft': draft,
        'client_id': client_id,
    }), 202
