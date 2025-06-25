import os
import logging
import base64
import json
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
import nest_asyncio
import asyncio
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GOOGLE_SHEETS_CREDS = os.getenv("GOOGLE_SHEETS_CREDS")  # base64 encoded
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "EventBotLog")

# Constants
MODEL = "openrouter/mistralai/mixtral-8x7b"
EVENT_TYPE, DESCRIPTION, FOLLOWUP = range(3)

# Google Sheets Setup
def init_google_sheets():
    creds_json = json.loads(base64.b64decode(GOOGLE_SHEETS_CREDS).decode("utf-8"))
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
    client = gspread.authorize(creds)
    sheet = client.open(GOOGLE_SHEET_NAME).sheet1
    return sheet

# Log to Google Sheets
def log_to_sheets(user_id, event_type, description, timestamp):
    try:
        sheet = init_google_sheets()
        sheet.append_row([str(user_id), event_type, description, timestamp])
    except Exception as e:
        logger.error(f"Logging to Sheets failed: {e}")

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton("🎂 Birthday", callback_data='birthday')],
        [InlineKeyboardButton("💼 Business", callback_data='business')],
        [InlineKeyboardButton("💍 Wedding", callback_data='wedding')],
    ]
    await update.message.reply_text(
        "👋 Hi! What type of event are you planning?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return EVENT_TYPE

# Help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ I’m EventBot! Here’s what I can help with:\n"
        "/start – Begin planning your event\n"
        "/help – Show help info\n"
        "/exit – Exit the conversation"
    )

# Exit command
async def exit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Thank you for using EventBot. Have a great day!")
    return ConversationHandler.END

# Event type selection
async def handle_event_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_type = query.data
    context.user_data["event_type"] = event_type
    await query.edit_message_text(f"🎯 Great! Now send me a short description of your {event_type} event.")
    return DESCRIPTION

# AI response
async def generate_ai_response(description: str, event_type: str) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    prompt = (
        f"You are a creative event planner. Plan a {event_type} with the following description:\n\n"
        f"{description}\n\n"
        "Respond clearly with structured suggestions, bullet points, and friendly tone. Use emojis where helpful."
    )
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a professional AI assistant that helps plan events with helpful, creative suggestions."},
            {"role": "user", "content": prompt}
        ]
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"AI Error: {e}")
        return "⚠️ Sorry, I couldn't generate a response at the moment."

# Handle description + log + suggest next
async def handle_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    description = update.message.text
    event_type = context.user_data.get("event_type", "event")
    user_id = update.message.from_user.id
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # AI + Google Sheets
    response = await generate_ai_response(description, event_type)
    log_to_sheets(user_id, event_type, description, timestamp)

    await update.message.reply_text(f"📅 Here's your *{event_type.capitalize()} Event Plan*:", parse_mode="Markdown")
    await update.message.reply_text(response, parse_mode="Markdown")

    # More Inline Options
    keyboard = [
        [InlineKeyboardButton("📍 Set Location", callback_data="location"),
         InlineKeyboardButton("📅 Set Date", callback_data="date")],
        [InlineKeyboardButton("💰 Set Budget", callback_data="budget"),
         InlineKeyboardButton("📋 Checklist", callback_data="checklist")],
        [InlineKeyboardButton("❌ Exit", callback_data="exit")]
    ]
    await update.message.reply_text(
        "Would you like to customize or explore more?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return FOLLOWUP

# Follow-up flow
async def handle_followup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selection = query.data

    if selection == "exit":
        await query.edit_message_text("👋 Thank you for using EventBot. All the best with your event!")
        return ConversationHandler.END

    context.user_data["event_type"] = selection
    await query.edit_message_text(f"📝 Please provide details for: *{selection}*", parse_mode="Markdown")
    return DESCRIPTION

# Unknown command fallback
async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ I didn’t understand that. Use /start to begin or /help for more info.")

# Clean previous webhooks
def clear_webhook():
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook")
    except Exception as e:
        logger.warning("Webhook cleanup failed: %s", e)

# Main App
async def main():
    clear_webhook()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            EVENT_TYPE: [CallbackQueryHandler(handle_event_type)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description)],
            FOLLOWUP: [CallbackQueryHandler(handle_followup)],
        },
        fallbacks=[
            CommandHandler("help", help_command),
            CommandHandler("exit", exit_command),
        ],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("exit", exit_command))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_message))

    await app.run_polling()

import asyncio

if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        pass


