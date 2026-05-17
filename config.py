"""
config.py — Centralised configuration loader.
Reads from .env locally and Railway environment variables in production.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Bot credentials ───────────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

# ── Main admin auto-bootstrap ─────────────────────────────────────────────────
# Set these in Render env vars → bot creates you as Core admin on every startup
ADMIN_TELEGRAM_ID: int = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
ADMIN_NAME: str        = os.getenv("ADMIN_NAME", "Admin")

# ── Webhook (Railway production) vs Polling (local dev) ───────────────────────
# Railway injects PORT automatically. If it's set, we use webhook mode.
WEBHOOK_URL: str   = os.getenv("WEBHOOK_URL", "")   # e.g. https://yourapp.railway.app
PORT: int          = int(os.getenv("PORT", "8443"))
WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "") # optional extra security

# ── Timezone ──────────────────────────────────────────────────────────────────
TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")

# ── Core group (optional — weekly report sent here too) ───────────────────────
CORE_GROUP_CHAT_ID: int | None = (
    int(os.getenv("CORE_GROUP_CHAT_ID", "0")) or None
)

# ── Database ──────────────────────────────────────────────────────────────────
# SQLite locally / on Railway.
# To migrate to PostgreSQL later, swap this with a connection string.
DB_PATH: str = os.getenv("DB_PATH", "rotaract.db")

# ── Role constants ────────────────────────────────────────────────────────────
ROLE_CORE     = "core"      # President, VP, Secretary, Treasurer, etc.
ROLE_DIRECTOR = "director"  # Avenue director
ROLE_MEMBER   = "member"    # Avenue member

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
STATUS_PENDING    = "Pending"
STATUS_IN_PROGRESS = "In Progress"
STATUS_COMPLETED  = "Completed"
STATUS_DELAYED    = "Delayed"
STATUS_AWAITING   = "Awaiting Approval"

# ── Escalation thresholds (hours overdue) ────────────────────────────────────
ESCALATE_DIRECTOR_AFTER_H  = 24
ESCALATE_SECRETARY_AFTER_H = 48
ESCALATE_PRESIDENT_AFTER_H = 72
