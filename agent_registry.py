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
