import logging
import asyncio
import os
import json
import requests
import datetime
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import nest_asyncio

nest_asyncio.apply()

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
HF_TOKEN = os.getenv("HUGGINGFACE_API_TOKEN")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Google Sheets Setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
gc = gspread.authorize(credentials)
sheet = gc.open(GOOGLE_SHEET_NAME).sheet1

# Hugging Face Inference API
async def query_huggingface(prompt):
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 150,
            "temperature": 0.75,
            "do_sample": True
        }
    }
    try:
        response = requests.post(
            "https://api-inference.huggingface.co/models/mistralai/Mixtral-8x7B-Instruct-v0.1",
            headers=headers,
            json=payload
        )
        result = response.json()
        if isinstance(result, list):
            return result[0]['generated_text'].strip()
        elif "error" in result:
            return "⚠️ AI service is temporarily down. Try again shortly."
    except Exception as e:
        return f"❌ Failed to reach AI API: {str(e)}"
    return "🤖 Unexpected error."

# Format response to bullet points
def format_response(raw_text, prompt):
    raw_text = raw_text.replace(prompt, '').strip()
    lines = raw_text.replace('\n', ' ').split('. ')
    bullet_points = []
    emojis = ["🎯", "📌", "✨", "💡", "🎉", "📝", "📍"]
    for i, line in enumerate(lines):
        line = line.strip().strip('.')
        if line and len(line) < 200:
            emoji = emojis[i % len(emojis)]
            bullet_points.append(f"{emoji} {line}.")
        if len(bullet_points) == 5:
            break
    return bullet_points

# Follow-up suggestions
def get_follow_up_questions(event_type):
    options = {
        "birthday": ["🎁 Return gift ideas?", "📍 Nearby birthday venues?"],
        "business": ["📅 Schedule planning?", "🍽️ Catering suggestions?"],
        "wedding": ["💒 Theme/outfit help?", "🎶 Music options?"]
    }
    return options.get(event_type, [])

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎂 Birthday", callback_data='birthday')],
        [InlineKeyboardButton("💼 Business", callback_data='business')],
        [InlineKeyboardButton("💍 Wedding", callback_data='wedding')]
    ]
    await update.message.reply_text("Hi! What type of event are you planning?", reply_markup=InlineKeyboardMarkup(keyboard))

# Handle event selection
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['event_type'] = query.data
    await query.message.reply_text(f"Awesome! Now tell me more about your {query.data} event idea.")

# Handle messages and AI processing
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event_type = context.user_data.get('event_type')
    if not event_type:
        await update.message.reply_text("Please choose an event type using /start.")
        return

    user_query = update.message.text
    await update.message.chat.send_action(action="typing")

    prompt = f"📅 Here's your {event_type} event plan:\n• Suggest a {event_type} plan in bullet points.\n• Limit to 100 words.\n• Input: {user_query}"
    ai_response = await query_huggingface(prompt)
    points = format_response(ai_response, prompt)

    await update.message.reply_text(f"📋 *Here’s a quick plan for your {event_type.title()}!*", parse_mode='Markdown')
    for point in points:
        await asyncio.sleep(1)
        await update.message.reply_text(point)

    followups = get_follow_up_questions(event_type)
    if followups:
        await asyncio.sleep(1)
        await update.message.reply_text("Need more help?", reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton(text=q, callback_data=f"followup:{q}")] for q in followups]
        ))

    # Log to Google Sheets
    try:
        sheet.append_row([
            update.effective_user.username,
            event_type,
            user_query,
            ai_response,
            str(datetime.datetime.now())
        ])
    except Exception as e:
        logger.warning(f"Failed to log to Google Sheets: {e}")

# Main loop
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot is live...")
    await app.run_polling()

if __name__ == '__main__':
    import nest_asyncio
    nest_asyncio.apply()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
