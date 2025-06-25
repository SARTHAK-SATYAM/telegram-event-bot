import os
import logging
import requests
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

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Stages
EVENT_TYPE, DESCRIPTION, FOLLOWUP = range(3)

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

# Handle event type selection
async def handle_event_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_type = query.data
    context.user_data["event_type"] = event_type
    await query.edit_message_text(f"🎯 Great! Now send me a short description of your {event_type} event.")
    return DESCRIPTION

# AI Response via OpenRouter
async def generate_ai_response(description: str, event_type: str) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "openrouter/auto",  # Use best fit model
        "messages": [
            {
                "role": "system",
                "content": f"You are an expert event planner. Help users plan a {event_type} event."
            },
            {
                "role": "user",
                "content": description
            }
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

# Handle event description
async def handle_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    description = update.message.text
    event_type = context.user_data.get("event_type", "event")

    response = await generate_ai_response(description, event_type)

    await update.message.reply_text(f"📅 Here's your *{event_type.capitalize()} Event Plan*:", parse_mode="Markdown")
    await update.message.reply_text(response, parse_mode="Markdown")

    keyboard = [
        [InlineKeyboardButton("👗 Themes or dress suggestions?", callback_data="theme")],
        [InlineKeyboardButton("🎶 Music and entertainment planning?", callback_data="entertainment")],
        [InlineKeyboardButton("❌ Exit", callback_data="exit")],
    ]
    await update.message.reply_text(
        "Would you like help with anything else?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return FOLLOWUP

# Handle follow-up interactions
async def handle_followup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["followup"] = query.data

    if query.data == "exit":
        await query.edit_message_text("👋 Thank you for using EventBot. Have a great day!")
        return ConversationHandler.END

    await query.edit_message_text(f"🎯 Great! Now send me a short description of your followup: {query.data} event.")
    return DESCRIPTION

# Handle unknown text
async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ I didn’t understand that. Please use /start to begin or /help for assistance.")

# Delete any previous webhook to avoid polling conflict
def clear_webhook():
    try:
        requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
    except Exception as e:
        logger.warning("Webhook cleanup failed: %s", e)

# Main application
async def main():
    clear_webhook()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

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

if __name__ == "__main__":
    nest_asyncio.apply()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
