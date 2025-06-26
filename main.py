import os
import logging
import requests
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
HF_API_KEY = os.getenv("HUGGINGFACE_API_TOKEN")
GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEET_NAME")

# Setup Google Sheets logging
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
client = gspread.authorize(creds)
sheet = client.open("EventBotLogs").sheet1

# Stages
EVENT_TYPE, DESCRIPTION, FOLLOWUP = range(3)

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

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ I’m EventBot! Here’s what I can help with:\n"
        "/start – Begin planning your event\n"
        "/help – Show help info\n"
        "/exit – Exit the conversation"
    )

async def exit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Thank you for using EventBot. Have a great day!")
    return ConversationHandler.END

async def handle_event_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_type = query.data
    context.user_data["event_type"] = event_type
    await query.edit_message_text(f"🎯 Great! Now send me a short description of your {event_type} event.")
    return DESCRIPTION
async def generate_ai_response(description: str, event_type: str) -> str:
    headers = {
        "Authorization": f"Bearer {HF_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": (
            f"You are an expert event planner. Help the user organize a {event_type} event.\n"
            f"User’s message: {description}\n"
            f"Respond with bullet points in a clear and friendly manner."
        )
    }

    try:
        response = requests.post(
            "https://api-inference.huggingface.co/models/tiiuae/falcon-7b-instruct",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()

        data = response.json()
        logger.info(f"HF Raw Response: {data}")

        # Handles both list and dict responses
        if isinstance(data, list) and "generated_text" in data[0]:
            return data[0]["generated_text"].strip()
        elif isinstance(data, dict) and "generated_text" in data:
            return data["generated_text"].strip()
        elif "error" in data:
            return f"❌ HuggingFace Error: {data['error']}"
        else:
            return "❌ Sorry, I didn’t get a valid response from the AI."
    except requests.exceptions.RequestException as e:
        logger.error(f"Request Error: {e}")
        return "❌ API request failed. Please try again later."
    except Exception as e:
        logger.error(f"Unexpected HF error: {e}")
        return "❌ An unexpected error occurred while generating the response."


async def handle_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    description = update.message.text
    event_type = context.user_data.get("event_type", "event")

    await update.message.chat.send_action(action=ChatAction.TYPING)
    await update.message.reply_text(f"🤔 Okay, give me a sec to plan your *{event_type.capitalize()}* event...", parse_mode="Markdown")

    response = await generate_ai_response(description, event_type)

    try:
        sheet.append_row([time.strftime("%Y-%m-%d %H:%M:%S"), update.effective_user.username or update.effective_user.first_name, event_type, description, response])
    except Exception as e:
        logger.warning(f"⚠️ Google Sheets Logging Failed: {e}")

    await update.message.chat.send_action(action=ChatAction.TYPING)
    await update.message.reply_text(f"📅 Here's your *{event_type.capitalize()} Event Plan*:", parse_mode="Markdown")
    await update.message.reply_text(response, parse_mode="Markdown")

    keyboard = [
        [InlineKeyboardButton("👗 Themes?", callback_data="theme")],
        [InlineKeyboardButton("🎶 Entertainment?", callback_data="entertainment")],
        [InlineKeyboardButton("✅ Checklist", callback_data="checklist")],
        [InlineKeyboardButton("❌ Exit", callback_data="exit")],
    ]
    await update.message.reply_text(
        "Would you like help with anything else?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return FOLLOWUP

async def handle_followup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["followup"] = query.data

    if query.data == "exit":
        await query.edit_message_text("👋 Thank you for using EventBot. Have a great day!")
        return ConversationHandler.END

    await query.edit_message_text(f"🎯 Great! Now send me a short description for: {query.data}")
    return DESCRIPTION

async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ I didn’t understand that. Use /start to begin or /help for guidance.")

async def clear_webhook():
    try:
        response = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook")
        if response.ok:
            logger.info("✅ Webhook deleted successfully.")
        else:
            logger.warning(f"⚠️ Webhook deletion failed: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"❌ Webhook cleanup error: {e}")

async def main():
    await clear_webhook()

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
        allow_reentry=True
    )

    # Register handlers
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("exit", exit_command))

    # Catch all unexpected messages that are commands
    app.add_handler(MessageHandler(filters.TEXT & filters.COMMAND, unknown_message))


    await app.run_polling()

# Main runner
if __name__ == "__main__":
    import asyncio
    import nest_asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    nest_asyncio.apply()

    try:
        loop.run_until_complete(main())
    except Exception as e:
        logger.exception(f"🔥 Unhandled Exception in main: {e}")

