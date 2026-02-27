# backend/db.py
from pathlib import Path
import os
import sqlite3
from contextlib import contextmanager
import re
from typing import Optional

DEFAULT_DB = "data/palabria.db"

def get_db_path():
    env_db = os.getenv("DB_PATH")
    if env_db:
        p = Path(env_db)
        p.parent.mkdir(parents=True, exist_ok=True)
        return str(p)
    local_db = Path(DEFAULT_DB)
    local_db.parent.mkdir(parents=True, exist_ok=True)
    return str(local_db)

DB_PATH = get_db_path()

DDL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  role TEXT DEFAULT 'student',
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  filename TEXT,
  uploaded_at TEXT DEFAULT (datetime('now')),
  text_hash TEXT,
  original_text TEXT,
  corrected_text TEXT,
  feedback TEXT,
  FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS metrics(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL,
  metric_name TEXT NOT NULL,
  metric_value REAL,
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY(document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS usage_stats(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  event TEXT NOT NULL,
  value REAL,
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS rag_questions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_name TEXT NOT NULL,
  question TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);
"""

def init_db():
    con = sqlite3.connect(DB_PATH)
    try:
        # Check if users table has 'role' column
        try:
            con.execute("SELECT role FROM users LIMIT 1")
        except sqlite3.OperationalError:
            # Column missing, add it
            print("Migrating DB: Adding 'role' column to users table...")
            try:
                con.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'student'")
            except Exception as e:
                print(f"Migration warning: {e}")

        # Check if documents table has new columns
        try:
            con.execute("SELECT original_text FROM documents LIMIT 1")
        except sqlite3.OperationalError:
            print("Migrating DB: Adding text columns to documents table...")
            try:
                con.execute("ALTER TABLE documents ADD COLUMN original_text TEXT")
                con.execute("ALTER TABLE documents ADD COLUMN corrected_text TEXT")
                con.execute("ALTER TABLE documents ADD COLUMN feedback TEXT")
            except Exception as e:
                print(f"Migration warning: {e}")

        con.executescript(DDL)
        con.commit()
    finally:
        con.close()

@contextmanager
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA foreign_keys = ON;")
        yield con
        con.commit()
    finally:
        con.close()

_ALLOWED = re.compile(r"^[A-Za-z0-9_\-\.]{1,32}$")

def sanitize_username(username: str) -> str:
    username = (username or "").strip()
    if not username:
        raise ValueError("username vacío")
    if not _ALLOWED.match(username):
        raise ValueError("username inválido: usa letras, números, _ - . (máx 32)")
    return username

def user_exists(username: str) -> bool:
    username = sanitize_username(username)
    with db() as con:
        row = con.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        return bool(row)

def create_user(username: str, role: str = "student") -> int:
    username = sanitize_username(username)
    if role not in ["student", "professor"]:
        role = "student"
    with db() as con:
        cur = con.execute("INSERT INTO users(username, role) VALUES(?, ?)", (username, role))
        return cur.lastrowid

def get_user_id(username: str) -> Optional[int]:
    username = sanitize_username(username)
    with db() as con:
        row = con.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        return row["id"] if row else None
        
def get_user_role(username: str) -> str:
    username = sanitize_username(username)
    with db() as con:
        row = con.execute("SELECT role FROM users WHERE username=?", (username,)).fetchone()
        return row["role"] if row else "student"

def ensure_user(username: str) -> int:
    username = sanitize_username(username)
    with db() as con:
        row = con.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if row:
            return row["id"]
        cur = con.execute("INSERT INTO users(username, role) VALUES(?, 'student')", (username,))
        return cur.lastrowid

def record_usage(user_id: int, event: str, value: float | None = None):
    with db() as con:
        con.execute(
            "INSERT INTO usage_stats(user_id, event, value) VALUES(?,?,?)",
            (user_id, event, value)
        )

def record_login_ts(user_id: int, epoch_seconds: float):
    record_usage(user_id, "login_ts", float(epoch_seconds))
    record_usage(user_id, "heartbeat", float(epoch_seconds))

def close_open_session(user_id: int, now_epoch: float, idle_grace: float = 1800.0):
    with db() as con:
        row_login = con.execute("""
            SELECT id, value FROM usage_stats
            WHERE user_id=? AND event='login_ts'
            ORDER BY id DESC LIMIT 1
        """, (user_id,)).fetchone()
        if not row_login:
            return
        last_login_id = int(row_login["id"])
        start_ts = float(row_login["value"] or 0.0)

        row_sd = con.execute("""
            SELECT id FROM usage_stats
            WHERE user_id=? AND event='session_duration' AND id>? 
            ORDER BY id DESC LIMIT 1
        """, (user_id, last_login_id)).fetchone()
        if row_sd:
            return

        row_hb = con.execute("""
            SELECT value FROM usage_stats
            WHERE user_id=? AND event='heartbeat' AND id>=?
            ORDER BY id DESC LIMIT 1
        """, (user_id, last_login_id)).fetchone()
        hb_ts = float(row_hb["value"]) if row_hb and row_hb["value"] is not None else None

        end_ts = float(now_epoch)
        if hb_ts is not None and (end_ts - hb_ts) <= idle_grace + 5:
            end_ts = hb_ts

        dur = max(0.0, end_ts - start_ts)
        dur = min(max(dur, 10.0), 12 * 3600.0)

        con.execute("INSERT INTO usage_stats(user_id, event, value) VALUES(?,?,?)",
                    (user_id, "session_duration", float(dur)))
        con.execute("INSERT INTO usage_stats(user_id, event, value) VALUES(?,?,NULL)",
                    (user_id, "logout"))

def create_document(user_id: int, filename: str | None, text_hash: str | None, 
                   original_text: str | None = None, corrected_text: str | None = None, 
                   feedback: str | None = None) -> int:
    with db() as con:
        cur = con.execute(
            "INSERT INTO documents(user_id, filename, text_hash, original_text, corrected_text, feedback) VALUES(?,?,?,?,?,?)",
            (user_id, filename, text_hash, original_text, corrected_text, feedback)
        )
        return cur.lastrowid

def insert_metric(document_id: int, name: str, value: float):
    with db() as con:
        con.execute(
            "INSERT INTO metrics(document_id, metric_name, metric_value) VALUES(?,?,?)",
            (document_id, name, float(value))
        )

def get_user_overview(username: str):
    username = sanitize_username(username)
    with db() as con:
        row_docs = con.execute("""
            SELECT COUNT(*) AS docs
            FROM documents d
            JOIN users u ON u.id = d.user_id
            WHERE u.username=?
        """, (username,)).fetchone()
        total_docs = int(row_docs["docs"] if row_docs else 0)

        avg_rows = con.execute("""
            WITH latest AS (
                SELECT m.* FROM metrics m
                JOIN (
                    SELECT document_id, metric_name, MAX(id) AS max_id
                    FROM metrics GROUP BY document_id, metric_name
                ) mx ON mx.max_id = m.id
            )
            SELECT l.metric_name, AVG(l.metric_value) AS avg_value
            FROM latest l
            JOIN documents d ON d.id = l.document_id
            JOIN users u ON u.id = d.user_id
            WHERE u.username=?
            GROUP BY l.metric_name
        """, (username,)).fetchall()

        row_docs_with_tu = con.execute("""
            WITH latest_tu AS (
                SELECT m.document_id, m.metric_value
                FROM metrics m
                JOIN (
                    SELECT document_id, MAX(id) AS max_id
                    FROM metrics
                    WHERE metric_name='frases_con_tu_impersonal'
                    GROUP BY document_id
                ) mx ON mx.max_id = m.id
            )
            SELECT COUNT(DISTINCT d.id) AS docs_with_tu
            FROM documents d
            JOIN users u ON u.id = d.user_id
            LEFT JOIN latest_tu lt ON lt.document_id = d.id
            WHERE u.username=? AND COALESCE(lt.metric_value,0) > 0
        """, (username,)).fetchone()
        docs_with_tu = int(row_docs_with_tu["docs_with_tu"] if row_docs_with_tu else 0)
        docs_with_tu_percent = round((docs_with_tu * 100.0 / total_docs), 1) if total_docs > 0 else 0.0

        row_docs_no_changes = con.execute("""
            WITH latest_user_changes AS (
                SELECT m.document_id, m.metric_value
                FROM metrics m
                JOIN (
                    SELECT document_id, MAX(id) AS max_id
                    FROM metrics
                    WHERE metric_name='cambios_realizados_usuario'
                    GROUP BY document_id
                ) mx ON mx.max_id = m.id
            )
            SELECT COUNT(DISTINCT d.id) AS docs_no_changes
            FROM documents d
            JOIN users u ON u.id = d.user_id
            LEFT JOIN latest_user_changes luc ON luc.document_id = d.id
            WHERE u.username=? AND COALESCE(luc.metric_value,0) = 0
        """, (username,)).fetchone()

        docs_no_changes = int(row_docs_no_changes["docs_no_changes"] if row_docs_no_changes else 0)
        docs_no_changes_percent = round((docs_no_changes * 100.0 / total_docs), 1) if total_docs > 0 else 0.0

        usage_rows = con.execute("""
            SELECT event, COUNT(*) AS n, AVG(value) AS avg_val
            FROM usage_stats us
            JOIN users u ON u.id = us.user_id
            WHERE u.username=?
            GROUP BY event
        """, (username,)).fetchall()

        login_days_row = con.execute("""
            SELECT COUNT(DISTINCT date(us.created_at)) AS days
            FROM usage_stats us
            JOIN users u ON u.id = us.user_id
            WHERE u.username=? AND us.event='login'
        """, (username,)).fetchone()

        avg_session_row = con.execute("""
            SELECT AVG(us.value) AS avg_sec
            FROM usage_stats us
            JOIN users u ON u.id = us.user_id
            WHERE u.username=? AND us.event='session_duration'
        """, (username,)).fetchone()

        return {
            "docs": total_docs,
            "avg_metrics": {r["metric_name"]: r["avg_value"] for r in avg_rows},
            "usage": {r["event"]: {"count": r["n"], "avg": r["avg_val"]} for r in usage_rows},
            "login_days": int(login_days_row["days"] if login_days_row else 0),
            "docs_with_tu_percent": docs_with_tu_percent,
            "docs_no_changes_percent": docs_no_changes_percent,
            "avg_session_seconds": float(avg_session_row["avg_sec"] or 0.0),
        }

def get_user_weekly_activity(username: str):
    """
    Devuelve los últimos 7 días con su tiempo total de conexión (sumado)
    y una categoría de actividad.
    """
    username = sanitize_username(username)
    with db() as con:
        rows = con.execute("""
            SELECT 
                date(us.created_at) AS day,
                SUM(CASE WHEN us.event='session_duration' THEN us.value ELSE 0 END) AS total_seconds
            FROM usage_stats us
            JOIN users u ON u.id = us.user_id
            WHERE u.username=? 
              AND date(us.created_at) >= date('now', '-6 days')
            GROUP BY date(us.created_at)
            ORDER BY day ASC
        """, (username,)).fetchall()

        from datetime import datetime, timedelta
        today = datetime.utcnow().date()
        days = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
        data = []
        seconds_by_day = {r["day"]: float(r["total_seconds"] or 0) for r in rows}

        for d in days:
            secs = seconds_by_day.get(d, 0)
            if secs == 0:
                cat = "No inició sesión"
            elif secs <= 300:
                cat = "Hasta 5 min"
            elif secs <= 900:
                cat = "Hasta 15 min"
            elif secs <= 1800:
                cat = "Hasta 30 min"
            else:
                cat = "Más de 30 min"
            data.append({"day": d, "total_seconds": secs, "categoria": cat})
        return data

def get_user_documents(username: str):
    username = sanitize_username(username)
    with db() as con:
        rows = con.execute("""
            SELECT d.id, d.filename, d.uploaded_at
            FROM documents d
            JOIN users u ON u.id = d.user_id
            WHERE u.username=?
            ORDER BY d.id DESC
        """, (username,)).fetchall()
        return [dict(r) for r in rows]

def get_document_metrics(doc_id: int):
    with db() as con:
        rows = con.execute("""
            SELECT metric_name, metric_value, created_at
            FROM metrics
            WHERE document_id=?
            ORDER BY id
        """, (doc_id,)).fetchall()
        return [dict(r) for r in rows]

def delete_document(doc_id: int) -> bool:
    with db() as con:
        con.execute("DELETE FROM metrics WHERE document_id=?", (doc_id,))
        cur = con.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        return cur.rowcount > 0

def get_global_overview():
    """
    Estadísticas para el Dashboard del Profesor.
    """
    with db() as con:
        # 1. Totales Generales
        row_stats = con.execute("""
            SELECT 
                (SELECT COUNT(*) FROM users WHERE role='student') as total_students,
                (SELECT COUNT(*) FROM documents) as total_docs
        """).fetchone()

        # 2. Promedios Globales de Métricas
        avg_metrics = con.execute("""
            SELECT metric_name, AVG(metric_value) as val
            FROM metrics
            GROUP BY metric_name
        """).fetchall()
        
        # 3. Lista de Alumnos con actividad
        students = con.execute("""
            SELECT u.username, COUNT(d.id) as docs_count, MAX(d.uploaded_at) as last_upload
            FROM users u
            LEFT JOIN documents d ON u.id = d.user_id
            WHERE u.role = 'student'
            GROUP BY u.id
            ORDER BY last_upload DESC
        """).fetchall()

        return {
            "total_students": row_stats["total_students"],
            "total_docs": row_stats["total_docs"],
            "avg_metrics": {r["metric_name"]: r["val"] for r in avg_metrics},
            "students": [dict(s) for s in students]
        }


def save_rag_questions(source_name: str, questions: list) -> int:
    with db() as con:
        for q in questions:
            q_text = (q or "").strip()
            if q_text:
                con.execute(
                    "INSERT INTO rag_questions(source_name, question) VALUES(?,?)",
                    (source_name, q_text)
                )
        return len(questions)


def get_rag_questions(source_name: str) -> list:
    with db() as con:
        rows = con.execute(
            "SELECT id, question, created_at FROM rag_questions WHERE source_name=? ORDER BY id",
            (source_name,)
        ).fetchall()
        return [dict(r) for r in rows]


def delete_rag_questions(source_name: str) -> int:
    with db() as con:
        cur = con.execute("DELETE FROM rag_questions WHERE source_name=?", (source_name,))
        return cur.rowcount


def get_quiz_questions(limit: int = 3) -> list:
    """Devuelve `limit` preguntas aleatorias, cada una de un source_name distinto."""
    with db() as con:
        rows = con.execute("""
            WITH one_per_source AS (
                SELECT id, source_name, question, created_at,
                       ROW_NUMBER() OVER (PARTITION BY source_name ORDER BY RANDOM()) AS rn
                FROM rag_questions
            )
            SELECT id, source_name, question, created_at
            FROM one_per_source
            WHERE rn = 1
            ORDER BY RANDOM()
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]