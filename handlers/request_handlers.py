"""
handlers/request_handlers.py
Inter-avenue work request flow: /request command.
"""

import logging
from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
import database as db
from utils import (
    format_request_card, request_action_keyboard, avenue_keyboard,
)

logger = logging.getLogger(__name__)

# Conversation states
(REQ_TO_AVENUE, REQ_DESC, REQ_DEADLINE) = range(3)


async def request_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = db.get_user(update.effective_user.id)
    if not u:
        await update.message.reply_text("⚠️ Please /start first to register.")
        return ConversationHandler.END
    ctx.user_data.clear()
    ctx.user_data["from_avenue"] = u["avenue"] or "Unknown"

    await update.message.reply_text(
        "📨 *Inter-Avenue Request — Step 1/3*\n\n"
        "Which avenue do you need help from?\n\n/cancel to abort.",
        parse_mode="Markdown",
        reply_markup=avenue_keyboard("reqtoa"),
    )
    return REQ_TO_AVENUE


async def req_to_avenue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["to_avenue"] = query.data.replace("reqtoa_", "")
    await query.message.reply_text(
        "📝 *Step 2/3* — Describe what you need:",
        parse_mode="Markdown",
    )
    return REQ_DESC


async def req_desc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["desc"] = update.message.text.strip()
    await update.message.reply_text(
        "📅 *Step 3/3* — Enter the *deadline* (`YYYY-MM-DD HH:MM`) or type `none`:",
        parse_mode="Markdown",
    )
    return REQ_DEADLINE


async def req_deadline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == "none":
        deadline = None
    else:
        try:
            from datetime import datetime
            datetime.strptime(text, "%Y-%m-%d %H:%M")
            deadline = text
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid format. Use `YYYY-MM-DD HH:MM` or `none`.",
                parse_mode="Markdown",
            )
            return REQ_DEADLINE

    ud       = ctx.user_data
    user_id  = update.effective_user.id
    req_id   = db.create_request(
        from_avenue=ud["from_avenue"],
        to_avenue=ud["to_avenue"],
        description=ud["desc"],
        deadline=deadline,
        requested_by=user_id,
    )
    req = db.get_request(req_id)

    # Notify director of the target avenue
    director = db.get_avenue_director(ud["to_avenue"])
    card_text = (
        f"📨 *New Request for {ud['to_avenue']}!*\n\n"
        + format_request_card(req)
    )
    if director:
        try:
            await update.get_bot().send_message(
                director["telegram_id"],
                card_text,
                parse_mode="Markdown",
                reply_markup=request_action_keyboard(req_id),
            )
        except Exception as e:
            logger.warning("Could not notify director: %s", e)

    # Also notify all members of target avenue
    members = db.get_users_by_avenue(ud["to_avenue"])
    for m in members:
        if director and m["telegram_id"] == director["telegram_id"]:
            continue  # already notified
        try:
            await update.get_bot().send_message(
                m["telegram_id"],
                card_text,
                parse_mode="Markdown",
                reply_markup=request_action_keyboard(req_id),
            )
        except Exception:
            pass

    await update.message.reply_text(
        f"✅ *Request #{req_id} Sent!*\n\n" + format_request_card(req),
        parse_mode="Markdown",
    )
    ctx.user_data.clear()
    return ConversationHandler.END


# ── Request action callback (Accept / Decline / Done) ────────────────────────

async def request_action_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # e.g. "req_accept_5"

    parts  = data.split("_")
    action = parts[1]   # accept | decline | done
    req_id = int(parts[2])

    status_map = {
        "accept":  "Accepted",
        "decline": "Declined",
        "done":    "Completed",
    }
    new_status = status_map.get(action)
    if not new_status:
        return

    db.update_request_status(req_id, new_status)
    req = db.get_request(req_id)

    # Notify requester
    requester = db.get_user(req["requested_by"])
    if requester:
        try:
            await ctx.bot.send_message(
                requester["telegram_id"],
                f"🔄 *Your request #{req_id} to {req['to_avenue']} is now: {new_status}*\n\n"
                + format_request_card(req),
                parse_mode="Markdown",
            )
        except Exception:
            pass

    await query.edit_message_text(
        f"✅ Request #{req_id} marked as *{new_status}*.\n\n" + format_request_card(req),
        parse_mode="Markdown",
    )


# ── Conversation assembly ─────────────────────────────────────────────────────

async def _cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Request cancelled.")
    return ConversationHandler.END


def request_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("request", request_start)],
        states={
            REQ_TO_AVENUE: [CallbackQueryHandler(req_to_avenue, pattern=r"^reqtoa_")],
            REQ_DESC:      [MessageHandler(filters.TEXT & ~filters.COMMAND, req_desc)],
            REQ_DEADLINE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, req_deadline)],
        },
        fallbacks=[CommandHandler("cancel", _cancel)],
        name="request_conv",
    )
