# 📅 Enigma EventBot — AI-Powered Event Planning on Telegram

**EventBot** is a conversational Telegram assistant that helps users effortlessly plan events—🎂 Birthdays, 💼 Business gatherings, 💍 Weddings—through AI-generated, actionable suggestions.

Built with a focus on usability, responsiveness, and human-like interaction, it keeps the planning experience smart, intuitive, and ongoing.

---

## 🚀 Features

- 🤖 AI-generated suggestions using OpenRouter's Mixtral-8x7B-Instruct.
- 💬 Interactive multi-step chat with emoji-rich bullet points.
- 🏷️ Inline event category selection (`Birthday`, `Business`, `Wedding`).
- 🔄 Continuous conversation loop with dynamic follow-up questions.
- 📍 Intelligent venue recommendations inferred from user input.
- 📊 Logs conversations to Google Sheets.
- 🧠 Simulates human-like typing/thinking pauses.
- 🔒 Fully async, reliable deployment-ready code.

---

## 🛠 Tech Stack

| Layer             | Stack Used                        |
|------------------|-----------------------------------|
| Language          | Python 3.11+                      |
| Bot Framework     | `python-telegram-bot`             |
| AI Model Backend  | `OpenRouter API` (Mixtral model)  |
| Logging/Storage   | `Google Sheets` via `gspread`     |
| HTTP Requests     | `httpx` (async)                   |
| Hosting Ready     | ✅ Render, Railway, or Heroku      |

---

## 🧑‍💻 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/SARTHAK-SATYAM/telegram-event-bot.git
cd telegram-event-bot
