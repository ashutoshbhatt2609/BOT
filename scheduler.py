"""
scheduler.py — APScheduler jobs for reminders, escalation, and weekly reports.
"""

import logging
import pytz
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
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
tz = pytz.timezone(TIMEZONE)


# ── Report builder ────────────────────────────────────────────────────────────

def build_report_text() -> str:
    stats = db.get_weekly_stats()
    total = stats["total"]
    comp  = stats["completed"]
    rate  = round((comp / total * 100) if total else 0, 1)

    lines = [
        "📊 *Weekly Rotaract Club Report*",
        f"🗓️ Generated: {datetime.now(tz).strftime('%d %b %Y, %I:%M %p')}",
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
        lines.append(
            f"{medal} *{av['avenue']}*: {av['done']}/{av['total']} tasks ({av_rate}%)"
        )

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        "Keep up the great work! 💪",
    ]

    report_text = "\n".join(lines)
    # Save to DB
    db.save_report(summary=report_text, statistics=str(stats))
    return report_text


# ── Scheduled job functions ───────────────────────────────────────────────────

async def send_weekly_report(bot) -> None:
    """Send weekly report to core group chat."""
    text = build_report_text()
    if CORE_GROUP_CHAT_ID:
        try:
            await bot.send_message(CORE_GROUP_CHAT_ID, text, parse_mode="Markdown")
            logger.info("Weekly report sent to core group.")
        except Exception as e:
            logger.error("Failed to send weekly report: %s", e)
    # Also send to all core members individually
    for user in db.get_users_by_role("core"):
        try:
            await bot.send_message(user["telegram_id"], text, parse_mode="Markdown")
        except Exception:
            pass


async def send_reminders(bot) -> None:
    """Daily reminder for all non-completed tasks."""
    tasks = [
        t for t in db.get_all_tasks()
        if t["status"] not in (STATUS_COMPLETED, STATUS_AWAITING)
    ]
    for task in tasks:
        members = db.get_users_by_avenue(task["avenue"])
        text = (
            f"⏰ *Daily Reminder*\n\n"
            + format_task_card(task)
        )
        for m in members:
            try:
                await bot.send_message(m["telegram_id"], text, parse_mode="Markdown")
            except Exception:
                pass


async def send_urgent_reminders(bot) -> None:
    """Every 5 hours — remind about Urgent tasks."""
    tasks = [
        t for t in db.get_all_tasks()
        if t["priority"] == "Urgent"
        and t["status"] not in (STATUS_COMPLETED, STATUS_AWAITING)
    ]
    for task in tasks:
        members = db.get_users_by_avenue(task["avenue"])
        text = (
            f"🚨 *URGENT Task Reminder!*\n\n"
            + format_task_card(task)
        )
        for m in members:
            try:
                await bot.send_message(m["telegram_id"], text, parse_mode="Markdown")
            except Exception:
                pass


async def send_deadline_reminders(bot, hours: int) -> None:
    """Remind about tasks with deadline within `hours` hours."""
    tasks = db.get_upcoming_deadline_tasks(hours)
    for task in tasks:
        members = db.get_users_by_avenue(task["avenue"])
        text = (
            f"⚠️ *Deadline Alert — {hours}h Remaining!*\n\n"
            + format_task_card(task)
        )
        for m in members:
            try:
                await bot.send_message(m["telegram_id"], text, parse_mode="Markdown")
            except Exception:
                pass


async def run_escalation(bot) -> None:
    """Escalate overdue tasks based on how many hours they're overdue."""
    overdue = db.get_overdue_tasks()
    now = datetime.now(tz).replace(tzinfo=None)

    for task in overdue:
        if not task["deadline"]:
            continue
        try:
            dl = datetime.strptime(task["deadline"], "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        hours_overdue = (now - dl).total_seconds() / 3600

        base_msg = (
            f"🚨 *ESCALATION ALERT*\n\n"
            f"Task #{task['id']}: *{task['title']}* is overdue by "
            f"{int(hours_overdue)}h!\n\n"
            + format_task_card(task)
        )

        # Level 1 — always notify assigned avenue members
        members = db.get_users_by_avenue(task["avenue"])
        for m in members:
            try:
                await bot.send_message(m["telegram_id"], base_msg, parse_mode="Markdown")
            except Exception:
                pass

        # Level 2 — notify avenue director
        if hours_overdue >= ESCALATE_DIRECTOR_AFTER_H:
            director = db.get_avenue_director(task["avenue"])
            if director:
                try:
                    await bot.send_message(
                        director["telegram_id"],
                        f"📣 [Director Escalation]\n\n" + base_msg,
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

        # Level 3 — notify Secretary
        if hours_overdue >= ESCALATE_SECRETARY_AFTER_H:
            secretaries = [
                u for u in db.get_users_by_role("core")
                if "secretary" in u["name"].lower() or "secretary" in (u.get("permissions") or "").lower()
            ]
            all_core = db.get_users_by_role("core")
            targets  = secretaries or all_core[:1]
            for t in targets:
                try:
                    await bot.send_message(
                        t["telegram_id"],
                        f"📣 [Secretary Escalation]\n\n" + base_msg,
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

        # Level 4 — notify President (all core)
        if hours_overdue >= ESCALATE_PRESIDENT_AFTER_H:
            for core in db.get_users_by_role("core"):
                try:
                    await bot.send_message(
                        core["telegram_id"],
                        f"📣 [PRESIDENT ESCALATION]\n\n" + base_msg,
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass


# ── Scheduler factory ─────────────────────────────────────────────────────────

def build_scheduler(bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=tz)

    # Daily reminder at 9 AM
    scheduler.add_job(
        send_reminders, CronTrigger(hour=9, minute=0, timezone=tz),
        args=[bot], id="daily_reminder", replace_existing=True,
    )

    # Urgent tasks — every 5 hours
    scheduler.add_job(
        send_urgent_reminders, IntervalTrigger(hours=5),
        args=[bot], id="urgent_reminder", replace_existing=True,
    )

    # Deadline — 24h reminder (check every hour)
    scheduler.add_job(
        send_deadline_reminders, IntervalTrigger(hours=1),
        args=[bot, 24], id="dl_24h", replace_existing=True,
    )

    # Deadline — 5h reminder (check every 30 min)
    scheduler.add_job(
        send_deadline_reminders, IntervalTrigger(minutes=30),
        args=[bot, 5], id="dl_5h", replace_existing=True,
    )

    # Deadline — 1h reminder (check every 15 min)
    scheduler.add_job(
        send_deadline_reminders, IntervalTrigger(minutes=15),
        args=[bot, 1], id="dl_1h", replace_existing=True,
    )

    # Escalation check — every 2 hours
    scheduler.add_job(
        run_escalation, IntervalTrigger(hours=2),
        args=[bot], id="escalation", replace_existing=True,
    )

    # Weekly report — Every Monday at 8 AM
    scheduler.add_job(
        send_weekly_report, CronTrigger(day_of_week="mon", hour=8, minute=0, timezone=tz),
        args=[bot], id="weekly_report", replace_existing=True,
    )

    return scheduler
