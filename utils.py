"""
utils.py — Shared formatting & keyboard helpers.
"""

from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import pytz
from config import TIMEZONE, PRIORITIES, AVENUES, STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_COMPLETED, STATUS_DELAYED, STATUS_AWAITING


def now_ist() -> datetime:
    tz = pytz.timezone(TIMEZONE)
    return datetime.now(tz)


def format_deadline(deadline_str: str) -> str:
    """Return a human-readable deadline string with time remaining."""
    if not deadline_str:
        return "No deadline"
    try:
        tz = pytz.timezone(TIMEZONE)
        dl = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M")
        dl = tz.localize(dl)
        now = now_ist()
        diff = dl - now
        if diff.total_seconds() < 0:
            secs = abs(diff.total_seconds())
            h = int(secs // 3600)
            return f"⚠️ *OVERDUE* by {h}h"
        total_h = int(diff.total_seconds() // 3600)
        if total_h < 1:
            return f"⏰ Due in < 1 hour!"
        elif total_h < 24:
            return f"⏰ Due in {total_h}h"
        else:
            days = total_h // 24
            return f"📅 Due in {days}d {total_h % 24}h"
    except ValueError:
        return deadline_str


def status_emoji(status: str) -> str:
    return {
        STATUS_PENDING:    "🔵 Pending",
        STATUS_IN_PROGRESS:"⏳ In Progress",
        STATUS_COMPLETED:  "✅ Completed",
        STATUS_DELAYED:    "⚠️ Delayed",
        STATUS_AWAITING:   "🔄 Awaiting Approval",
    }.get(status, status)


def priority_emoji(priority: str) -> str:
    return {
        "Low":    "🟢 Low",
        "Medium": "🟡 Medium",
        "High":   "🟠 High",
        "Urgent": "🔴 Urgent",
    }.get(priority, priority)


def format_task_card(task) -> str:
    """Format a task as a rich Telegram message card."""
    return (
        f"📋 *Task #{task['id']}: {task['title']}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 {task['description'] or 'No description'}\n\n"
        f"👥 *Avenue:* {task['avenue'] or 'Unassigned'}\n"
        f"🎯 *Assigned to:* {task['assigned_to'] or 'Unassigned'}\n"
        f"📊 *Priority:* {priority_emoji(task['priority'])}\n"
        f"📌 *Status:* {status_emoji(task['status'])}\n"
        f"🕐 *Deadline:* {format_deadline(task['deadline'])}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )


def format_request_card(req) -> str:
    return (
        f"📨 *Inter-Avenue Request #{req['id']}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📤 *From:* {req['from_avenue']}\n"
        f"📥 *To:* {req['to_avenue']}\n"
        f"📝 *Details:* {req['request_description']}\n"
        f"🕐 *Deadline:* {format_deadline(req['deadline'])}\n"
        f"📌 *Status:* {status_emoji(req['status'])}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )


# ── Inline keyboards ──────────────────────────────────────────────────────────

def task_status_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Done",        callback_data=f"task_done_{task_id}"),
            InlineKeyboardButton("⏳ In Progress", callback_data=f"task_prog_{task_id}"),
        ],
        [
            InlineKeyboardButton("⚠️ Delayed",     callback_data=f"task_delay_{task_id}"),
            InlineKeyboardButton("🔄 Awaiting",    callback_data=f"task_await_{task_id}"),
        ],
        [
            InlineKeyboardButton("🔵 Pending",     callback_data=f"task_pend_{task_id}"),
        ],
    ])


def request_action_keyboard(req_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Accept",   callback_data=f"req_accept_{req_id}"),
            InlineKeyboardButton("❌ Decline",  callback_data=f"req_decline_{req_id}"),
        ],
        [
            InlineKeyboardButton("✔️ Mark Done", callback_data=f"req_done_{req_id}"),
        ],
    ])


def avenue_keyboard(callback_prefix: str = "avenue") -> InlineKeyboardMarkup:
    """Return an inline keyboard of all 9 avenues."""
    buttons = []
    for i in range(0, len(AVENUES), 2):
        row = [InlineKeyboardButton(AVENUES[i], callback_data=f"{callback_prefix}_{AVENUES[i]}")]
        if i + 1 < len(AVENUES):
            row.append(InlineKeyboardButton(AVENUES[i+1], callback_data=f"{callback_prefix}_{AVENUES[i+1]}"))
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def priority_keyboard(callback_prefix: str = "priority") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(p, callback_data=f"{callback_prefix}_{p}") for p in PRIORITIES]
    ])


def role_keyboard(callback_prefix: str = "role") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👑 Core",      callback_data=f"{callback_prefix}_core"),
            InlineKeyboardButton("🎯 Director",  callback_data=f"{callback_prefix}_director"),
            InlineKeyboardButton("👤 Member",    callback_data=f"{callback_prefix}_member"),
        ]
    ])
