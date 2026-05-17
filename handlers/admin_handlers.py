"""
handlers/admin_handlers.py
Core-leadership-only commands: /adduser, /removeuser, /setrole, /setavenue,
/announce, /report, and escalation helpers.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters,
)
import database as db
from utils import role_keyboard, avenue_keyboard, format_task_card
from config import ROLE_CORE, ROLE_DIRECTOR, ROLE_MEMBER

logger = logging.getLogger(__name__)

# ConversationHandler states
(ADD_TG_ID, ADD_NAME, ADD_ROLE, ADD_AVENUE,
 ANNOUNCE_TEXT,
 SET_ROLE_ID, SET_ROLE_PICK,
 SET_AV_ID, SET_AV_PICK) = range(9)


def is_core(user_id: int) -> bool:
    u = db.get_user(user_id)
    return u is not None and u["role"] == ROLE_CORE


def core_only(func):
    """Decorator: block non-core users."""
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not is_core(update.effective_user.id):
            await update.message.reply_text(
                "🚫 This command is restricted to *Core Leadership* only.",
                parse_mode="Markdown",
            )
            return ConversationHandler.END
        return await func(update, ctx)
    wrapper.__name__ = func.__name__
    return wrapper


# ── /adduser ─────────────────────────────────────────────────────────────────

@core_only
async def adduser_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "➕ *Add New User*\n\nSend the user's *Telegram ID*.\n"
        "(They can find their ID using @userinfobot)\n\n"
        "/cancel to abort.",
        parse_mode="Markdown",
    )
    return ADD_TG_ID


async def adduser_get_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["new_tg_id"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Invalid ID. Send a numeric Telegram ID.")
        return ADD_TG_ID
    await update.message.reply_text("📝 Enter the user's *full name*:", parse_mode="Markdown")
    return ADD_NAME


async def adduser_get_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["new_name"] = update.message.text.strip()
    await update.message.reply_text(
        "🏷️ Select their *role*:", parse_mode="Markdown",
        reply_markup=role_keyboard("adduserrole"),
    )
    return ADD_ROLE


async def adduser_get_role(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["new_role"] = query.data.replace("adduserrole_", "")
    await query.message.reply_text(
        "🏢 Select their *avenue*:", parse_mode="Markdown",
        reply_markup=avenue_keyboard("adduserav"),
    )
    return ADD_AVENUE


async def adduser_get_avenue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    avenue = query.data.replace("adduserav_", "")
    tg_id  = ctx.user_data["new_tg_id"]
    name   = ctx.user_data["new_name"]
    role   = ctx.user_data["new_role"]

    db.add_user(telegram_id=tg_id, name=name, username="", role=role, avenue=avenue)
    await query.message.reply_text(
        f"✅ *User Added!*\n\n"
        f"👤 Name: {name}\n🆔 ID: {tg_id}\n"
        f"🏷️ Role: {role}\n🏢 Avenue: {avenue}",
        parse_mode="Markdown",
    )
    ctx.user_data.clear()
    return ConversationHandler.END


# ── /removeuser ───────────────────────────────────────────────────────────────

@core_only
async def removeuser(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args:
        await update.message.reply_text("Usage: `/removeuser <telegram_id>`", parse_mode="Markdown")
        return
    try:
        tg_id = int(args[0])
        db.remove_user(tg_id)
        await update.message.reply_text(f"✅ User `{tg_id}` removed.", parse_mode="Markdown")
    except (ValueError, Exception) as e:
        await update.message.reply_text(f"❌ Error: {e}")


# ── /setrole ──────────────────────────────────────────────────────────────────

@core_only
async def setrole_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏷️ *Set User Role*\n\nSend the user's *Telegram ID*:",
        parse_mode="Markdown",
    )
    return SET_ROLE_ID


async def setrole_get_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["setrole_id"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Invalid ID.")
        return SET_ROLE_ID
    await update.message.reply_text(
        "Pick new role:", reply_markup=role_keyboard("setrolepick")
    )
    return SET_ROLE_PICK


async def setrole_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    role  = query.data.replace("setrolepick_", "")
    tg_id = ctx.user_data["setrole_id"]
    db.update_user_role(tg_id, role)
    await query.message.reply_text(
        f"✅ Role of `{tg_id}` updated to *{role}*.", parse_mode="Markdown"
    )
    return ConversationHandler.END


# ── /setavenue ────────────────────────────────────────────────────────────────

@core_only
async def setavenue_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏢 *Set User Avenue*\n\nSend the user's *Telegram ID*:",
        parse_mode="Markdown",
    )
    return SET_AV_ID


async def setavenue_get_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["setav_id"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Invalid ID.")
        return SET_AV_ID
    await update.message.reply_text(
        "Pick avenue:", reply_markup=avenue_keyboard("setavpick")
    )
    return SET_AV_PICK


async def setavenue_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    avenue = query.data.replace("setavpick_", "")
    tg_id  = ctx.user_data["setav_id"]
    db.update_user_avenue(tg_id, avenue)
    await query.message.reply_text(
        f"✅ Avenue of `{tg_id}` set to *{avenue}*.", parse_mode="Markdown"
    )
    return ConversationHandler.END


# ── /announce ─────────────────────────────────────────────────────────────────

@core_only
async def announce_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📢 *Broadcast Announcement*\n\nType the announcement message:\n\n/cancel to abort.",
        parse_mode="Markdown",
    )
    return ANNOUNCE_TEXT


async def announce_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg  = update.message.text
    users = db.get_all_users()
    text  = (
        f"📢 *Rotaract Club Announcement*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{msg}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"— Core Leadership"
    )
    sent = 0
    for u in users:
        try:
            await ctx.bot.send_message(u["telegram_id"], text, parse_mode="Markdown")
            sent += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ Announcement sent to {sent} members.")
    return ConversationHandler.END


# ── /report ───────────────────────────────────────────────────────────────────

@core_only
async def report_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    from scheduler import build_report_text
    text = build_report_text()
    await update.message.reply_text(text, parse_mode="Markdown")


# ── /listusers ────────────────────────────────────────────────────────────────

@core_only
async def listusers(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    users = db.get_all_users()
    if not users:
        await update.message.reply_text("No users registered yet.")
        return
    lines = ["👥 *Registered Members*\n━━━━━━━━━━━━━━━━━━━━"]
    for u in users:
        lines.append(
            f"• *{u['name']}* | {u['role']} | {u['avenue'] or 'No avenue'} | `{u['telegram_id']}`"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── /cancel ───────────────────────────────────────────────────────────────────

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END


# ── Conversation handlers assembly ────────────────────────────────────────────

def adduser_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("adduser", adduser_start)],
        states={
            ADD_TG_ID:  [MessageHandler(filters.TEXT & ~filters.COMMAND, adduser_get_id)],
            ADD_NAME:   [MessageHandler(filters.TEXT & ~filters.COMMAND, adduser_get_name)],
            ADD_ROLE:   [CallbackQueryHandler(adduser_get_role, pattern=r"^adduserrole_")],
            ADD_AVENUE: [CallbackQueryHandler(adduser_get_avenue, pattern=r"^adduserav_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="adduser_conv",
        persistent=False,
    )


def setrole_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("setrole", setrole_start)],
        states={
            SET_ROLE_ID:   [MessageHandler(filters.TEXT & ~filters.COMMAND, setrole_get_id)],
            SET_ROLE_PICK: [CallbackQueryHandler(setrole_pick, pattern=r"^setrolepick_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )


def setavenue_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("setavenue", setavenue_start)],
        states={
            SET_AV_ID:   [MessageHandler(filters.TEXT & ~filters.COMMAND, setavenue_get_id)],
            SET_AV_PICK: [CallbackQueryHandler(setavenue_pick, pattern=r"^setavpick_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )


def announce_conv() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("announce", announce_start)],
        states={
            ANNOUNCE_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, announce_send)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
