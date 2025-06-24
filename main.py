import logging
import asyncio
import os
import json
import requests
import datetime
import re
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import nest_asyncio

nest_asyncio.apply()
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
HF_TOKEN = os.getenv("HUGGINGFACE_API_TOKEN")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Google Sheets Setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
gc = gspread.authorize(credentials)
sheet = gc.open(GOOGLE_SHEET_NAME).sheet1

# Hugging Face API Call
async def query_huggingface(prompt):
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 150,
            "temperature": 0.7,
            "do_sample": True
        }
    }
    response = requests.post(
        "https://api-inference.huggingface.co/models/mistralai/Mixtral-8x7B-Instruct-v0.1",
        headers=headers,
        json=payload
    )
    result = response.json()
    if isinstance(result, list):
        return result[0]['generated_text'].strip()
    elif "error" in result:
        return "⚠️ Sorry, the AI service is temporarily unavailable. Please try again later."
    return "🤖 Something went wrong."

# Format into bullet points
def format_response(raw_text, prompt):
    cleaned = raw_text.replace(prompt, '').strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    sentences = re.split(r'\. ', cleaned)
    emojis = ["🎯", "📌", "✨", "💡", "🎉", "📝", "📍"]
    bullet_points = []
    for i, sentence in enumerate(sentences):
        sentence = sentence.strip().strip('.')
        if sentence and len(sentence) < 160:
            emoji = emojis[i % len(emojis)]
            bullet_points.append(f"{emoji} {sentence}.")
        if len(bullet_points) == 5:
            break
    return bullet_points

# Follow-up Suggestions
def get_follow_up_questions(event_type):
    follow_ups = {
        "birthday": [
            "🎁 Want suggestions for birthday return gifts?",
            "📍 Need help finding a venue nearby?"
        ],
        "business": [
            "📅 Need help scheduling or organizing sessions?",
            "📦 Want catering or vendor suggestions?"
        ],
        "wedding": [
            "💒 Need help with wedding themes or outfits?",
            "🎶 Looking for music or entertainment suggestions?"
        ]
    }
    return follow_ups.get(event_type, [])

# Random outro message
sign_offs = [
    "😊 Hope this helps you plan better!",
    "🚀 Ready to make your event unforgettable?",
    "🎈 Let's make it amazing together!",
    "📲 Type anything else or click /start to begin again."
]

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎂 Birthday", callback_data='birthday')],
        [InlineKeyboardButton("💼 Business", callback_data='business')],
        [InlineKeyboardButton("💍 Wedding", callback_data='wedding')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Hi! What type of event are you planning?", reply_markup=reply_markup)

# Handle event type button click
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['event_type'] = query.data
    await query.message.reply_text(f"Great! Now send me a short description of your {query.data} event.")

# Handle message
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event_type = context.user_data.get('event_type')
    if not event_type:
        await update.message.reply_text("Please choose an event type first using /start.")
        return

    user_query = update.message.text
    await update.message.chat.send_action(action="typing")

    # Natural language prompt for AI
    prompt = (
        f"You're an event planner AI. "
        f"Generate a concise {event_type} event plan for: {user_query}. "
        f"Format it into 4-5 bullet points under 100 words. Be clear, fun, and creative."
    )

    result = await query_huggingface(prompt)
    bullet_output = format_response(result, prompt)

    await update.message.reply_text(f"📅 Here's your *{event_type.title()} Event Plan*:", parse_mode='Markdown')
    for point in bullet_output:
        await asyncio.sleep(1.1)
        await update.message.reply_text(point)

    await asyncio.sleep(0.8)
    await update.message.reply_text(random.choice(sign_offs))

    # Follow-up questions
    follow_ups = get_follow_up_questions(event_type)
    if follow_ups:
        await asyncio.sleep(1)
        await update.message.reply_text("Need more help?", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(text=question, callback_data=f"followup:{question}")]
            for question in follow_ups
        ]))

    # Log to Google Sheets
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

# Main app
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot is live...")
    await app.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
