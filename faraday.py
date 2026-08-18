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
# Now wired to db.py: every request creates/updates a client record (keyed
# by email), and a Clear report is permanently saved via
# save_sanctuary_report() instead of only existing in the HTTP response.
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

METRIC_LABELS = {
    'ac_magnetic_mg': 'AC magnetic field',
    'ac_electric_vm': 'AC electric field',
    'rf_microwave_uwm2': 'RF / wireless radiation',
    'dirty_electricity_gs': 'Dirty electricity',
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


def draft_report(client_name, property_address, readings):
    """Runs score -> flag -> draft narrative. Returns draft text ONLY — never
    sends anything. The route below is responsible for passing this through
    run_full_audit() before any client ever sees it."""
    score, flagged_zones, _ = score_property(readings)

    lines = [
        f"Sanctuary Score Report — {client_name}",
        f"Property: {property_address}",
        "",
        f"Overall Sanctuary Score: {score}/100",
        "",
    ]

    if not flagged_zones:
        lines.append(
            "All measured areas fell within the 'No Concern' band of the Building "
            "Biology SBM-2015 sleeping-area guidelines. No specific zones are "
            "flagged this visit."
        )
    else:
        lines.append("Flagged areas, most significant first:")
        for fz in sorted(flagged_zones, key=lambda z: CONCERN_LEVELS.index(z['concern_level']), reverse=True):
            label = METRIC_LABELS.get(fz['metric'], fz['metric'])
            lines.append(
                f"- {fz['room']}: {label} measured at {fz['value']}, in the "
                f"'{fz['concern_level'].replace('_', ' ')}' band."
            )

    lines.append("")
    lines.append(
        "This assessment follows the Building Biology SBM-2015 precautionary "
        "framework. Findings on dirty electricity specifically reflect the least "
        "scientifically established of the four measured categories and are "
        "reported with that in mind."
    )
    return "\n".join(lines)


@faraday_bp.route('/api/faraday/sanctuary-report', methods=['POST'])
def sanctuary_report():
    body = request.get_json(silent=True) or {}
    client_name = str(body.get('client_name') or '').strip()
    email = str(body.get('email') or '').strip()
    phone = str(body.get('phone') or '').strip()
    property_address = str(body.get('property_address') or '').strip()
    readings = body.get('readings') or []

    if not client_name or not email or not readings:
        return jsonify({'status': 'error', 'reply': 'client_name، email و readings الزامی هستند.'}), 400

    client_id = get_or_create_client(client_name, email, phone=phone, property_address=property_address)

    draft = draft_report(client_name, property_address, readings)
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
