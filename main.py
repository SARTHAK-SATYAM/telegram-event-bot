import logging
import asyncio
import os
import datetime
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import nest_asyncio

nest_asyncio.apply()
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Google Sheets Setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
gc = gspread.authorize(credentials)
sheet = gc.open(GOOGLE_SHEET_NAME).sheet1

# OpenRouter AI API
async def query_openrouter(prompt):
    import httpx

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/EnigmaEventBot",
    }

    messages = [
        {"role": "system", "content": (
            "You are an expert event planner. Respond in friendly, concise bullet points (5-10),"
            " include emojis, actionable advice, and helpful suggestions. Always end with follow-up questions"
            " such as budget, food, music, and venue preferences to keep the conversation going."
        )},
        {"role": "user", "content": prompt},
    ]

    payload = {
        "model": "mistralai/mixtral-8x7b-instruct",
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": 500,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=40,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"⚠️ OpenRouter API Error: {e}")
        return f"⚠️ AI service failed: {str(e)}"

# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎂 Birthday", callback_data='birthday')],
        [InlineKeyboardButton("💼 Business", callback_data='business')],
        [InlineKeyboardButton("💍 Wedding", callback_data='wedding')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Hi! What type of event are you planning?", reply_markup=reply_markup)

# /help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🆘 *How to Use EventBot*\n\n"
        "1. Type /start to select an event category.\n"
        "2. Describe the event (e.g., 'Budget-friendly wedding in Delhi with floral theme').\n"
        "3. Receive AI-curated plans in bullet points.\n"
        "4. Use follow-up buttons to refine your planning.\n\n"
        "Just type your idea, and we'll help you plan!"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

# Event button selected
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['event_type'] = query.data
    await query.message.reply_text(f"📌 Great! Send me a short description of your {query.data} event.")

# Message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event_type = context.user_data.get('event_type')
    if not event_type:
        await update.message.reply_text("Please choose an event type using /start first.")
        return

    user_query = update.message.text.strip()
    await update.message.chat.send_action(action="typing")

    prompt = f"Plan a {event_type} event with the following description: {user_query}"
    result = await query_openrouter(prompt)

    await update.message.reply_text(f"📅 Here's your *{event_type.title()} Event Plan*:", parse_mode='Markdown')
    for line in result.strip().split('\n'):
        if line.strip():
            await asyncio.sleep(1)
            await update.message.reply_text(line.strip())

    # Log interaction
    try:
        sheet.append_row([
            update.effective_user.username,
            event_type,
            user_query,
            result,
            str(datetime.datetime.now())
        ])
    except Exception as e:
        logger.warning(f"[Sheets] Logging failed: {e}")

# Main
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Bot is live and polling...")
    await app.run_polling()

if __name__ == "__main__":
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
