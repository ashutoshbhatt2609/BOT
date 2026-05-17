"""
handlers/task_handlers.py
Task creation (Core only), listing, claim, and status update flows.

Rules:
  - Only CORE can create and assign tasks to avenues.
  - Tasks are assigned to an AVENUE as a whole — no pre-assigned person.
  - Any avenue member can CLAIM a task (tap "Take Task" button).
  - Claiming sets assigned_to = member name + status = In Progress.
"""

import logging
from datetime import datetime
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
    ROLE_CORE,
    STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_COMPLETED,
    STATUS_DELAYED, STATUS_AWAITING,
)

logger = logging.getLogger(__name__)

# ConversationHandler states — 4 steps (no person step)
(NT_TITLE, NT_DESC, NT_AVENUE, NT_DEADLINE, NT_PRIORITY) = range(5)


# ── Permission guard ──────────────────────────────────────────────────────────

def is_core(user_id: int) -> bool:
    u = db.get_user(user_id)
    return u is not None and u["role"] == ROLE_CORE


# ── /newtask ──────────────────────────────────────────────────────────────────

async def newtask_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_core(update.effective_user.id):
        await update.message.reply_text(
            "🚫 Only *Core Leadership* can create tasks.\n\n"
            "If you want to take on a task, use /mytasks and tap *🙋 Take Task*.",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    ctx.user_data.clear()
    await update.message.reply_text(
        "📋 *New Task — Step 1/4*\n\n"
        "What is the *task title*?\n\n"
        "/cancel to abort.",
        parse_mode="Markdown",
    )
    return NT_TITLE


async def nt_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["title"] = update.message.text.strip()
    await update.message.reply_text(
        "📝 *Step 2/4* — Provide a *description*\n(or type `skip`):",
        parse_mode="Markdown",
    )
    return NT_DESC


async def nt_desc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    ctx.user_data["desc"] = "" if text.lower() == "skip" else text
    await update.message.reply_text(
        "🏢 *Step 3/4* — Select the *avenue* this task belongs to:",
        parse_mode="Markdown",
        reply_markup=avenue_keyboard("ntavenue"),
    )
    return NT_AVENUE


async def nt_avenue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["avenue"] = query.data.replace("ntavenue_", "")
    await query.message.reply_text(
        "📅 *Step 4a/4* — Enter the *deadline*:\n"
        "Format: `YYYY-MM-DD HH:MM`\n"
        "Example: `2026-06-01 18:00`\n\n"
        "Or type `none` for no deadline.",
        parse_mode="Markdown",
    )
    return NT_DEADLINE


async def nt_deadline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == "none":
        ctx.user_data["deadline"] = None
    else:
        try:
            datetime.strptime(text, "%Y-%m-%d %H:%M")
            ctx.user_data["deadline"] = text
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid format. Use `YYYY-MM-DD HH:MM` or `none`.",
                parse_mode="Markdown",
            )
            return NT_DEADLINE

    await update.message.reply_text(
        "🎯 *Step 4b/4* — Select *priority*:",
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
        assigned_to=None,          # No pre-assignment — members claim it
        assigned_by=user_id,
        avenue=ud["avenue"],
        deadline=ud["deadline"],
        priority=priority,
    )
    task = db.get_task(task_id)

    # Schedule per-task deadline reminders via JobQueue
    if ud["deadline"] and ctx.application.job_queue:
        from scheduler import schedule_task_reminders
        schedule_task_reminders(ctx.application, task_id, ud["deadline"])

    # Notify all members of the assigned avenue
    avenue_members = db.get_users_by_avenue(ud["avenue"])
    note_text = (
        f"🔔 *New Task for {ud['avenue']}!*\n\n"
        f"Core leadership has assigned a task to your avenue.\n"
        f"Tap *🙋 Take Task* to claim it and become responsible.\n\n"
        + format_task_card(task)
    )
    notified = 0
    for member in avenue_members:
        try:
            await ctx.bot.send_message(
                member["telegram_id"],
                note_text,
                parse_mode="Markdown",
                reply_markup=task_status_keyboard(task_id),
            )
            notified += 1
        except Exception as e:
            logger.warning("Could not notify %s: %s", member["telegram_id"], e)

    await query.message.reply_text(
        f"✅ *Task #{task_id} Created & Sent to {ud['avenue']}!*\n"
        f"👥 Notified {notified} member(s)\n\n"
        + format_task_card(task),
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
        f"📋 *Your Tasks ({len(tasks)} total)*\n━━━━━━━━━━━━━━━━━━━━\n"
        f"Tap *🙋 Take Task* on any unclaimed task to own it.",
        parse_mode="Markdown",
    )
    for t in tasks[:10]:
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
        await update.message.reply_text(
            f"📭 No tasks for *{u['avenue']}* yet.", parse_mode="Markdown"
        )
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


