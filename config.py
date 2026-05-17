"""
config.py — Centralised configuration loader.
Reads from .env so secrets are never hard-coded in source.
"""

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")
CORE_GROUP_CHAT_ID: int | None = (
    int(os.getenv("CORE_GROUP_CHAT_ID", "0")) or None
)
DB_PATH: str = os.getenv("DB_PATH", "rotaract.db")

# ── Role constants ────────────────────────────────────────────────────────────
ROLE_CORE = "core"          # President, VP, Secretary, Treasurer, etc.
ROLE_DIRECTOR = "director"  # Avenue director
ROLE_MEMBER = "member"      # Avenue member

# ── Avenue names ─────────────────────────────────────────────────────────────
AVENUES = [
    "Technical",
    "Club Service",
    "Community Service",
    "International Service",
    "Professional Development",
    "Public Relations",
    "Media & Design",
    "Editorial",
    "Fellowship",
]

# ── Priority levels ───────────────────────────────────────────────────────────
PRIORITIES = ["Low", "Medium", "High", "Urgent"]

# ── Task statuses ─────────────────────────────────────────────────────────────
STATUS_PENDING = "Pending"
STATUS_IN_PROGRESS = "In Progress"
STATUS_COMPLETED = "Completed"
STATUS_DELAYED = "Delayed"
STATUS_AWAITING = "Awaiting Approval"

# ── Escalation thresholds (in hours) ─────────────────────────────────────────
ESCALATE_DIRECTOR_AFTER_H = 24   # Notify director after 24h overdue
ESCALATE_SECRETARY_AFTER_H = 48  # Notify secretary after 48h overdue
ESCALATE_PRESIDENT_AFTER_H = 72  # Notify president after 72h overdue
