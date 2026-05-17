"""
database.py — SQLite layer for the Rotaract Telegram Bot.

Tables:
  users      — registered Telegram users with roles
  avenues    — the 9 club avenues
  tasks      — tasks with assignments, deadlines & status
  requests   — inter-avenue work requests
  reports    — weekly auto-generated report snapshots
"""

import sqlite3
import logging
from datetime import datetime
from typing import Optional
from config import DB_PATH

logger = logging.getLogger(__name__)


# ── Connection helper ─────────────────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ── Schema initialisation ─────────────────────────────────────────────────────

def init_db() -> None:
    """Create all tables if they do not already exist."""
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS avenues (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            avenue_name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            name        TEXT    NOT NULL,
            username    TEXT,
            role        TEXT    NOT NULL DEFAULT 'member',
            avenue      TEXT,
            permissions TEXT    DEFAULT '',
            joined_at   TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            title        TEXT NOT NULL,
            description  TEXT,
            assigned_to  TEXT,
            assigned_by  INTEGER REFERENCES users(telegram_id),
            avenue       TEXT,
            deadline     TEXT,
            priority     TEXT NOT NULL DEFAULT 'Medium',
            status       TEXT NOT NULL DEFAULT 'Pending',
            created_at   TEXT DEFAULT (datetime('now')),
            updated_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS requests (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            from_avenue         TEXT NOT NULL,
            to_avenue           TEXT NOT NULL,
            request_description TEXT NOT NULL,
            deadline            TEXT,
            status              TEXT NOT NULL DEFAULT 'Pending',
            requested_by        INTEGER REFERENCES users(telegram_id),
            created_at          TEXT DEFAULT (datetime('now')),
            updated_at          TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS reports (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_date TEXT DEFAULT (datetime('now')),
            summary        TEXT,
            statistics     TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id   INTEGER REFERENCES users(telegram_id),
            avenue      TEXT,
            message     TEXT,
            file_id     TEXT,
            file_type   TEXT,
            sent_at     TEXT DEFAULT (datetime('now'))
        );
        """)
        _seed_avenues(conn)
    logger.info("Database initialised at %s", DB_PATH)


def _seed_avenues(conn: sqlite3.Connection) -> None:
    """Insert the 9 default avenues if they don't exist."""
    from config import AVENUES
    for av in AVENUES:
        conn.execute(
            "INSERT OR IGNORE INTO avenues (avenue_name) VALUES (?)", (av,)
        )


# ── User helpers ──────────────────────────────────────────────────────────────

def add_user(telegram_id: int, name: str, username: str,
             role: str = "member", avenue: str = None) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO users (telegram_id, name, username, role, avenue)
               VALUES (?, ?, ?, ?, ?)""",
            (telegram_id, name, username, role, avenue)
        )


def get_user(telegram_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()


def get_all_users() -> list:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users ORDER BY role, name").fetchall()


def update_user_role(telegram_id: int, role: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET role = ? WHERE telegram_id = ?", (role, telegram_id)
        )


def update_user_avenue(telegram_id: int, avenue: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET avenue = ? WHERE telegram_id = ?", (avenue, telegram_id)
        )


def remove_user(telegram_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))


def get_users_by_role(role: str) -> list:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE role = ?", (role,)
        ).fetchall()


def get_users_by_avenue(avenue: str) -> list:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE avenue = ?", (avenue,)
        ).fetchall()


def get_avenue_director(avenue: str) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE avenue = ? AND role = 'director' LIMIT 1",
            (avenue,)
        ).fetchone()


# ── Task helpers ──────────────────────────────────────────────────────────────

def create_task(title: str, description: str, assigned_to: str,
                assigned_by: int, avenue: str, deadline: str,
                priority: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO tasks (title, description, assigned_to, assigned_by,
               avenue, deadline, priority)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (title, description, assigned_to, assigned_by, avenue, deadline, priority)
        )
        return cur.lastrowid


def get_task(task_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()


def get_all_tasks() -> list:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM tasks ORDER BY deadline ASC"
        ).fetchall()


def get_tasks_by_avenue(avenue: str) -> list:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM tasks WHERE avenue = ? ORDER BY deadline ASC",
            (avenue,)
        ).fetchall()


def get_tasks_by_status(status: str) -> list:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM tasks WHERE status = ? ORDER BY deadline ASC",
            (status,)
        ).fetchall()


def get_tasks_for_user(telegram_id: int) -> list:
    with get_conn() as conn:
        user = get_user(telegram_id)
        if not user:
            return []
        if user["role"] == "core":
            return get_all_tasks()
        return conn.execute(
            "SELECT * FROM tasks WHERE avenue = ? ORDER BY deadline ASC",
            (user["avenue"],)
        ).fetchall()


def update_task_status(task_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE tasks SET status = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (status, task_id)
        )


def get_overdue_tasks() -> list:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_conn() as conn:
        return conn.execute(
            """SELECT * FROM tasks
               WHERE status NOT IN ('Completed', 'Awaiting Approval')
               AND deadline IS NOT NULL
               AND deadline < ?""",
            (now,)
        ).fetchall()


def get_upcoming_deadline_tasks(hours: int) -> list:
    """Tasks whose deadline is within the next `hours` hours."""
    from datetime import timedelta
    now = datetime.now()
    cutoff = (now + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")
    now_str = now.strftime("%Y-%m-%d %H:%M")
    with get_conn() as conn:
        return conn.execute(
            """SELECT * FROM tasks
               WHERE status NOT IN ('Completed', 'Awaiting Approval')
               AND deadline IS NOT NULL
               AND deadline BETWEEN ? AND ?""",
            (now_str, cutoff)
        ).fetchall()


# ── Request helpers ───────────────────────────────────────────────────────────

def create_request(from_avenue: str, to_avenue: str,
                   description: str, deadline: str,
                   requested_by: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO requests
               (from_avenue, to_avenue, request_description, deadline, requested_by)
               VALUES (?, ?, ?, ?, ?)""",
            (from_avenue, to_avenue, description, deadline, requested_by)
        )
        return cur.lastrowid


def get_request(req_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM requests WHERE id = ?", (req_id,)
        ).fetchone()


def get_requests_for_avenue(avenue: str) -> list:
    with get_conn() as conn:
        return conn.execute(
            """SELECT * FROM requests
               WHERE to_avenue = ? OR from_avenue = ?
               ORDER BY created_at DESC""",
            (avenue, avenue)
        ).fetchall()


def update_request_status(req_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE requests SET status = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (status, req_id)
        )


# ── Message log helpers ───────────────────────────────────────────────────────

def log_message(sender_id: int, avenue: str, message: str,
                file_id: str = None, file_type: str = None) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO messages (sender_id, avenue, message, file_id, file_type)
               VALUES (?, ?, ?, ?, ?)""",
            (sender_id, avenue, message, file_id, file_type)
        )


# ── Report helpers ────────────────────────────────────────────────────────────

def save_report(summary: str, statistics: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO reports (summary, statistics) VALUES (?, ?)",
            (summary, statistics)
        )


def get_weekly_stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        completed = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'Completed'"
        ).fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'Pending'"
        ).fetchone()[0]
        in_progress = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'In Progress'"
        ).fetchone()[0]
        delayed = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'Delayed'"
        ).fetchone()[0]

        # Per-avenue stats
        avenue_rows = conn.execute(
            """SELECT avenue, COUNT(*) as total,
               SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) as done
               FROM tasks WHERE avenue IS NOT NULL
               GROUP BY avenue ORDER BY done DESC"""
        ).fetchall()

        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "in_progress": in_progress,
            "delayed": delayed,
            "avenues": [dict(r) for r in avenue_rows],
        }
