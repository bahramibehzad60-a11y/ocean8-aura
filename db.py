# ---------------------------------------------------------------------------
# db.py
#
# Everything that touches ocean8_aura.db lives here: connecting, creating
# tables, and logging a chat interaction. main.py, agents.py, and cyborg.py
# all import log_interaction() from here instead of talking to SQLite
# directly — so if the storage engine ever changes, this is the only file
# that needs to change.
#
# Three new tables added alongside the original agent_logs/products:
#   clients            — one row per client, filled by the online intake form
#   sanctuary_reports   — Faraday's reports, linked to a client, one row per visit
#   feng_shui_reports   — Vitruvius's reports, same pattern
# A client can have many reports over time (repeat visits) — that's the
# whole point of client_id being a foreign key rather than embedding
# report data directly on the clients row.
#
# NOTE: faraday.py and vitruvius.py do not call save_sanctuary_report() /
# save_feng_shui_report() yet — right now a "Clear" report is returned in
# the HTTP response and then lost. Wiring those two calls in is the next
# step after this file is live.
# ---------------------------------------------------------------------------
import sqlite3
import json
from datetime import datetime
DB_PATH = 'ocean8_aura.db'
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS agent_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            agent_name TEXT NOT NULL DEFAULT 'cyborg',
            message TEXT NOT NULL,
            response TEXT NOT NULL,
            ok INTEGER NOT NULL DEFAULT 1
        )
    ''')
    # Migrate pre-existing databases that predate the agent_name/ok columns,
    # so an already-deployed ocean8_aura.db upgrades in place instead of
    # crashing on the first chat message.
    existing_cols = {row['name'] for row in conn.execute('PRAGMA table_info(agent_logs)').fetchall()}
    if 'agent_name' not in existing_cols:
        conn.execute("ALTER TABLE agent_logs ADD COLUMN agent_name TEXT NOT NULL DEFAULT 'cyborg'")
    if 'ok' not in existing_cols:
        conn.execute('ALTER TABLE agent_logs ADD COLUMN ok INTEGER NOT NULL DEFAULT 1')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Active'
        )
    ''')
    if conn.execute('SELECT COUNT(*) FROM products').fetchone()[0] == 0:
        conn.executemany(
            'INSERT INTO products (name, category, status) VALUES (?,?,?)',
            [
                ('Smart Aroma Diffuser V1', 'Hardware / Smart Device', 'Active'),
                ('Aura Cleansing Essence', 'Liquid / Wellness', 'Ready'),
            ]
        )

    conn.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL DEFAULT '',
            property_address TEXT NOT NULL DEFAULT '',
            birth_date TEXT NOT NULL DEFAULT '',
            gender TEXT NOT NULL DEFAULT ''
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS sanctuary_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            property_address TEXT NOT NULL DEFAULT '',
            score INTEGER,
            flagged_zones TEXT NOT NULL DEFAULT '[]',
            raw_readings TEXT NOT NULL DEFAULT '[]',
            report_text TEXT NOT NULL DEFAULT '',
            audit_status TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (client_id) REFERENCES clients (id)
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS feng_shui_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            property_address TEXT NOT NULL DEFAULT '',
            kua_number INTEGER,
            kua_group TEXT NOT NULL DEFAULT '',
            facing_direction TEXT NOT NULL DEFAULT '',
            room_layout TEXT NOT NULL DEFAULT '',
            construction_year INTEGER,
            report_text TEXT NOT NULL DEFAULT '',
            audit_status TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (client_id) REFERENCES clients (id)
        )
    ''')

    conn.commit()
    conn.close()
def log_interaction(agent_name, message, response, ok=1):
    conn = get_db()
    conn.execute(
        'INSERT INTO agent_logs (timestamp, agent_name, message, response, ok) VALUES (?,?,?,?,?)',
        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), agent_name, message, response, ok)
    )
    conn.commit()
    conn.close()


def get_or_create_client(name, email, phone='', property_address='', birth_date='', gender=''):
    """Looks up a client by email; if found, updates only the fields that
    were actually provided (non-empty) -- so a later call with partial info
    (e.g. a Sanctuary Score request, which has no birth_date/gender) never
    wipes out data an earlier call already stored. Creates a new record if
    no client with this email exists yet. Returns the client's id either way."""
    conn = get_db()
    existing = conn.execute('SELECT * FROM clients WHERE email = ?', (email,)).fetchone()
    if existing:
        client_id = existing['id']
        conn.execute(
            'UPDATE clients SET name=?, phone=?, property_address=?, birth_date=?, gender=? WHERE id=?',
            (
                name or existing['name'],
                phone or existing['phone'],
                property_address or existing['property_address'],
                birth_date or existing['birth_date'],
                gender or existing['gender'],
                client_id,
            )
        )
    else:
        cur = conn.execute(
            'INSERT INTO clients (created_at, name, email, phone, property_address, birth_date, gender) VALUES (?,?,?,?,?,?,?)',
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), name, email, phone, property_address, birth_date, gender)
        )
        client_id = cur.lastrowid
    conn.commit()
    conn.close()
    return client_id


def save_sanctuary_report(client_id, property_address, score, flagged_zones, raw_readings, report_text, audit_status):
    """flagged_zones and raw_readings are Python lists/dicts — stored as
    JSON text since SQLite has no native array type. Returns the new report's id."""
    conn = get_db()
    cur = conn.execute(
        'INSERT INTO sanctuary_reports (client_id, created_at, property_address, score, flagged_zones, raw_readings, report_text, audit_status) VALUES (?,?,?,?,?,?,?,?)',
        (
            client_id,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            property_address,
            score,
            json.dumps(flagged_zones, ensure_ascii=False),
            json.dumps(raw_readings, ensure_ascii=False),
            report_text,
            audit_status,
        )
    )
    conn.commit()
    conn.close()
    return cur.lastrowid


def save_feng_shui_report(client_id, property_address, kua_number, kua_group, facing_direction,
                           room_layout, construction_year, report_text, audit_status):
    """Returns the new report's id."""
    conn = get_db()
    cur = conn.execute(
        'INSERT INTO feng_shui_reports (client_id, created_at, property_address, kua_number, kua_group, '
        'facing_direction, room_layout, construction_year, report_text, audit_status) VALUES (?,?,?,?,?,?,?,?,?,?)',
        (
            client_id,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            property_address,
            kua_number,
            kua_group,
            facing_direction,
            room_layout,
            construction_year,
            report_text,
            audit_status,
        )
    )
    conn.commit()
    conn.close()
    return cur.lastrowid
