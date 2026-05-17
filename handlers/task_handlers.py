"""
handlers/task_handlers.py
Task creation, listing, and status update flows.
"""

import logging
from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
import database as db
from utils import (
    format_task_card, task_status_keyboard,
    avenue_keyboard, priority_keyboard,
)
from config import (
    ROLE_CORE, ROLE_DIRECTOR,
    STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_COMPLETED,
    STATUS_DELAYED, STATUS_AWAITING,
)

logger = logging.getLogger(__name__)

# ConversationHandler states
(NT_TITLE, NT_DESC, NT_AVENUE, NT_PERSON,
 NT_DEADLINE, NT_PRIORITY) = range(6)


def can_create_task(user_id: int) -> bool:
    u = db.get_user(user_id)
    return u is not None and u["role"] in (ROLE_CORE, ROLE_DIRECTOR)


# ── /newtask ──────────────────────────────────────────────────────────────────

async def newtask_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not can_create_task(update.effective_user.id):
        await update.message.reply_text(
            "🚫 Only *Core* or *Avenue Directors* can create tasks.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END
    ctx.user_data.clear()
    await update.message.reply_text(
        "📋 *New Task — Step 1/5*\n\nWhat is the *task title*?\n\n/cancel to abort.",
        parse_mode="Markdown",
    )
    return NT_TITLE


async def nt_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["title"] = update.message.text.strip()
    await update.message.reply_text(
        "📝 *Step 2/5* — Provide a *description* (or type `skip`):",
        parse_mode="Markdown",
    )
    return NT_DESC


async def nt_desc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    ctx.user_data["desc"] = "" if text.lower() == "skip" else text
    await update.message.reply_text(
        "🏢 *Step 3/5* — Select the *avenue*:",
        parse_mode="Markdown",
        reply_markup=avenue_keyboard("ntavenue"),
    )
    return NT_AVENUE


async def nt_avenue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["avenue"] = query.data.replace("ntavenue_", "")
    await query.message.reply_text(
        "🎯 *Step 4/5* — Assigned to (name or type `avenue` for whole team):",
        parse_mode="Markdown",
    )
    return NT_PERSON


async def nt_person(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["person"] = update.message.text.strip()
    await update.message.reply_text(
        "📅 *Step 5a/5* — Enter the *deadline* in `YYYY-MM-DD HH:MM` format\n"
        "Example: `2026-06-01 18:00`\n\nOr type `none` for no deadline.",
        parse_mode="Markdown",
    )
    return NT_DEADLINE


async def nt_deadline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == "none":
        ctx.user_data["deadline"] = None
    else:
        # Basic validation
        try:
            from datetime import datetime
            datetime.strptime(text, "%Y-%m-%d %H:%M")
            ctx.user_data["deadline"] = text
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid format. Use `YYYY-MM-DD HH:MM` or `none`.",
                parse_mode="Markdown",
            )
            return NT_DEADLINE

    await update.message.reply_text(
        "🎯 *Step 5b/5* — Select *priority*:",
        parse_mode="Markdown",
        reply_markup=priority_keyboard("ntpriority"),
    )
    return NT_PRIORITY


async def nt_priority(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    priority = query.data.replace("ntpriority_", "")
    user_id  = query.from_user.id
    ud       = ctx.user_data

    task_id = db.create_task(
        title=ud["title"],
        description=ud["desc"],
        assigned_to=ud["person"],
        assigned_by=user_id,
        avenue=ud["avenue"],
        deadline=ud["deadline"],
        priority=priority,
    )
    task = db.get_task(task_id)

    # Notify members of the assigned avenue
    avenue_members = db.get_users_by_avenue(ud["avenue"])
    note_text = (
        f"🔔 *New Task Assigned to {ud['avenue']}!*\n\n"
        + format_task_card(task)
    )
    for member in avenue_members:
        try:
            await ctx.bot.send_message(
                member["telegram_id"],
                note_text,
                parse_mode="Markdown",
                reply_markup=task_status_keyboard(task_id),
            )
        except Exception as e:
            logger.warning("Could not notify %s: %s", member["telegram_id"], e)

    await query.message.reply_text(
        f"✅ *Task #{task_id} Created!*\n\n" + format_task_card(task),
        parse_mode="Markdown",
        reply_markup=task_status_keyboard(task_id),
    )
    ctx.user_data.clear()
    return ConversationHandler.END


# ── /mytasks ──────────────────────────────────────────────────────────────────

async def mytasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tasks = db.get_tasks_for_user(update.effective_user.id)
    if not tasks:
        await update.message.reply_text("📭 No tasks found for your avenue.")
        return
    await update.message.reply_text(
        f"📋 *Your Tasks ({len(tasks)} total)*\n━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown",
    )
    for t in tasks[:10]:  # Batch to avoid flood
        await update.message.reply_text(
            format_task_card(t),
            parse_mode="Markdown",
            reply_markup=task_status_keyboard(t["id"]),
        )


# ── /pending ──────────────────────────────────────────────────────────────────

async def pending_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tasks = db.get_tasks_by_status(STATUS_PENDING)
    if not tasks:
        await update.message.reply_text("✅ No pending tasks!")
        return
    await update.message.reply_text(
        f"🔵 *Pending Tasks ({len(tasks)})*\n━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown",
    )
    for t in tasks[:10]:
        await update.message.reply_text(
            format_task_card(t), parse_mode="Markdown",
            reply_markup=task_status_keyboard(t["id"]),
        )


# ── /completed ────────────────────────────────────────────────────────────────

async def completed_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tasks = db.get_tasks_by_status(STATUS_COMPLETED)
    if not tasks:
        await update.message.reply_text("📭 No completed tasks yet.")
        return
    await update.message.reply_text(
        f"✅ *Completed Tasks ({len(tasks)})*\n━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown",
    )
    for t in tasks[:10]:
        await update.message.reply_text(format_task_card(t), parse_mode="Markdown")


# ── /avenuetasks ──────────────────────────────────────────────────────────────

async def avenue_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = db.get_user(update.effective_user.id)
    if not u or not u["avenue"]:
        await update.message.reply_text("⚠️ You are not assigned to an avenue yet.")
        return
    tasks = db.get_tasks_by_avenue(u["avenue"])
    if not tasks:
        await update.message.reply_text(f"📭 No tasks for *{u['avenue']}*.", parse_mode="Markdown")
        return
    await update.message.reply_text(
        f"🏢 *{u['avenue']} Tasks ({len(tasks)})*\n━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown",
    )
    for t in tasks[:10]:
        await update.message.reply_text(
            format_task_card(t), parse_mode="Markdown",
            reply_markup=task_status_keyboard(t["id"]),
        )


# ── Status callback handler ───────────────────────────────────────────────────

STATUS_MAP = {
    "task_done":  STATUS_COMPLETED,
    "task_prog":  STATUS_IN_PROGRESS,
    "task_delay": STATUS_DELAYED,
    "task_await": STATUS_AWAITING,
    "task_pend":  STATUS_PENDING,
}


async def task_status_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # e.g. "task_done_3"

    parts = data.rsplit("_", 1)
    prefix = parts[0]
    task_id = int(parts[1])

    new_status = STATUS_MAP.get(prefix)
    if not new_status:
        return

    old_task = db.get_task(task_id)
    if not old_task:
        await query.answer("Task not found.", show_alert=True)
        return

    db.update_task_status(task_id, new_status)
    task = db.get_task(task_id)

    # Notify core members of status change
    core_users = db.get_users_by_role("core")
    notify_text = (
        f"🔄 *Task Status Updated*\n\n"
        f"📋 Task #{task_id}: *{task['title']}*\n"
        f"📌 New Status: *{new_status}*\n"
        f"👤 Updated by: {query.from_user.full_name}"
    )
    for cu in core_users:
        try:
            await ctx.bot.send_message(cu["telegram_id"], notify_text, parse_mode="Markdown")
        except Exception:
            pass

    await query.edit_message_text(
        format_task_card(task),
        parse_mode="Markdown",
        reply_markup=task_status_keyboard(task_id),
    )


# ── Conversation assembly ─────────────────────────────────────────────────────

def newtask_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("newtask", newtask_start)],
        states={
            NT_TITLE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, nt_title)],
            NT_DESC:     [MessageHandler(filters.TEXT & ~filters.COMMAND, nt_desc)],
            NT_AVENUE:   [CallbackQueryHandler(nt_avenue,   pattern=r"^ntavenue_")],
            NT_PERSON:   [MessageHandler(filters.TEXT & ~filters.COMMAND, nt_person)],
            NT_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, nt_deadline)],
            NT_PRIORITY: [CallbackQueryHandler(nt_priority, pattern=r"^ntpriority_")],
        },
        fallbacks=[CommandHandler("cancel", _cancel)],
        name="newtask_conv",
    )


async def _cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Task creation cancelled.")
    return ConversationHandler.END
