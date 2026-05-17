"""
main.py — Entry point for the Rotaract Club Telegram Bot.

Usage:
  1. Copy .env.example to .env and fill in BOT_TOKEN
  2. pip install -r requirements.txt
  3. python main.py
"""

import asyncio
import logging
from telegram import BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)

import database as db
from config import BOT_TOKEN
from scheduler import build_scheduler

# Handlers
from handlers.common_handlers import start, help_cmd, handle_group_message, unknown_command
from handlers.admin_handlers  import (
    removeuser, report_cmd, listusers,
    adduser_conv, setrole_conv, setavenue_conv, announce_conv,
)
from handlers.task_handlers   import (
    mytasks, pending_tasks, completed_tasks, avenue_tasks,
    task_status_callback, newtask_conv,
)
from handlers.request_handlers import (
    request_conv, request_action_callback,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """Set bot commands visible in Telegram menu."""
    await application.bot.set_my_commands([
        BotCommand("start",       "Register / Welcome"),
        BotCommand("help",        "Show all commands"),
        BotCommand("newtask",     "Create a new task"),
        BotCommand("mytasks",     "View your avenue's tasks"),
        BotCommand("pending",     "View pending tasks"),
        BotCommand("completed",   "View completed tasks"),
        BotCommand("avenuetasks", "All tasks for your avenue"),
        BotCommand("request",     "Send inter-avenue request"),
        BotCommand("report",      "Generate weekly report [Core]"),
        BotCommand("announce",    "Broadcast announcement [Core]"),
        BotCommand("adduser",     "Add a user [Core]"),
        BotCommand("removeuser",  "Remove a user [Core]"),
        BotCommand("setrole",     "Set user role [Core]"),
        BotCommand("setavenue",   "Set user avenue [Core]"),
        BotCommand("listusers",   "List all users [Core]"),
        BotCommand("cancel",      "Cancel current operation"),
    ])
    logger.info("Bot commands registered.")


def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set! Create a .env file from .env.example.")
        return

    # Initialise database
    db.init_db()
    logger.info("Database ready.")

    # Build Telegram application
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # ── Conversation handlers (must be added first) ───────────────────────────
    app.add_handler(adduser_conv())
    app.add_handler(setrole_conv())
    app.add_handler(setavenue_conv())
    app.add_handler(announce_conv())
    app.add_handler(newtask_conv())
    app.add_handler(request_conv())

    # ── Simple command handlers ───────────────────────────────────────────────
    app.add_handler(CommandHandler("start",       start))
    app.add_handler(CommandHandler("help",        help_cmd))
    app.add_handler(CommandHandler("mytasks",     mytasks))
    app.add_handler(CommandHandler("pending",     pending_tasks))
    app.add_handler(CommandHandler("completed",   completed_tasks))
    app.add_handler(CommandHandler("avenuetasks", avenue_tasks))
    app.add_handler(CommandHandler("report",      report_cmd))
    app.add_handler(CommandHandler("removeuser",  removeuser))
    app.add_handler(CommandHandler("listusers",   listusers))

    # ── Inline keyboard callbacks ─────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(task_status_callback,   pattern=r"^task_"))
    app.add_handler(CallbackQueryHandler(request_action_callback, pattern=r"^req_"))

    # ── Group message logger ──────────────────────────────────────────────────
    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, handle_group_message)
    )

    # ── Unknown commands fallback ─────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # ── APScheduler ───────────────────────────────────────────────────────────
    scheduler = build_scheduler(app.bot)
    scheduler.start()
    logger.info("Scheduler started. Jobs: %s", [j.id for j in scheduler.get_jobs()])

    logger.info("🤖 Rotaract Bot is running… Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=["message", "callback_query"])

    scheduler.shutdown()


if __name__ == "__main__":
    main()
