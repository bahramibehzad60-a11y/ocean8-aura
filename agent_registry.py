# ===========================================================================
# FILE 1 of 2 — agent_registry.py
# This is your COMPLETE file with Faraday added. Replace the whole file.
# ===========================================================================

# ---------------------------------------------------------------------------
# agent_registry.py
#
# Single source of truth for "who exists". Just names and roles — no
# personas, no API logic, no routes. agents.py, cyborg.py, and main.py
# all import from here instead of repeating this list in three places.
# ---------------------------------------------------------------------------
AGENT_META = {
    'cyborg':  {'name': 'CYBORG',  'role': 'Central Orchestrator & Synapse Core'},
    'ikigai':  {'name': 'IKIGAI',  'role': 'Purpose & Strategic Alignment Engine'},
    'wolf':    {'name': 'WOLF',    'role': 'Market Opportunity Scanner'},
    'mercury': {'name': 'MERCURY', 'role': 'Communications & Messaging Relay'},
    'saul':    {'name': 'SAUL',    'role': 'Compliance & Legal Counsel'},
    'scrooge': {'name': 'SCROOGE', 'role': 'Financial Ledger & Budget Controller'},
    'shield':  {'name': 'SHIELD',  'role': 'Security & Access Sentinel'},
    'spider':  {'name': 'SPIDER',  'role': 'Web & Data Crawler'},
    'faraday': {'name': 'FARADAY', 'role': 'Electromagnetic Field & Sanctuary Scanner'},
}
# The 8 specialists, i.e. everyone except Cyborg. agents.py uses this to
# validate incoming agent_id path parameters.
SPECIALIST_IDS = [aid for aid in AGENT_META if aid != 'cyborg']


# ===========================================================================
# FILE 2 of 2 — agents.py
# Do NOT replace this whole file. Just add these two lines to your EXISTING
# agents.py, inside the two dicts that are already there — one line each,
# alongside the other 7 entries. Nothing else in agents.py needs to change;
# the "for _pid in SPECIALIST_PERSONAS" loop right after the dict already
# applies the language/length rule to Faraday automatically once this line
# exists.
# ===========================================================================

# --- add inside SPECIALIST_PERSONAS = { ... } ---
    'faraday': f"{_BRAND_CONTEXT} You are Faraday, the environmental field and sanctuary-score agent — precise and scientific, focused on EMF readings, Building Biology benchmarks, and translating field data into a Sanctuary Score.",

# --- add inside SPECIALIST_TEMPLATES = { ... } ---
    'faraday': 'قرائتِ «{msg}» برای محاسبه‌ی امتیازِ حریم در صف پردازش قرار گرفت.',
