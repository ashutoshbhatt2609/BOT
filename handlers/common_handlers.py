"""
handlers/common_handlers.py — /start, /help, and general message routing.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database as db
from config import ROLE_CORE, ROLE_DIRECTOR, ROLE_MEMBER

logger = logging.getLogger(__name__)

HELP_TEXT = """
🌟 *Rotaract Club Bot — Command Reference*
━━━━━━━━━━━━━━━━━━━━━━━━

👤 *All Members*
/start — Register & welcome message
/help — Show this help menu
/mytasks — View your avenue's tasks
/pending — View pending tasks
/completed — View completed tasks
/request — Send inter-avenue request

📋 *Avenue Directors*
/newtask — Create a new task
/avenuetasks — View all tasks for your avenue

👑 *Core Leadership*
/newtask — Create tasks for any avenue
/report — Generate weekly report now
/announce — Broadcast to all members
/adduser — Register a user
/removeuser — Remove a user
/setrole — Change a user's role
/setavenue — Set a user's avenue

━━━━━━━━━━━━━━━━━━━━━━━━
Use inline buttons for status updates!
"""


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db_user = db.get_user(user.id)

    if not db_user:
        # Auto-register as member; admin can promote later
        db.add_user(
            telegram_id=user.id,
            name=user.full_name,
            username=user.username or "",
        )
        await update.message.reply_text(
            f"👋 Welcome, *{user.full_name}*!\n\n"
            "You've been registered as a *Member*.\n"
            "An admin will assign your role and avenue shortly.\n\n"
            "Use /help to see available commands.",
            parse_mode="Markdown",
        )
        logger.info("New user registered: %s (%s)", user.full_name, user.id)
    else:
        role_display = {
            ROLE_CORE: "👑 Core Leadership",
            ROLE_DIRECTOR: "🎯 Avenue Director",
            ROLE_MEMBER: "👤 Member",
        }.get(db_user["role"], db_user["role"])
        await update.message.reply_text(
            f"Welcome back, *{user.full_name}*! 🎉\n\n"
            f"🏷️ Role: {role_display}\n"
            f"🏢 Avenue: {db_user['avenue'] or 'Unassigned'}\n\n"
            "Use /help for available commands.",
            parse_mode="Markdown",
        )


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def handle_group_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """
    In group chats: log messages and files for record-keeping.
    Does NOT forward — Telegram groups handle their own delivery.
    """
    msg = update.message
    if not msg:
        return

    sender = msg.from_user
    db_user = db.get_user(sender.id)
    avenue = db_user["avenue"] if db_user else None
    text = msg.text or msg.caption or ""

    # Detect file type
    file_id, file_type = None, None
    if msg.document:
        file_id = msg.document.file_id
        file_type = "document"
    elif msg.photo:
        file_id = msg.photo[-1].file_id
        file_type = "photo"
    elif msg.video:
        file_id = msg.video.file_id
        file_type = "video"
    elif msg.audio:
        file_id = msg.audio.file_id
        file_type = "audio"
    elif msg.voice:
        file_id = msg.voice.file_id
        file_type = "voice"
    elif msg.sticker:
        file_id = msg.sticker.file_id
        file_type = "sticker"

    db.log_message(
        sender_id=sender.id,
        avenue=avenue,
        message=text,
        file_id=file_id,
        file_type=file_type,
    )


async def unknown_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "❓ Unknown command. Use /help to see all available commands."
    )
