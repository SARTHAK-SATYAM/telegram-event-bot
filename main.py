import logging
import asyncio
import os
import json
import requests
import datetime
import time
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
HF_TOKEN = os.getenv("HUGGINGFACE_API_TOKEN")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
gc = gspread.authorize(credentials)
sheet = gc.open(GOOGLE_SHEET_NAME).sheet1

async def query_openrouter(prompt):
    import httpx
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/EnigmaEventBot",
    }
    payload = {
        "model": "mistralai/mixtral-8x7b-instruct",
        "messages": [
            {"role": "system", "content": "You are a helpful and concise event planner that responds in bullet points and emojis."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 300,
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"⚠️ OpenRouter API Error: {e}")
        return f"⚠️ AI service failed: {str(e)}"

def format_response(raw_text, prompt):
    raw_text = raw_text.replace(prompt, "").strip()
    lines = raw_text.replace('\n', ' ').split('. ')
    bullet_points = []
    emojis = ["🎯", "📌", "✨", "💡", "🎉", "📝", "📍"]
    for i, line in enumerate(lines):
        line = line.strip().strip('.')
        if line and len(line) < 200:
            emoji = emojis[i % len(emojis)]
            bullet_points.append(f"{emoji} {line}.")
        if len(bullet_points) == 10:
            break
    return bullet_points

def get_follow_up_questions(event_type):
    follow_ups = {
        "birthday": [
            "🎁 Suggestions for return gifts?",
            "📍 Venue recommendations in your area?",
            "🍽️ What type of food should be served?",
            "🕒 What is the event duration?"
        ],
        "business": [
            "📅 Help with scheduling or logistics?",
            "🍽️ Catering options?",
            "🎤 Need guest speaker suggestions?",
            "📈 How to promote the event?"
        ],
        "wedding": [
            "💒 Themes or dress suggestions?",
            "🎶 Music and entertainment planning?",
            "🍴 Food and drink recommendations?",
            "🕒 Timeline and schedule setup?"
        ]
    }
    return follow_ups.get(event_type, [])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎂 Birthday", callback_data='birthday')],
        [InlineKeyboardButton("💼 Business", callback_data='business')],
        [InlineKeyboardButton("💍 Wedding", callback_data='wedding')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Hi! What type of event are you planning?", reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🆘 *How to Use EventBot*\n\n"
        "1. Type /start to select an event category.\n"
        "2. Describe the event (e.g., 'Jungle theme birthday for 10-year-old in Mumbai').\n"
        "3. Get AI-curated suggestions in bullet points.\n"
        "4. Tap follow-up questions to refine your plan.\n\n"
        "Need more support? Just ask!"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("followup:"):
        followup = data.replace("followup:", "")
        event_type = context.user_data.get('event_type', 'event')
        user_query = context.user_data.get('user_query', '')
        prompt = f"Continue planning the {event_type} event. Focus on: {followup}. So far: {user_query}"
        result = await query_openrouter(prompt)
        formatted = format_response(result, prompt)
        await query.message.reply_text(f"📌 Here's your Followup: {followup}\n")
        for line in formatted:
            await asyncio.sleep(1)
            await query.message.reply_text(line)

        follow_ups = get_follow_up_questions(event_type)
        keyboard = [[InlineKeyboardButton(q, callback_data=f"followup:{q}")] for q in follow_ups]
        keyboard.append([InlineKeyboardButton("🛑 Exit", callback_data="exit")])
        await asyncio.sleep(1)
        await query.message.reply_text("Would you like more help?", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "exit":
        await query.message.reply_text("👋 Thank you! Feel free to start again anytime with /start.")
    else:
        context.user_data['event_type'] = data
        await query.message.reply_text(f"🎯 Great! Now send me a short description of your {data} event.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event_type = context.user_data.get('event_type')
    if not event_type:
        await update.message.reply_text("Please choose an event type first using /start.")
        return

    user_query = update.message.text
    context.user_data['user_query'] = user_query

    await update.message.chat.send_action(action="typing")
    prompt = f"Suggest a {event_type} event plan in bullet points. Limit to 100 words. Input: {user_query}"
    result = await query_openrouter(prompt)
    formatted_points = format_response(result, prompt)

    await update.message.reply_text(f"📅 Here's your *{event_type.title()} Event Plan*:", parse_mode='Markdown')
    for point in formatted_points:
        await asyncio.sleep(1.1)
        await update.message.reply_text(point)

    follow_ups = get_follow_up_questions(event_type)
    keyboard = [[InlineKeyboardButton(q, callback_data=f"followup:{q}")] for q in follow_ups]
    keyboard.append([InlineKeyboardButton("🛑 Exit", callback_data="exit")])
    await asyncio.sleep(1)
    await update.message.reply_text("Would you like help with anything else?", reply_markup=InlineKeyboardMarkup(keyboard))

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

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot is live and polling...")
    await app.run_polling()

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
