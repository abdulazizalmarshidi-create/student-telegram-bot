import os
import sqlite3
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# الإعدادات
# =========================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")  # ضع رقم حسابك في متغير البيئة
CONTACT_USERNAME = os.getenv("CONTACT_USERNAME", "Abdulazizfh")
DB_PATH = os.getenv("DB_PATH", "tickets.db")

# حالات إنشاء التذكرة
TICKET_TYPE, TRAINING_NUMBER, FULL_NAME, DESCRIPTION, CONFIRM = range(5)

# حالات متابعة التذكرة
TRACK_TICKET = 10

STATUS_LABELS = {
    "new": "🆕 جديدة",
    "in_progress": "🛠️ تحت الإجراء",
    "waiting_student": "⏳ بانتظار الطالب",
    "resolved": "✅ تم الحل",
    "closed": "🔒 مغلقة",
}

TICKET_TYPES = {
    "blackboard": "🖥️ مشكلة في البلاك بورد",
    "rayat": "🔐 مشكلة في رايات",
    "course": "📚 مشكلة في المقرر/المحتوى",
    "other": "📝 مشكلة أخرى",
}


# =========================
# قاعدة البيانات
# =========================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_code TEXT UNIQUE,
                telegram_user_id INTEGER NOT NULL,
                telegram_username TEXT,
                ticket_type TEXT NOT NULL,
                training_number TEXT NOT NULL,
                full_name TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_code TEXT NOT NULL,
                note TEXT NOT NULL,
                is_public INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_ticket(user_id, username, ticket_type, training_number, full_name, description):
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO tickets (
                ticket_code, telegram_user_id, telegram_username, ticket_type,
                training_number, full_name, description, status, created_at, updated_at
            )
            VALUES (NULL, ?, ?, ?, ?, ?, ?, 'new', ?, ?)
            """,
            (
                user_id,
                username or "",
                ticket_type,
                training_number,
                full_name,
                description,
                now_text(),
                now_text(),
            ),
        )
        ticket_id = cur.lastrowid
        ticket_code = f"ET-{1000 + ticket_id}"
        conn.execute(
            "UPDATE tickets SET ticket_code = ? WHERE id = ?",
            (ticket_code, ticket_id),
        )
        return ticket_code


def get_ticket(ticket_code):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM tickets WHERE UPPER(ticket_code) = UPPER(?)",
            (ticket_code.strip(),),
        ).fetchone()


def get_public_notes(ticket_code):
    with get_db() as conn:
        return conn.execute(
            """
            SELECT * FROM ticket_notes
            WHERE UPPER(ticket_code) = UPPER(?) AND is_public = 1
            ORDER BY id ASC
            """,
            (ticket_code.strip(),),
        ).fetchall()


def add_note(ticket_code, note, is_public=False):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO ticket_notes (ticket_code, note, is_public, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (ticket_code.upper(), note, 1 if is_public else 0, now_text()),
        )
        conn.execute(
            "UPDATE tickets SET updated_at = ? WHERE UPPER(ticket_code) = UPPER(?)",
            (now_text(), ticket_code),
        )


def update_status(ticket_code, status):
    with get_db() as conn:
        cur = conn.execute(
            """
            UPDATE tickets
            SET status = ?, updated_at = ?
            WHERE UPPER(ticket_code) = UPPER(?)
            """,
            (status, now_text(), ticket_code),
        )
        return cur.rowcount > 0


def latest_tickets(limit=10):
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM tickets ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()


# =========================
# أدوات مساعدة
# =========================
def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 إعادة تعيين كلمة مرور رايات", callback_data="rayat")],
        [InlineKeyboardButton("🎫 فتح تذكرة دعم", callback_data="open_ticket")],
        [InlineKeyboardButton("📋 متابعة تذكرة", callback_data="track_ticket")],
        [InlineKeyboardButton("👨‍💼 التواصل مع رئيس قسم التدرب الإلكتروني", callback_data="contact_head")],
    ])


def ticket_type_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(TICKET_TYPES["blackboard"], callback_data="type_blackboard")],
        [InlineKeyboardButton(TICKET_TYPES["rayat"], callback_data="type_rayat")],
        [InlineKeyboardButton(TICKET_TYPES["course"], callback_data="type_course")],
        [InlineKeyboardButton(TICKET_TYPES["other"], callback_data="type_other")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_ticket")],
    ])


def is_admin(user_id):
    if not ADMIN_USER_ID:
        return False
    return str(user_id) == str(ADMIN_USER_ID)


async def notify_admin(context: ContextTypes.DEFAULT_TYPE, ticket_code: str):
    if not ADMIN_USER_ID:
        return

    ticket = get_ticket(ticket_code)
    if not ticket:
        return

    text = (
        f"🎫 تذكرة جديدة: {ticket['ticket_code']}\n\n"
        f"النوع: {TICKET_TYPES.get(ticket['ticket_type'], ticket['ticket_type'])}\n"
        f"الاسم: {ticket['full_name']}\n"
        f"الرقم التدريبي: {ticket['training_number']}\n"
        f"الحالة: {STATUS_LABELS.get(ticket['status'], ticket['status'])}\n\n"
        f"الوصف:\n{ticket['description']}\n\n"
        f"للملاحظات الداخلية:\n/note {ticket['ticket_code']} الملاحظة\n\n"
        f"للرد على الطالب:\n/reply {ticket['ticket_code']} الرد\n\n"
        f"لتغيير الحالة:\n/status {ticket['ticket_code']} in_progress"
    )

    try:
        await context.bot.send_message(chat_id=int(ADMIN_USER_ID), text=text)
    except Exception:
        pass


# =========================
# القائمة الرئيسية
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 مرحباً بك في بوت التدرب الإلكتروني\n\n"
        "اختر الخدمة المطلوبة:"
    )

    if update.message:
        await update.message.reply_text(text, reply_markup=main_keyboard())
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=main_keyboard())


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def main_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "rayat":
        await query.edit_message_text(
            "🔐 إعادة تعيين كلمة مرور رايات\n\n"
            "لإعادة تعيين كلمة المرور، افتح الرابط التالي واختر (الدخول إلى الخدمة):\n\n"
            "https://tvtc.gov.sa/ar/Eservices/Pages/ResetPassword.aspx\n\n"
            "بعد الانتهاء يمكنك العودة للقائمة الرئيسية.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_home")]
            ]),
        )

    elif query.data == "contact_head":
        await query.edit_message_text(
            "👨‍💼 التواصل مع رئيس قسم التدرب الإلكتروني\n\n"
            f"يمكنك التواصل عبر تيليجرام:\n@{CONTACT_USERNAME}\n\n"
            "للمشكلات الفنية يفضّل فتح تذكرة دعم حتى يمكن متابعتها وتوثيقها.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎫 فتح تذكرة دعم", callback_data="open_ticket")],
                [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_home")],
            ]),
        )

    elif query.data == "back_home":
        await start(update, context)


# =========================
# فتح تذكرة
# =========================
async def open_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data.pop("new_ticket", None)
    context.user_data["new_ticket"] = {}

    await query.edit_message_text(
        "🎫 فتح تذكرة دعم\n\n"
        "اختر نوع المشكلة:",
        reply_markup=ticket_type_keyboard(),
    )
    return TICKET_TYPE


async def choose_ticket_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_ticket":
        context.user_data.pop("new_ticket", None)
        await query.edit_message_text(
            "تم إلغاء فتح التذكرة.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_home")]
            ]),
        )
        return ConversationHandler.END

    ticket_type = query.data.replace("type_", "")
    if ticket_type not in TICKET_TYPES:
        return TICKET_TYPE

    context.user_data["new_ticket"]["ticket_type"] = ticket_type

    await query.edit_message_text(
        f"تم اختيار: {TICKET_TYPES[ticket_type]}\n\n"
        "أرسل الآن الرقم التدريبي:"
    )
    return TRAINING_NUMBER


async def receive_training_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = update.message.text.strip()

    if len(value) < 4:
        await update.message.reply_text("الرقم التدريبي غير واضح. أرسله مرة أخرى:")
        return TRAINING_NUMBER

    context.user_data["new_ticket"]["training_number"] = value
    await update.message.reply_text("ممتاز. الآن أرسل الاسم الثلاثي:")
    return FULL_NAME


async def receive_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = update.message.text.strip()

    if len(value.split()) < 2:
        await update.message.reply_text("الاسم غير واضح. أرسل الاسم الكامل مرة أخرى:")
        return FULL_NAME

    context.user_data["new_ticket"]["full_name"] = value
    await update.message.reply_text(
        "📝 اكتب وصف المشكلة بالتفصيل.\n\n"
        "مثال: لا يظهر لي المقرر في البلاك بورد منذ صباح اليوم."
    )
    return DESCRIPTION


async def receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = update.message.text.strip()

    if len(value) < 8:
        await update.message.reply_text("اكتب وصفاً أوضح للمشكلة:")
        return DESCRIPTION

    context.user_data["new_ticket"]["description"] = value
    data = context.user_data["new_ticket"]

    summary = (
        "📋 راجع بيانات التذكرة:\n\n"
        f"النوع: {TICKET_TYPES[data['ticket_type']]}\n"
        f"الرقم التدريبي: {data['training_number']}\n"
        f"الاسم: {data['full_name']}\n\n"
        f"وصف المشكلة:\n{data['description']}\n\n"
        "هل تريد إرسال التذكرة؟"
    )

    await update.message.reply_text(
        summary,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ إرسال التذكرة", callback_data="confirm_ticket")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_ticket")],
        ]),
    )
    return CONFIRM


async def confirm_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_ticket":
        context.user_data.pop("new_ticket", None)
        await query.edit_message_text(
            "تم إلغاء التذكرة.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_home")]
            ]),
        )
        return ConversationHandler.END

    if query.data != "confirm_ticket":
        return CONFIRM

    data = context.user_data.get("new_ticket")
    if not data:
        await query.edit_message_text("انتهت الجلسة. افتح تذكرة جديدة من القائمة.")
        return ConversationHandler.END

    user = query.from_user
    ticket_code = create_ticket(
        user_id=user.id,
        username=user.username,
        ticket_type=data["ticket_type"],
        training_number=data["training_number"],
        full_name=data["full_name"],
        description=data["description"],
    )

    context.user_data.pop("new_ticket", None)

    await query.edit_message_text(
        "✅ تم إرسال التذكرة بنجاح\n\n"
        f"رقم التذكرة: {ticket_code}\n"
        "الحالة: 🆕 جديدة\n\n"
        "احتفظ برقم التذكرة لمتابعتها لاحقاً.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 متابعة التذكرة", callback_data="track_ticket")],
            [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_home")],
        ]),
    )

    await notify_admin(context, ticket_code)
    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("new_ticket", None)
    await update.message.reply_text("تم الإلغاء.", reply_markup=main_keyboard())
    return ConversationHandler.END


# =========================
# متابعة التذكرة
# =========================
async def track_ticket_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📋 متابعة تذكرة\n\n"
        "أرسل رقم التذكرة، مثال:\nET-1001"
    )
    return TRACK_TICKET


async def track_ticket_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticket_code = update.message.text.strip().upper()
    ticket = get_ticket(ticket_code)

    if not ticket:
        await update.message.reply_text(
            "❌ لم أجد تذكرة بهذا الرقم.\n"
            "تأكد من الرقم وأرسله مرة أخرى، مثال: ET-1001"
        )
        return TRACK_TICKET

    # حماية خصوصية الطالب: لا تظهر التذكرة إلا لصاحبها أو للمشرف
    if ticket["telegram_user_id"] != update.effective_user.id and not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ هذه التذكرة غير مرتبطة بحسابك.")
        return ConversationHandler.END

    notes = get_public_notes(ticket_code)
    public_updates = ""
    if notes:
        public_updates = "\n\n📨 آخر التحديثات:\n" + "\n".join(
            f"• {row['note']}" for row in notes[-5:]
        )

    text = (
        f"🎫 التذكرة: {ticket['ticket_code']}\n"
        f"الحالة: {STATUS_LABELS.get(ticket['status'], ticket['status'])}\n"
        f"النوع: {TICKET_TYPES.get(ticket['ticket_type'], ticket['ticket_type'])}\n"
        f"آخر تحديث: {ticket['updated_at']}"
        f"{public_updates}"
    )

    await update.message.reply_text(text, reply_markup=main_keyboard())
    return ConversationHandler.END


# =========================
# أوامر المشرف
# =========================
async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"رقم حساب تيليجرام الخاص بك:\n{update.effective_user.id}\n\n"
        "ضع هذا الرقم في متغير البيئة ADMIN_USER_ID في الاستضافة."
    )


async def tickets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("هذا الأمر مخصص للمشرف.")
        return

    tickets = latest_tickets(10)
    if not tickets:
        await update.message.reply_text("لا توجد تذاكر حتى الآن.")
        return

    lines = ["🎫 آخر 10 تذاكر:\n"]
    for ticket in tickets:
        lines.append(
            f"{ticket['ticket_code']} | "
            f"{STATUS_LABELS.get(ticket['status'], ticket['status'])}\n"
            f"{ticket['full_name']} - {ticket['training_number']}"
        )

    await update.message.reply_text("\n\n".join(lines))


async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("هذا الأمر مخصص للمشرف.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "الاستخدام:\n/note ET-1001 نص الملاحظة\n\n"
            "هذه الملاحظة داخلية ولن تظهر للطالب."
        )
        return

    ticket_code = context.args[0].upper()
    note = " ".join(context.args[1:]).strip()

    if not get_ticket(ticket_code):
        await update.message.reply_text("لم أجد التذكرة.")
        return

    add_note(ticket_code, note, is_public=False)
    await update.message.reply_text(
        f"✅ تمت إضافة ملاحظة داخلية على {ticket_code}.\n"
        "لن تظهر هذه الملاحظة للطالب."
    )


async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("هذا الأمر مخصص للمشرف.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "الاستخدام:\n/reply ET-1001 نص الرد"
        )
        return

    ticket_code = context.args[0].upper()
    reply_text = " ".join(context.args[1:]).strip()
    ticket = get_ticket(ticket_code)

    if not ticket:
        await update.message.reply_text("لم أجد التذكرة.")
        return

    add_note(ticket_code, reply_text, is_public=True)

    try:
        await context.bot.send_message(
            chat_id=ticket["telegram_user_id"],
            text=(
                f"📨 تحديث على التذكرة {ticket_code}\n\n"
                f"{reply_text}\n\n"
                f"الحالة الحالية: {STATUS_LABELS.get(ticket['status'], ticket['status'])}"
            ),
        )
        await update.message.reply_text(f"✅ تم إرسال الرد للطالب على {ticket_code}.")
    except Exception:
        await update.message.reply_text(
            "تم حفظ الرد في التذكرة، لكن تعذر إرساله مباشرة للطالب."
        )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("هذا الأمر مخصص للمشرف.")
        return

    if len(context.args) != 2:
        await update.message.reply_text(
            "الاستخدام:\n/status ET-1001 in_progress\n\n"
            "الحالات المتاحة:\n"
            "new\nin_progress\nwaiting_student\nresolved\nclosed"
        )
        return

    ticket_code = context.args[0].upper()
    new_status = context.args[1].lower()

    if new_status not in STATUS_LABELS:
        await update.message.reply_text("الحالة غير صحيحة.")
        return

    ticket = get_ticket(ticket_code)
    if not ticket:
        await update.message.reply_text("لم أجد التذكرة.")
        return

    update_status(ticket_code, new_status)
    ticket = get_ticket(ticket_code)

    try:
        await context.bot.send_message(
            chat_id=ticket["telegram_user_id"],
            text=(
                f"🔔 تم تحديث حالة التذكرة {ticket_code}\n\n"
                f"الحالة الجديدة: {STATUS_LABELS[new_status]}"
            ),
        )
    except Exception:
        pass

    await update.message.reply_text(
        f"✅ تم تحديث {ticket_code} إلى: {STATUS_LABELS[new_status]}"
    )


async def ticket_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("هذا الأمر مخصص للمشرف.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("الاستخدام:\n/ticket ET-1001")
        return

    ticket_code = context.args[0].upper()
    ticket = get_ticket(ticket_code)
    if not ticket:
        await update.message.reply_text("لم أجد التذكرة.")
        return

    with get_db() as conn:
        notes = conn.execute(
            """
            SELECT * FROM ticket_notes
            WHERE UPPER(ticket_code) = UPPER(?)
            ORDER BY id ASC
            """,
            (ticket_code,),
        ).fetchall()

    notes_text = ""
    if notes:
        notes_text = "\n\n🗒️ الملاحظات والتحديثات:\n" + "\n".join(
            f"• {'للطالب' if n['is_public'] else 'داخلي'}: {n['note']}"
            for n in notes
        )

    text = (
        f"🎫 {ticket['ticket_code']}\n"
        f"الحالة: {STATUS_LABELS.get(ticket['status'], ticket['status'])}\n"
        f"النوع: {TICKET_TYPES.get(ticket['ticket_type'], ticket['ticket_type'])}\n"
        f"الاسم: {ticket['full_name']}\n"
        f"الرقم التدريبي: {ticket['training_number']}\n"
        f"Telegram ID: {ticket['telegram_user_id']}\n\n"
        f"الوصف:\n{ticket['description']}"
        f"{notes_text}"
    )

    await update.message.reply_text(text)


# =========================
# تشغيل البوت
# =========================
def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN غير موجود في متغيرات البيئة.")

    init_db()

    app = Application.builder().token(TOKEN).build()

    ticket_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(open_ticket, pattern="^open_ticket$")],
        states={
            TICKET_TYPE: [
                CallbackQueryHandler(
                    choose_ticket_type,
                    pattern="^(type_blackboard|type_rayat|type_course|type_other|cancel_ticket)$",
                )
            ],
            TRAINING_NUMBER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_training_number)
            ],
            FULL_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_full_name)
            ],
            DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_description)
            ],
            CONFIRM: [
                CallbackQueryHandler(
                    confirm_ticket,
                    pattern="^(confirm_ticket|cancel_ticket)$",
                )
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        allow_reentry=True,
    )

    track_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(track_ticket_start, pattern="^track_ticket$")],
        states={
            TRACK_TICKET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, track_ticket_receive)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("myid", myid))

    # أوامر المشرف
    app.add_handler(CommandHandler("tickets", tickets_command))
    app.add_handler(CommandHandler("ticket", ticket_command))
    app.add_handler(CommandHandler("note", note_command))
    app.add_handler(CommandHandler("reply", reply_command))
    app.add_handler(CommandHandler("status", status_command))

    # المحادثات
    app.add_handler(ticket_conversation)
    app.add_handler(track_conversation)

    # الأزرار العامة
    app.add_handler(
        CallbackQueryHandler(
            main_buttons,
            pattern="^(rayat|contact_head|back_home)$",
        )
    )

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
