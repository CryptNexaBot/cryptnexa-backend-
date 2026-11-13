import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

WEBAPP_URL = "https://cryptnexa-backend.onrender.com/"
BOT_TOKEN = "9047928965:AAFwgZzenhoygduvmfxCx-FTpoqpq0c2IF8"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    keyboard = [
        [InlineKeyboardButton("🚀 Fur CRYPTNEXA WebApp", web_app={"url": WEBAPP_URL})]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 Ku soo dhawoow CRYPTNEXA, *{user_name}*!\n\n"
        "Nidaamka maalgashiga iyo xaqiijinta tooska ah ee USDT. Riix badhanka hoose si aad u furto madasha:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("🤖 CryptNexa Bot waa uu shaqeynayaa...")
    app.run_polling()