# ── Status + Claim callback handler ──────────────────────────────────────────

STATUS_MAP = {
    "task_done":  STATUS_COMPLETED,
    "task_prog":  STATUS_IN_PROGRESS,
    "task_delay": STATUS_DELAYED,
    "task_await": STATUS_AWAITING,
    "task_pend":  STATUS_PENDING,
}


async def task_status_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data   # e.g. "task_done_3" or "task_claim_3"

    parts   = data.rsplit("_", 1)
    prefix  = parts[0]
    task_id = int(parts[1])

    # ── Claim flow ────────────────────────────────────────────────────────────
    if prefix == "task_claim":
        await query.answer()
        claimed = db.claim_task(task_id, query.from_user.id)
        task = db.get_task(task_id)
        if not task:
            await query.answer("Task not found.", show_alert=True)
            return

        if not claimed:
            await query.answer(
                f"This task is already claimed by {task['assigned_to']}.",
                show_alert=True,
            )
            return

        # Notify core about who claimed the task
        claimer_name = query.from_user.full_name
        notify = (
            f"🙋 *Task Claimed!*\n\n"
            f"📋 Task #{task_id}: *{task['title']}*\n"
            f"👤 Claimed by: *{claimer_name}*\n"
            f"🏢 Avenue: {task['avenue']}"
        )
        for cu in db.get_users_by_role("core"):
            try:
                await ctx.bot.send_message(cu["telegram_id"], notify, parse_mode="Markdown")
            except Exception:
                pass

        # Also notify avenue members
        for m in db.get_users_by_avenue(task["avenue"] or ""):
            if m["telegram_id"] == query.from_user.id:
                continue
            try:
                await ctx.bot.send_message(
                    m["telegram_id"],
                    f"🙋 *{claimer_name}* has taken Task #{task_id}: *{task['title']}*",
                    parse_mode="Markdown",
                )
            except Exception:
                pass

        await query.edit_message_text(
            format_task_card(db.get_task(task_id)),
            parse_mode="Markdown",
            reply_markup=task_status_keyboard(task_id),
        )
        return

    # ── Status update flow ────────────────────────────────────────────────────
    await query.answer()
    new_status = STATUS_MAP.get(prefix)
    if not new_status:
        return

    task = db.get_task(task_id)
    if not task:
        await query.answer("Task not found.", show_alert=True)
        return

    db.update_task_status(task_id, new_status)
    task = db.get_task(task_id)

    notify_text = (
        f"🔄 *Task Status Updated*\n\n"
        f"📋 Task #{task_id}: *{task['title']}*\n"
        f"📌 New Status: *{new_status}*\n"
        f"👤 Updated by: {query.from_user.full_name}\n"
        f"🏢 Avenue: {task['avenue']}"
    )
    for cu in db.get_users_by_role("core"):
        try:
            await ctx.bot.send_message(cu["telegram_id"], notify_text, parse_mode="Markdown")
        except Exception:
            pass

    await query.edit_message_text(
        format_task_card(task),
        parse_mode="Markdown",
        reply_markup=task_status_keyboard(task_id),
    )


# ── Cancel + Conversation assembly ───────────────────────────────────────────

async def _cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Task creation cancelled.")
    return ConversationHandler.END


def newtask_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("newtask", newtask_start)],
        states={
            NT_TITLE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, nt_title)],
            NT_DESC:     [MessageHandler(filters.TEXT & ~filters.COMMAND, nt_desc)],
            NT_AVENUE:   [CallbackQueryHandler(nt_avenue,   pattern=r"^ntavenue_")],
            NT_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, nt_deadline)],
            NT_PRIORITY: [CallbackQueryHandler(nt_priority, pattern=r"^ntpriority_")],
        },
        fallbacks=[CommandHandler("cancel", _cancel)],
        name="newtask_conv",
        per_message=False,
    )
