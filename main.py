import logging
import asyncio
import os
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
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
import httpx

nest_asyncio.apply()
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Google Sheets Setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
gc = gspread.authorize(credentials)
sheet = gc.open(GOOGLE_SHEET_NAME).sheet1

# OpenRouter AI Call
async def query_openrouter(prompt):
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/EnigmaEventBot",
    }

    payload = {
        "model": "mistralai/mixtral-8x7b-instruct",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a creative and helpful event planner. "
                    "Give clear, friendly bullet-point suggestions (7–10), using emojis. "
                    "Include theme, food, logistics, venue suggestions based on location, etc. "
                    "Always end with a human-like follow-up question to refine the plan."
                )
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 500,
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

# Follow-up Question Suggestions
def get_follow_up_questions(event_type):
    follow_ups = {
        "birthday": [
            "🎁 Suggestions for return gifts?",
            "📍 Venue recommendations in your area?",
            "🍰 Cake and catering options?",
            "🎊 Decoration themes for kids?"
        ],
        "business": [
            "📅 Help with scheduling or logistics?",
            "🍽️ Catering options?",
            "📢 Need guest speaker suggestions?",
            "📈 How to promote the event?"
        ],
        "wedding": [
            "💒 Themes or dress suggestions?",
            "🎶 Music and entertainment planning?",
            "📷 Photography ideas?",
            "🍽️ Food and drink packages?"
        ]
    }
    return follow_ups.get(event_type, [])

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
        "2. Describe the event (e.g., 'Jungle theme birthday for 10-year-old in Mumbai').\n"
        "3. Get AI-curated suggestions in bullet points.\n"
        "4. Tap follow-up questions to refine your plan.\n\n"
        "Need more support? Just ask!"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

# Event selection
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "exit":
        await query.message.reply_text("👋 Alright! I'm here if you need help again. Just type /start.")
        return

    context.user_data['event_type'] = query.data
    await query.message.reply_text(f"🎯 Great! Now send me a short description of your {query.data} event.")

# Follow-up handler
async def handle_followup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    followup_text = query.data.replace("followup:", "").strip()
    event_type = context.user_data.get("event_type", "event")

    await query.message.chat.send_action(action=ChatAction.TYPING)
    await asyncio.sleep(1.2)
    await query.message.reply_text(f"🧠 Processing your follow-up: {followup_text}")

    prompt = (
        f"You are a helpful event planner. Respond to this question: '{followup_text}' "
        f"with 7–10 bullet points, using emojis, and include suggestions based on the context. "
        f"If relevant, recommend resorts or venues based on inferred location from user's original input. "
        f"End with a human-like follow-up question."
    )

    result = await query_openrouter(prompt)
    for point in result.strip().split('\n'):
        if point.strip():
            await asyncio.sleep(1)
            await query.message.reply_text(point.strip())

    follow_ups = get_follow_up_questions(event_type)
    if follow_ups:
        await asyncio.sleep(1)
        await query.message.reply_text("Would you like more help?", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(text=q, callback_data=f"followup:{q}")] for q in follow_ups
        ] + [[InlineKeyboardButton("🔴 Exit", callback_data="exit")]]))

# Handle user message
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event_type = context.user_data.get('event_type')
    if not event_type:
        await update.message.reply_text("Please choose an event type first using /start.")
        return

    user_query = update.message.text
    await update.message.chat.send_action(action=ChatAction.TYPING)
    await asyncio.sleep(1.5)

    prompt = (
        f"As an expert event planner, analyze the following user input for a {event_type} event: '{user_query}'. "
        f"Generate 7–10 clear, bullet-pointed suggestions using emojis. Include themes, catering, entertainment, "
        f"logistics, and personalized venue recommendations inferred from any mentioned location or preferences. "
        f"End with a follow-up question to get more clarity (budget, guests, etc)."
    )

    result = await query_openrouter(prompt)
    await update.message.reply_text(f"📅 Here's your *{event_type.title()} Event Plan*:", parse_mode='Markdown')

    for point in result.strip().split('\n'):
        if point.strip():
            await asyncio.sleep(1.1)
            await update.message.reply_text(point.strip())

    follow_ups = get_follow_up_questions(event_type)
    if follow_ups:
        await asyncio.sleep(1)
        await update.message.reply_text("Would you like help with anything else?", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(text=q, callback_data=f"followup:{q}")] for q in follow_ups
        ] + [[InlineKeyboardButton("🔴 Exit", callback_data="exit")]]))

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

# Main App
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_callback, pattern=r'^(birthday|business|wedding|exit)$'))
    app.add_handler(CallbackQueryHandler(handle_followup, pattern=r'^followup:'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Bot is live and polling...")
    await app.run_polling()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception(f"🔥 Unhandled Exception in main: {e}")
