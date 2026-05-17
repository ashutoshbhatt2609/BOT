"""
handlers/message_handlers.py
Targeted messaging system:
  - Members → message their own avenue OR any other avenue
  - Directors → message any avenue
  - Core → message any avenue OR broadcast to ALL avenues at once
             Also message the Leadership group directly
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
import database as db
from config import AVENUES, ROLE_CORE

logger = logging.getLogger(__name__)

# Conversation states
MSG_TARGET, MSG_CONTENT = range(2)


def _build_target_keyboard(is_core: bool) -> InlineKeyboardMarkup:
    """Build the target-selection keyboard.
    Core gets an extra 'All Avenues' + 'Leadership' button row."""
    buttons = []
    # Avenue buttons — 2 per row
    for i in range(0, len(AVENUES), 2):
        row = [InlineKeyboardButton(AVENUES[i], callback_data=f"msgtgt_{AVENUES[i]}")]
        if i + 1 < len(AVENUES):
            row.append(InlineKeyboardButton(AVENUES[i + 1], callback_data=f"msgtgt_{AVENUES[i + 1]}"))
        buttons.append(row)

    # Leadership is always available (sends to all Core members)
    buttons.append([InlineKeyboardButton("👑 Leadership (Core Team)", callback_data="msgtgt_LEADERSHIP")])

    # Core-only: broadcast to every member
    if is_core:
        buttons.append([InlineKeyboardButton("📢 ALL AVENUES (Broadcast)", callback_data="msgtgt_ALL")])

    return InlineKeyboardMarkup(buttons)


async def msg_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = db.get_user(user.id)

    if not db_user:
        await update.message.reply_text(
            "⚠️ You are not registered. Send /start first."
        )
        return ConversationHandler.END

    is_core = db_user["role"] == ROLE_CORE
    ctx.user_data.clear()
    ctx.user_data["sender_name"] = db_user["name"]
    ctx.user_data["sender_avenue"] = db_user["avenue"] or "Unregistered"
    ctx.user_data["sender_role"] = db_user["role"]
    ctx.user_data["is_core"] = is_core

    await update.message.reply_text(
        "💬 *Send a Message*\n\n"
        "Select who you want to send a message to:\n\n"
        "📌 *Core members* can message any avenue or broadcast to all.\n"
        "📌 *Directors/Members* can message any specific avenue.\n\n"
        "/cancel to abort.",
        parse_mode="Markdown",
        reply_markup=_build_target_keyboard(is_core),
    )
    return MSG_TARGET


async def msg_target(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    target = query.data.replace("msgtgt_", "")
    ctx.user_data["target"] = target

    target_display = {
        "ALL": "📢 ALL AVENUES",
        "LEADERSHIP": "👑 Leadership (Core Team)",
    }.get(target, f"🏢 {target}")

    await query.message.reply_text(
        f"📨 *Messaging: {target_display}*\n\n"
        "Now send your message.\n"
        "You can send:\n"
        "  • Text\n"
        "  • Photo 📷\n"
        "  • Document 📄\n"
        "  • Video 🎥\n"
        "  • Audio 🎵\n"
        "  • Voice note 🎤\n\n"
        "/cancel to abort.",
        parse_mode="Markdown",
    )
    return MSG_CONTENT


async def msg_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle any content type and forward to recipients."""
    msg = update.message
    ud  = ctx.user_data
    target = ud.get("target", "")

    sender_name   = ud.get("sender_name", "Unknown")
    sender_avenue = ud.get("sender_avenue", "")
    sender_role   = ud.get("sender_role", "member")

    role_badge = {
        "core":     "👑 Core",
        "director": "🎯 Director",
        "member":   "👤 Member",
    }.get(sender_role, sender_role)

    header = (
        f"💬 *Message from {sender_name}*\n"
        f"🏷️ {role_badge} | {sender_avenue}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    # Determine recipients
    recipients: list = []

    if target == "ALL":
        recipients = db.get_all_users()
    elif target == "LEADERSHIP":
        recipients = db.get_users_by_role("core")
    else:
        recipients = db.get_users_by_avenue(target)

    if not recipients:
        await msg.reply_text(
            f"⚠️ No members found in *{target}*. Nobody to send to.",
            parse_mode="Markdown",
        )
        ctx.user_data.clear()
        return ConversationHandler.END

    # Send header + content to each recipient
    sent_count = 0
    failed_count = 0

    for recipient in recipients:
        # Don't send to the sender themselves
        if recipient["telegram_id"] == msg.from_user.id:
            continue
        try:
            # 1. Send the header
            await ctx.bot.send_message(
                recipient["telegram_id"],
                header,
                parse_mode="Markdown",
            )
            # 2. Forward the actual content (preserves media, files, etc.)
            await ctx.bot.forward_message(
                chat_id=recipient["telegram_id"],
                from_chat_id=msg.chat_id,
                message_id=msg.message_id,
            )
            sent_count += 1
        except Exception as e:
            logger.warning("Failed to send to %s: %s", recipient["telegram_id"], e)
            failed_count += 1

    # Build target label for confirmation
    target_label = {
        "ALL": "ALL AVENUES",
        "LEADERSHIP": "Leadership (Core Team)",
    }.get(target, target)

    await msg.reply_text(
        f"✅ *Message sent!*\n\n"
        f"📤 To: *{target_label}*\n"
        f"👥 Delivered: {sent_count} member(s)\n"
        + (f"❌ Failed: {failed_count}" if failed_count else ""),
        parse_mode="Markdown",
    )

    # Log the message to DB
    file_id, file_type = _extract_file(msg)
    db.log_message(
        sender_id=msg.from_user.id,
        avenue=target,
        message=msg.text or msg.caption or "",
        file_id=file_id,
        file_type=file_type,
    )

    ctx.user_data.clear()
    return ConversationHandler.END


def _extract_file(msg):
    """Extract file_id and type from a message if it contains media."""
    if msg.document:
        return msg.document.file_id, "document"
    if msg.photo:
        return msg.photo[-1].file_id, "photo"
    if msg.video:
        return msg.video.file_id, "video"
    if msg.audio:
        return msg.audio.file_id, "audio"
    if msg.voice:
        return msg.voice.file_id, "voice"
    if msg.sticker:
        return msg.sticker.file_id, "sticker"
    return None, None


async def _cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Message cancelled.")
    return ConversationHandler.END


# ── Conversation assembly ─────────────────────────────────────────────────────

# Accept ALL content types: text, photos, documents, video, audio, voice, sticker
ALL_CONTENT = (
    filters.TEXT
    | filters.PHOTO
    | filters.Document.ALL
    | filters.VIDEO
    | filters.AUDIO
    | filters.VOICE
    | filters.Sticker.ALL
)


def msg_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("msg", msg_start)],
        states={
            MSG_TARGET:  [CallbackQueryHandler(msg_target, pattern=r"^msgtgt_")],
            MSG_CONTENT: [MessageHandler(ALL_CONTENT & ~filters.COMMAND, msg_send)],
        },
        fallbacks=[CommandHandler("cancel", _cancel)],
        name="msg_conv",
        per_message=False,
    )
