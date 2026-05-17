"""
main.py — Entry point for the Rotaract Club Telegram Bot.

MODE DETECTION (automatic):
  - Local dev  → python main.py        → uses Long Polling
  - Railway    → PORT env set          → uses Webhook (event-driven, lightweight)

Usage:
  1. Copy .env.example to .env and fill in BOT_TOKEN
  2. pip install -r requirements.txt
  3. python main.py
"""

import logging
from telegram import BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)

import database as db
from config import (
    BOT_TOKEN, WEBHOOK_URL, PORT, WEBHOOK_SECRET,
)
from scheduler import setup_jobs

# Handlers
from handlers.common_handlers  import start, help_cmd, handle_group_message, unknown_command
from handlers.admin_handlers   import (
    removeuser, report_cmd, listusers,
    adduser_conv, setrole_conv, setavenue_conv, announce_conv,
)
from handlers.task_handlers    import (
    mytasks, pending_tasks, completed_tasks, avenue_tasks,
    task_status_callback, newtask_conv,
)
from handlers.request_handlers  import (
    request_conv, request_action_callback,
)
from handlers.message_handlers  import msg_conv

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Post-init (runs after bot connects) ──────────────────────────────────────

async def post_init(application: Application) -> None:
    """Register bot commands in Telegram menu + start JobQueue jobs."""
    await application.bot.set_my_commands([
        BotCommand("start",       "Register / Welcome"),
        BotCommand("help",        "Show all commands"),
        BotCommand("msg",         "Send message to an avenue or leadership"),
        BotCommand("newtask",     "Create a new task [Core only]"),
        BotCommand("mytasks",     "View your avenue's tasks"),
        BotCommand("pending",     "View pending tasks"),
        BotCommand("completed",   "View completed tasks"),
        BotCommand("avenuetasks", "All tasks for your avenue"),
        BotCommand("request",     "Send inter-avenue work request"),
        BotCommand("report",      "Generate weekly report [Core]"),
        BotCommand("announce",    "Broadcast announcement [Core]"),
        BotCommand("adduser",     "Add a user [Core]"),
        BotCommand("removeuser",  "Remove a user [Core]"),
        BotCommand("setrole",     "Set user role [Core]"),
        BotCommand("setavenue",   "Set user avenue [Core]"),
        BotCommand("listusers",   "List all members [Core]"),
        BotCommand("cancel",      "Cancel current operation"),
    ])
    logger.info("Bot commands registered.")

    # Start recurring JobQueue jobs (daily reminder, weekly report, escalation)
    setup_jobs(application)


# ── Application builder ───────────────────────────────────────────────────────

def build_app() -> Application:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # ── Conversation handlers (registered first — highest priority) ───────────
    app.add_handler(adduser_conv())
    app.add_handler(setrole_conv())
    app.add_handler(setavenue_conv())
    app.add_handler(announce_conv())
    app.add_handler(newtask_conv())
    app.add_handler(request_conv())
    app.add_handler(msg_conv())

    # ── Command handlers ──────────────────────────────────────────────────────
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
    app.add_handler(CallbackQueryHandler(task_status_callback,    pattern=r"^task_"))
    app.add_handler(CallbackQueryHandler(request_action_callback, pattern=r"^req_"))

    # ── Group message logger (logs all group messages + files to DB) ──────────
    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, handle_group_message)
    )

    # ── Unknown commands fallback ─────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    return app


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        logger.error(
            "BOT_TOKEN is not set! "
            "Copy .env.example to .env and fill in your token."
        )
        return

    db.init_db()
    logger.info("Database ready at: %s", __import__("config").DB_PATH)

    app = build_app()

    # ── Mode: Webhook (Railway) or Long Polling (local) ───────────────────────
    if WEBHOOK_URL:
        # Production mode — Railway provides PORT automatically
        webhook_url = f"{WEBHOOK_URL.rstrip('/')}/{BOT_TOKEN}"
        logger.info("Starting in WEBHOOK mode → %s", webhook_url)
        logger.info("Listening on 0.0.0.0:%s", PORT)

        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=webhook_url,
            url_path=BOT_TOKEN,
            secret_token=WEBHOOK_SECRET or None,
            allowed_updates=["message", "callback_query"],
        )
    else:
        # Local development mode — Long Polling
        logger.info("WEBHOOK_URL not set — starting in LONG POLLING mode (local dev).")
        logger.info("Rotaract Bot is running... Press Ctrl+C to stop.")
        app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
