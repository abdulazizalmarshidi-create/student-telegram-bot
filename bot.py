import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN =  os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔐 كلمة مرور رايات", callback_data="rayat")],
        [InlineKeyboardButton("🖥️ الدعم الفني للبلاك بورد", callback_data="blackboard")]
    ]

    await update.message.reply_text(
        "👋 مرحباً بك في بوت التدرب الإلكتروني\n\nاختر الخدمة المطلوبة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
)
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "rayat":
        await query.edit_message_text(
            "🔐 كلمة المرور لنظام رايات\n\n"
            "لإعادة تعيينها، افتح الرابط التالي واختر (الدخول إلى الخدمة):\n\n"
            "https://tvtc.gov.sa/ar/Eservices/Pages/ResetPassword.aspx"
        )

    elif query.data == "blackboard":
        await query.edit_message_text(
            "🖥️ الدعم الفني للبلاك بورد\n\n"
            "✅ يمكنك الآن التحدث مباشرة مع مسؤول الدعم من خلال @Abdulazizfh\n\n"
            "يرجى كتابة وصف مشكلتك كاملاً مع الرقم التدريبي والاسم الثلاثي."
        )
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()