# ---------------------------------------------------------------------------
# db.py
#
# Everything that touches ocean8_aura.db lives here: connecting, creating
# tables, and logging a chat interaction. main.py, agents.py, and cyborg.py
# all import log_interaction() from here instead of talking to SQLite
# directly — so if the storage engine ever changes, this is the only file
# that needs to change.
# ---------------------------------------------------------------------------
import sqlite3
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
