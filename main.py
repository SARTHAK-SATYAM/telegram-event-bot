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

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
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
        "model": "openrouter/auto",
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

# Handle follow-up interactions
async def handle_followup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["followup"] = query.data

    if query.data == "exit":
        await query.edit_message_text("👋 Thank you for using EventBot. Have a great day!")
        return ConversationHandler.END

    await query.edit_message_text(f"🎯 Great! Now send me a short description for: {query.data}")
    return DESCRIPTION

# Unknown command fallback
async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ I didn’t understand that. Use /start to begin or /help for guidance.")

# Async webhook cleaner
async def clear_webhook():
    try:
        response = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook")
        if response.ok:
            logger.info("✅ Webhook deleted successfully.")
        else:
            logger.warning(f"⚠️ Webhook deletion failed: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"❌ Webhook cleanup error: {e}")

# Main entry
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
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("exit", exit_command))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_message))

    await app.run_polling()

# Safe event loop startup
if __name__ == "__main__":
    import asyncio
    import sys

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Workaround for already running loop in environments like Jupyter/Render
            task = loop.create_task(main())
        else:
            loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Bot stopped cleanly.")
    except RuntimeError as e:
        print(f"RuntimeError: {e}")
        sys.exit(1)

