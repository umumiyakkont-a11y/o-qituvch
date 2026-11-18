import asyncio
import logging
import os
import sqlite3
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Message,
)

# Render'da Environment Variables orqali o'qiladi
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8371392099"))

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# --- BAZA BILAN ISHLASH ---
def init_db():
    conn = sqlite3.connect("kitobxon.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            fullname TEXT,
            phone TEXT,
            school TEXT,
            grade TEXT,
            registered INTEGER DEFAULT 0
        )
    """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS channels (
            channel_username TEXT PRIMARY KEY,
            channel_title TEXT
        )
    """
    )
    conn.commit()
    conn.close()

init_db()

# --- FSM (STATE) HOLATLAR ---
class RegState(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_school = State()
    waiting_for_grade = State()

class EditState(StatesGroup):
    edit_choice = State()
    new_value = State()

class BroadcastState(StatesGroup):
    waiting_for_text = State()

class ChannelState(StatesGroup):
    waiting_for_channel = State()

class DeleteUserState(StatesGroup):
    waiting_for_id = State()

# --- YORDAMCHI FUNKSIYALAR ---
def get_user(user_id):
    conn = sqlite3.connect("kitobxon.db")
    cursor = conn.cursor()
    cursor.execute("SELECT fullname, phone, school, grade, registered FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res

async def check_subscriptions(user_id: int) -> list:
    conn = sqlite3.connect("kitobxon.db")
    cursor = conn.cursor()
    cursor.execute("SELECT channel_username FROM channels")
    channels = cursor.fetchall()
    conn.close()

    unsubscribed = []
    for (ch,) in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch, user_id=user_id)
            if member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.KICKED]:
                unsubscribed.append(ch)
        except Exception:
            unsubscribed.append(ch)
    return unsubscribed

def sub_keyboard(channels):
    keyboard = []
    for ch in channels:
        keyboard.append([InlineKeyboardButton(text=f"📢 {ch} ga obuna bo'lish", url=f"https://t.me/{ch.lstrip('@')}")])
    keyboard.append([InlineKeyboardButton(text="✅ A'zo bo'ldim", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

admin_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📢 E'lon yuborish")],
        [KeyboardButton(text="📋 Ishtirokchilar ro'yxati")],
        [KeyboardButton(text="❌ Ro'yxatdan o'chirish")],
        [KeyboardButton(text="➕ Majburiy obuna kanali")],
    ],
    resize_keyboard=True
)

# --- /START VA MAJBURIY OBUNA ---
@router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if user_id == ADMIN_ID:
        await message.answer("👑 Admin paneliga xush kelibsiz:", reply_markup=admin_keyboard)
        return

    unsub = await check_subscriptions(user_id)
    if unsub:
        await message.answer(
            "⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'lishingiz kerak:",
            reply_markup=sub_keyboard(unsub),
        )
        return

    user = get_user(user_id)
    if user and user[4] == 1:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="✏️ Ma'lumotlarni tahrirlash", callback_data="edit_info")]]
        )
        await message.answer(
            f"Assalomu alaykum, {user[0]}! Siz allaqachon ro'yxatdan o'tgansiz.",
            reply_markup=kb,
        )
    else:
        await state.set_state(RegState.waiting_for_name)
        await message.answer("Kitobxonlik tanloviga xush kelibsiz! \n\nIltimos, **Ism va Familiyangizni** kiriting:", reply_markup=ReplyKeyboardRemove())

