"""
scheduler.py — PTB JobQueue-based scheduler (Railway-optimized).

Strategy:
  - NO APScheduler. Uses python-telegram-bot's built-in JobQueue.
  - Per-task reminders scheduled at task creation time (event-driven).
  - Daily reminder + weekly report via run_daily / run_repeating.
  - Escalation via run_repeating at low frequency (2h).
  - Zero idle DB polling — jobs fire only when needed.
"""

import logging
import pytz
from datetime import datetime, timedelta, time as dt_time
from telegram.ext import Application, CallbackContext
import database as db
from utils import format_task_card
from config import (
    TIMEZONE, CORE_GROUP_CHAT_ID,
    STATUS_COMPLETED, STATUS_AWAITING,
    ESCALATE_DIRECTOR_AFTER_H,
    ESCALATE_SECRETARY_AFTER_H,
    ESCALATE_PRESIDENT_AFTER_H,
)

logger = logging.getLogger(__name__)
IST = pytz.timezone(TIMEZONE)


# ── Report builder (shared with /report command) ──────────────────────────────

def build_report_text() -> str:
    stats = db.get_weekly_stats()
    total = stats["total"]
    comp  = stats["completed"]
    rate  = round((comp / total * 100) if total else 0, 1)

    lines = [
        "📊 *Weekly Rotaract Club Report*",
        f"🗓️ Generated: {datetime.now(IST).strftime('%d %b %Y, %I:%M %p')}",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📋 Total Tasks:     {total}",
        f"✅ Completed:       {comp}",
        f"🔵 Pending:         {stats['pending']}",
        f"⏳ In Progress:     {stats['in_progress']}",
        f"⚠️ Delayed:         {stats['delayed']}",
        f"📈 Completion Rate: {rate}%",
        "",
        "🏢 *Avenue Performance*",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for i, av in enumerate(stats["avenues"], 1):
        av_rate = round((av["done"] / av["total"] * 100) if av["total"] else 0, 1)
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "•"
        lines.append(f"{medal} *{av['avenue']}*: {av['done']}/{av['total']} ({av_rate}%)")

    lines += ["━━━━━━━━━━━━━━━━━━━━━━━━", "Keep up the great work! 💪"]
    report_text = "\n".join(lines)
    db.save_report(summary=report_text, statistics=str(stats))
    return report_text


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _notify_avenue(bot, avenue: str, text: str) -> None:
    for m in db.get_users_by_avenue(avenue):
        try:
            await bot.send_message(m["telegram_id"], text, parse_mode="Markdown")
        except Exception:
            pass


async def _notify_core(bot, text: str) -> None:
    for u in db.get_users_by_role("core"):
        try:
            await bot.send_message(u["telegram_id"], text, parse_mode="Markdown")
        except Exception:
            pass


# ── Per-task reminder jobs (scheduled at task creation) ───────────────────────

def schedule_task_reminders(app: Application, task_id: int, deadline_str: str) -> None:
    """
    Schedule deadline-aware reminder jobs for a single task.
    Called immediately when a task is created by Core.
    Zero-scan — no DB polling; jobs know their task_id.
    """
    try:
        dl = IST.localize(datetime.strptime(deadline_str, "%Y-%m-%d %H:%M"))
    except ValueError:
        logger.warning("Invalid deadline format for task %s: %s", task_id, deadline_str)
        return

    now = datetime.now(IST)
    jq  = app.job_queue

    reminders = [
        (dl - timedelta(hours=24), f"⏰ *24h Reminder* — Task #{task_id} deadline is tomorrow!"),
        (dl - timedelta(hours=5),  f"⏰ *5h Reminder* — Task #{task_id} is due in 5 hours!"),
        (dl - timedelta(hours=1),  f"⏰ *1h Reminder* — Task #{task_id} is due in 1 HOUR!"),
    ]

    for fire_at, label in reminders:
        if fire_at > now:
            jq.run_once(
                _task_reminder_job,
                when=fire_at,
                data={"task_id": task_id, "label": label},
                name=f"task_{task_id}_remind",
            )
            logger.info("Scheduled reminder for task %s at %s", task_id, fire_at.strftime("%Y-%m-%d %H:%M"))


async def _task_reminder_job(ctx: CallbackContext) -> None:
    """Fire a single task-specific deadline reminder."""
    task_id = ctx.job.data["task_id"]
    label   = ctx.job.data["label"]

    task = db.get_task(task_id)
    if not task or task["status"] in (STATUS_COMPLETED, STATUS_AWAITING):
        return  # Task already done — skip

    text = label + "\n\n" + format_task_card(task)
    await _notify_avenue(ctx.bot, task["avenue"] or "", text)


# ── Recurring global jobs ─────────────────────────────────────────────────────

async def _daily_reminder_job(ctx: CallbackContext) -> None:
    """Daily 9 AM reminder for all pending/in-progress tasks."""
    tasks = [
        t for t in db.get_all_tasks()
        if t["status"] not in (STATUS_COMPLETED, STATUS_AWAITING)
    ]
    if not tasks:
        return
    for task in tasks:
        text = f"⏰ *Daily Task Reminder*\n\n" + format_task_card(task)
        await _notify_avenue(ctx.bot, task["avenue"] or "", text)


async def _weekly_report_job(ctx: CallbackContext) -> None:
    """Monday 8 AM weekly report to all Core members."""
    text = build_report_text()
    if CORE_GROUP_CHAT_ID:
        try:
            await ctx.bot.send_message(CORE_GROUP_CHAT_ID, text, parse_mode="Markdown")
        except Exception as e:
            logger.error("Failed group report: %s", e)
    await _notify_core(ctx.bot, text)


async def _escalation_job(ctx: CallbackContext) -> None:
    """Every 2h — check overdue tasks and escalate up the hierarchy."""
    overdue = db.get_overdue_tasks()
    now = datetime.now(IST).replace(tzinfo=None)

    for task in overdue:
        if not task["deadline"]:
            continue
        try:
            dl = datetime.strptime(task["deadline"], "%Y-%m-%d %H:%M")
        except ValueError:
            continue

        hours_overdue = (now - dl).total_seconds() / 3600
        base = (
            f"🚨 *ESCALATION — Task #{task['id']} Overdue by {int(hours_overdue)}h!*\n\n"
            + format_task_card(task)
        )

        # Always notify avenue members
        await _notify_avenue(ctx.bot, task["avenue"] or "", base)

        if hours_overdue >= ESCALATE_DIRECTOR_AFTER_H:
            director = db.get_avenue_director(task["avenue"] or "")
            if director:
                try:
                    await ctx.bot.send_message(
                        director["telegram_id"],
                        f"📣 [Director Escalation]\n\n" + base,
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

        if hours_overdue >= ESCALATE_SECRETARY_AFTER_H:
            await _notify_core(ctx.bot, f"📣 [Secretary Escalation]\n\n" + base)

        if hours_overdue >= ESCALATE_PRESIDENT_AFTER_H:
            await _notify_core(ctx.bot, f"🚨 [PRESIDENT ESCALATION]\n\n" + base)


async def _urgent_reminder_job(ctx: CallbackContext) -> None:
    """Every 5h — ping URGENT priority uncompleted tasks."""
    tasks = [
        t for t in db.get_all_tasks()
        if t["priority"] == "Urgent"
        and t["status"] not in (STATUS_COMPLETED, STATUS_AWAITING)
    ]
    for task in tasks:
        text = f"🚨 *URGENT Task Reminder!*\n\n" + format_task_card(task)
        await _notify_avenue(ctx.bot, task["avenue"] or "", text)


# ── Setup — called from main.py post_init ─────────────────────────────────────

def setup_jobs(app: Application) -> None:
    """Register all recurring jobs using PTB's built-in JobQueue."""
    jq = app.job_queue

    # Daily reminder — 9:00 AM IST, every day
    jq.run_daily(
        _daily_reminder_job,
        time=dt_time(9, 0, tzinfo=IST),
        name="daily_reminder",
    )

    # Weekly report — Monday 8:00 AM IST
    jq.run_daily(
        _weekly_report_job,
        time=dt_time(8, 0, tzinfo=IST),
        days=(1,),           # 1 = Monday (PTB: 0=Sun, 1=Mon … 6=Sat)
        name="weekly_report",
    )

    # Escalation check — every 2 hours
    jq.run_repeating(
        _escalation_job,
        interval=timedelta(hours=2),
        first=timedelta(minutes=5),  # first check 5 min after startup
        name="escalation",
    )

    # Urgent task reminder — every 5 hours
    jq.run_repeating(
        _urgent_reminder_job,
        interval=timedelta(hours=5),
        first=timedelta(minutes=10),
        name="urgent_reminder",
    )

    logger.info("JobQueue jobs scheduled: %s", [j.name for j in jq.jobs()])
