import os
import requests
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import gspread
from datetime import datetime

# Load env variables
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
HF_API_KEY = os.getenv("HF_API_KEY")
HF_MODEL = "HuggingFaceH4/zephyr-7b-beta"
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")

# Hugging Face header
headers = {
    "Authorization": f"Bearer {HF_API_KEY}",
    "Content-Type": "application/json"
}

# Connect to Google Sheets
gc = gspread.service_account(filename="creds.json")
sheet = gc.open(GOOGLE_SHEET_NAME).sheet1

# /start handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎉 Birthday", callback_data='birthday')],
        [InlineKeyboardButton("💍 Wedding", callback_data='wedding')],
        [InlineKeyboardButton("💼 Corporate", callback_data='corporate')]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Hi! 👋 What type of event are you planning?", reply_markup=markup)

# Button click handler
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["event_type"] = query.data
    await query.edit_message_text(
        text=f"Great! You selected *{query.data.title()}*. Now tell me your city, budget, or preferences.",
        parse_mode="Markdown"
    )

# Handle user input
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    user_id = update.effective_user.id
    event_type = context.user_data.get("event_type", "event")
    await update.message.reply_text("🤖 Thinking...")

    try:
        prompt = (
            f"Give a short and clear 5-line suggestion for a {event_type} based on: {user_input}. "
            f"Only include venue, theme, budget, and unique ideas. Be concise."
        )
        payload = {"inputs": prompt}
        response = requests.post(
            f"https://api-inference.huggingface.co/models/{HF_MODEL}",
            headers=headers,
            json=payload
        )
        result = response.json()
        print("HF RAW RESPONSE:", result)

        if isinstance(result, list) and "generated_text" in result[0]:
            reply = result[0]["generated_text"][len(prompt):].strip()
            lines = reply.replace("\n\n", "\n").split("\n")
            lines = [line.strip() for line in lines if line.strip()]
            formatted = "\n".join(f"🔹 {line}" for line in lines[:5])
            if len(formatted) > 1000:
                formatted = formatted[:1000] + "...\n\n⚠️ Trimmed for clarity."

            # Log to Google Sheets
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet.append_row([str(user_id), event_type, user_input, formatted, timestamp])

            await update.message.reply_text(formatted or "🤷 No response generated.")
        else:
            await update.message.reply_text("⚠️ AI model error. Try again.")
            print("HF Error:", result)

    except Exception as e:
        print("Exception:", e)
        await update.message.reply_text("❌ Something went wrong. Try again later.")

# Bot launcher
async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot is live...")
    await app.run_polling()

# Run bot with asyncio fix
if __name__ == "__main__":
    import asyncio
    try:
        asyncio.get_event_loop().run_until_complete(main())
    except RuntimeError:
        import nest_asyncio
        nest_asyncio.apply()
        asyncio.get_event_loop().run_until_complete(main())
