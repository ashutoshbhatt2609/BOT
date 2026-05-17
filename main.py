"""
main.py — Rotaract Club Telegram Bot entry point.

MODE DETECTION (automatic, in priority order):
  1. WEBHOOK_URL set               → Starlette + Uvicorn, webhook active
  2. RENDER=true (Render sets it)  → Starlette + Uvicorn, webhook pending
                                     (health check passes; set WEBHOOK_URL
                                      in Render dashboard to activate bot)
  3. Neither                       → PTB Long Polling (local dev)
"""


import asyncio
import os
import logging
from contextlib import asynccontextmanager

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, JSONResponse
from starlette.routing import Route
from telegram import BotCommand, Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)

import database as db

# Render automatically injects RENDER=true into the container environment
IS_RENDER: bool = os.getenv("RENDER", "").lower() == "true"
from config import BOT_TOKEN, WEBHOOK_URL, PORT, WEBHOOK_SECRET, ADMIN_TELEGRAM_ID, ADMIN_NAME
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
from handlers.request_handlers import request_conv, request_action_callback
from handlers.message_handlers import msg_conv

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Global PTB Application instance (shared across ASGI requests)
_ptb_app: Application | None = None


# ── Handler registration (shared between polling & webhook) ───────────────────

def _register_handlers(app: Application) -> None:
    """Attach all handlers to a PTB Application instance."""
    # Conversation handlers — must be registered first
    app.add_handler(adduser_conv())
    app.add_handler(setrole_conv())
    app.add_handler(setavenue_conv())
    app.add_handler(announce_conv())
    app.add_handler(newtask_conv())
    app.add_handler(request_conv())
    app.add_handler(msg_conv())

    # Command handlers
    app.add_handler(CommandHandler("start",       start))
    app.add_handler(CommandHandler("help",        help_cmd))
    app.add_handler(CommandHandler("mytasks",     mytasks))
    app.add_handler(CommandHandler("pending",     pending_tasks))
    app.add_handler(CommandHandler("completed",   completed_tasks))
    app.add_handler(CommandHandler("avenuetasks", avenue_tasks))
    app.add_handler(CommandHandler("report",      report_cmd))
    app.add_handler(CommandHandler("removeuser",  removeuser))
    app.add_handler(CommandHandler("listusers",   listusers))

    # Inline keyboard callbacks
    app.add_handler(CallbackQueryHandler(task_status_callback,    pattern=r"^task_"))
    app.add_handler(CallbackQueryHandler(request_action_callback, pattern=r"^req_"))

    # Group message logger
    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, handle_group_message)
    )

    # Unknown command fallback
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))


async def _register_commands(bot) -> None:
    """Set Telegram bot command menu."""
    await bot.set_my_commands([
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


# ── WEBHOOK MODE — Starlette ASGI app (Render) ───────────────────────────────

async def _startup() -> None:
    """Initialise PTB Application on Starlette startup."""
    global _ptb_app
    db.init_db()
    if ADMIN_TELEGRAM_ID:
        db.bootstrap_admin(ADMIN_TELEGRAM_ID, ADMIN_NAME)

    _ptb_app = Application.builder().token(BOT_TOKEN).build()
    _register_handlers(_ptb_app)

    await _ptb_app.initialize()
    await _register_commands(_ptb_app.bot)

    if WEBHOOK_URL:
        # Full webhook mode — Telegram sends updates to our URL
        webhook_path = f"/webhook/{BOT_TOKEN}"
        webhook_full = f"{WEBHOOK_URL.rstrip('/')}{webhook_path}"
        await _ptb_app.bot.set_webhook(
            url=webhook_full,
            secret_token=WEBHOOK_SECRET or None,
            allowed_updates=["message", "callback_query"],
        )
        logger.info("Webhook registered: %s", webhook_full)
        await _ptb_app.start()
        setup_jobs(_ptb_app)
        logger.info("Bot is LIVE on Render via webhook.")
    else:
        # Render detected but WEBHOOK_URL not yet set (first deploy)
        # Health check will pass; set WEBHOOK_URL in Render dashboard to activate.
        logger.warning(
            "WEBHOOK_URL is not set. "
            "Health check is running but the bot is NOT receiving Telegram updates. "
            "Add WEBHOOK_URL in your Render environment variables to activate."
        )


async def _shutdown() -> None:
    """Gracefully stop PTB Application on Starlette shutdown."""
    if _ptb_app:
        await _ptb_app.stop()
        await _ptb_app.shutdown()
        logger.info("PTB Application shut down cleanly.")


@asynccontextmanager
async def _lifespan(app):
    await _startup()
    yield
    await _shutdown()


# ── Starlette route handlers ──────────────────────────────────────────────────

async def health_check(request: Request) -> PlainTextResponse:
    """Render health check — must return 200."""
    return PlainTextResponse("OK — Rotaract Bot is running.", status_code=200)


async def telegram_webhook(request: Request) -> PlainTextResponse:
    """Receive Telegram webhook updates and feed to PTB."""
    # Optional secret token validation
    if WEBHOOK_SECRET:
        incoming_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if incoming_secret != WEBHOOK_SECRET:
            logger.warning("Invalid webhook secret token received.")
            return PlainTextResponse("Unauthorized", status_code=403)

    try:
        body   = await request.json()
        update = Update.de_json(data=body, bot=_ptb_app.bot)
        await _ptb_app.process_update(update)
    except Exception as e:
        logger.error("Error processing update: %s", e)

    return PlainTextResponse("OK", status_code=200)


def _build_starlette_app() -> Starlette:
    return Starlette(
        lifespan=_lifespan,
        routes=[
            Route("/health",                  health_check,     methods=["GET"]),
            Route("/",                        health_check,     methods=["GET"]),
            Route(f"/webhook/{BOT_TOKEN}",    telegram_webhook, methods=["POST"]),
        ],
    )


# ── POLLING MODE — local development ─────────────────────────────────────────

def _run_polling() -> None:
    """Start PTB in long polling mode (local dev — no WEBHOOK_URL set)."""
    db.init_db()
    if ADMIN_TELEGRAM_ID:
        db.bootstrap_admin(ADMIN_TELEGRAM_ID, ADMIN_NAME)
    logger.info("Starting in LONG POLLING mode (local dev)")

    async def _post_init(app: Application) -> None:
        await _register_commands(app.bot)
        setup_jobs(app)

    app = Application.builder().token(BOT_TOKEN).post_init(_post_init).build()
    _register_handlers(app)

    logger.info("Rotaract Bot running... Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=["message", "callback_query"])


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        logger.error(
            "BOT_TOKEN not set! Copy .env.example → .env and fill in your token."
        )
        return

    if WEBHOOK_URL or IS_RENDER:
        # Production: Render detected (even on first deploy before WEBHOOK_URL is set)
        logger.info(
            "Starting Starlette + Uvicorn on port %s | IS_RENDER=%s | WEBHOOK_URL=%s",
            PORT, IS_RENDER, WEBHOOK_URL or "(not set yet)",
        )
        starlette_app = _build_starlette_app()
        uvicorn.run(
            starlette_app,
            host="0.0.0.0",
            port=PORT,
            log_level="info",
        )
    else:
        # Local development — long polling
        _run_polling()


if __name__ == "__main__":
    main()