@router.callback_query(F.data == "check_sub")
async def verify_subscription(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    unsub = await check_subscriptions(user_id)
    if unsub:
        await callback.answer("Hali hamma kanallarga obuna bo'lmadingiz!", show_alert=True)
    else:
        await callback.message.delete()
        await cmd_start(callback.message, state)

# --- RO'YXATDAN O'TISH ---
@router.message(RegState.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(fullname=message.text)
    await state.set_state(RegState.waiting_for_phone)
    await message.answer("Telefon raqamingizni kiriting (Faqat raqamlar, masalan: 998901234567):")

@router.message(RegState.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not phone.replace("+", "").isdigit():
        await message.answer("❌ Xato! Telefon raqam faqat raqamlardan iborat bo'lishi kerak. Qaytadan kiriting:")
        return
    await state.update_data(phone=phone)
    await state.set_state(RegState.waiting_for_school)
    await message.answer("Qaysi maktabda o'qiysiz? (Faqat maktab raqamini kiriting, masalan: 14):")

@router.message(RegState.waiting_for_school)
async def process_school(message: Message, state: FSMContext):
    school = message.text.strip()
    if not school.isdigit():
        await message.answer("❌ Xato! Maktab raqamini faqat sonlarda kiriting (masalan: 14):")
        return
    await state.update_data(school=school)
    await state.set_state(RegState.waiting_for_grade)
    await message.answer("Nechanchi sinfda o'qiysiz? (Faqat sinf raqamini kiriting, masalan: 8):")

@router.message(RegState.waiting_for_grade)
async def process_grade(message: Message, state: FSMContext):
    grade = message.text.strip()
    if not grade.isdigit():
        await message.answer("❌ Xato! Sinf raqamini faqat sonlarda kiriting (masalan: 8):")
        return

    data = await state.get_data()
    user_id = message.from_user.id

    conn = sqlite3.connect("kitobxon.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO users (user_id, fullname, phone, school, grade, registered)
        VALUES (?, ?, ?, ?, ?, 1)
    """,
        (user_id, data["fullname"], data["phone"], data["school"], grade),
    )
    conn.commit()
    conn.close()

    await state.clear()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✏️ Ma'lumotlarni tahrirlash", callback_data="edit_info")]]
    )
    await message.answer("✅ Tabriklaymiz! Siz tanlovga muvaffaqiyatli ro'yxatdan o'tdingiz.", reply_markup=kb)

# --- TAHRIRLASH ---
@router.callback_query(F.data == "edit_info")
async def edit_menu(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ism va Familiya", callback_data="edit_fullname")],
            [InlineKeyboardButton(text="Telefon raqam", callback_data="edit_phone")],
            [InlineKeyboardButton(text="Maktab", callback_data="edit_school")],
            [InlineKeyboardButton(text="Sinf", callback_data="edit_grade")],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_home")],
        ]
    )
    await callback.message.edit_text("Nimani tahrirlamoqchisiz?", reply_markup=kb)

@router.callback_query(F.data.startswith("edit_"))
async def edit_field_start(callback: CallbackQuery, state: FSMContext):
    if callback.data == "back_home":
        user = get_user(callback.from_user.id)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="✏️ Ma'lumotlarni tahrirlash", callback_data="edit_info")]]
        )
        await callback.message.edit_text(f"Ism: {user[0]}\nTel: {user[1]}\nMaktab: {user[2]}\nSinf: {user[3]}", reply_markup=kb)
        return

    field = callback.data.split("_")[1]
    await state.update_data(field_to_edit=field)
    await state.set_state(EditState.new_value)
    await callback.message.answer(f"Yangi {field}ni kiriting:")

@router.message(EditState.new_value)
async def save_new_value(message: Message, state: FSMContext):
    data = await state.get_data()
    field = data["field_to_edit"]
    user_id = message.from_user.id
    val = message.text.strip()

    if field == "phone" and not val.replace("+", "").isdigit():
        await message.answer("❌ Xato! Telefon raqam faqat raqamlardan iborat bo'lsin:")
        return
    elif field in ["school", "grade"] and not val.isdigit():
        await message.answer("❌ Xato! Bu maydon faqat sonlardan iborat bo'lsin:")
        return

    mapping = {"fullname": "fullname", "phone": "phone", "school": "school", "grade": "grade"}
    db_field = mapping.get(field)

    conn = sqlite3.connect("kitobxon.db")
    cursor = conn.cursor()
    cursor.execute(f"UPDATE users SET {db_field} = ? WHERE user_id = ?", (val, user_id))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer("✅ Ma'lumotlaringiz yangilandi! /start ni bosing.")

# --- ADMIN PANEL ---
@router.message(F.text == "/admin")
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("👑 Admin paneliga xush kelibsiz:", reply_markup=admin_keyboard)

@router.message(F.text == "📢 E'lon yuborish")
async def adm_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(BroadcastState.waiting_for_text)
    await message.answer("Yuboriladigan xabar matnini kiriting:", reply_markup=ReplyKeyboardRemove())

@router.message(BroadcastState.waiting_for_text)
async def send_broadcast(message: Message, state: FSMContext):
    await state.clear()
    conn = sqlite3.connect("kitobxon.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE registered = 1")
    users = cursor.fetchall()
    conn.close()

    count = 0
    for (uid,) in users:
        try:
            await bot.send_message(uid, message.text)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await message.answer(f"✅ E'lon {count} ta foydalanuvchiga yuborildi!", reply_markup=admin_keyboard)

@router.message(F.text == "📋 Ishtirokchilar ro'yxati")
async def adm_list(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("kitobxon.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, fullname, phone, school, grade FROM users WHERE registered = 1")
    users = cursor.fetchall()
    conn.close()

    if not users:
        await message.answer("Hozircha ro'yxatdan o'tganlar yo'q.", reply_markup=admin_keyboard)
        return

    text = "📋 **Ishtirokchilar ro'yxati:**\n\n"
    for i, u in enumerate(users, 1):
        text += f"{i}. 🆔 ID: `{u[0]}`\n   👤 **{u[1]}**\n   📞 Tel: {u[2]}\n   🏫 Maktab: {u[3]}, Sinf: {u[4]}\n\n"
        if len(text) > 3500:
            await message.answer(text, parse_mode="Markdown")
            text = ""
    if text:
        await message.answer(text, parse_mode="Markdown", reply_markup=admin_keyboard)

@router.message(F.text == "❌ Ro'yxatdan o'chirish")
async def adm_delete(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(DeleteUserState.waiting_for_id)
    await message.answer("O'chirilishi kerak bo'lgan foydalanuvchi **Telegram ID** raqamini kiriting:", reply_markup=ReplyKeyboardRemove())

@router.message(DeleteUserState.waiting_for_id)
async def process_delete_user(message: Message, state: FSMContext):
    await state.clear()
    try:
        target_id = int(message.text.strip())
        conn = sqlite3.connect("kitobxon.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE user_id = ?", (target_id,))
        conn.commit()
        conn.close()
        
        try:
            await bot.send_message(target_id, "⚠️ Siz admin tomonidan tanlov ro'yxatidan o'chirildingiz.")
        except Exception:
            pass

        await message.answer(f"✅ ID {target_id} o'chirildi.", reply_markup=admin_keyboard)
    except ValueError:
        await message.answer("❌ Noto'g'ri ID.", reply_markup=admin_keyboard)

@router.message(F.text == "➕ Majburiy obuna kanali")
async def adm_channel(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("kitobxon.db")
    cursor = conn.cursor()
    cursor.execute("SELECT channel_username FROM channels")
    channels = cursor.fetchall()
    conn.close()

    ch_list = "\n".join([c[0] for c in channels]) if channels else "Hozircha kanallar yo'q."
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_ch")],
            [InlineKeyboardButton(text="🗑 Kanalni o'chirish", callback_data="del_ch")],
        ]
    )
    await message.answer(f"📢 Hozirgi kanallar:\n{ch_list}", reply_markup=kb)

@router.callback_query(F.data == "add_ch")
async def add_channel_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ChannelState.waiting_for_channel)
    await callback.message.answer("Kanal username'ini yuboring (masalan: `@kanal_nomi`):")

@router.callback_query(F.data == "del_ch")
async def delete_channel_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ChannelState.waiting_for_channel)
    await callback.message.answer("O'chirmoqchi bo'lgan kanal username'ini yuboring:")

@router.message(ChannelState.waiting_for_channel)
async def save_or_remove_channel(message: Message, state: FSMContext):
    ch = message.text.strip()
    conn = sqlite3.connect("kitobxon.db")
    cursor = conn.cursor()
    # Tekshiramiz: bu kanal bazada bormi yoki yo'q, shunga qarab qo'shamiz yoki o'chiramiz
    cursor.execute("SELECT channel_username FROM channels WHERE channel_username = ?", (ch,))
    exists = cursor.fetchone()
    
    if exists:
        cursor.execute("DELETE FROM channels WHERE channel_username = ?", (ch,))
        conn.commit()
        msg = f"🗑 {ch} majburiy obunadan olib tashlandi."
    else:
        cursor.execute("INSERT OR IGNORE INTO channels (channel_username) VALUES (?)", (ch,))
        conn.commit()
        msg = f"✅ {ch} majburiy obunaga qo'shildi!"
    conn.close()
    
    await state.clear()
    await message.answer(msg, reply_markup=admin_keyboard)


# --- RENDER WEB SERVICE UCHUN AIOHTTP SERVER ---
async def handle(request):
    return web.Response(text="Bot is running!")

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    # Veb-serverni hamda bot pollingni bir vaqtda ishga tushiramiz
    await web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
