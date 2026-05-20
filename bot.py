import asyncio
import aiosqlite
from datetime import datetime, timedelta, date

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    WebAppInfo,
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton,
    FSInputFile
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from apscheduler.schedulers.asyncio import AsyncIOScheduler


# ================= CONFIG =================

TOKEN    = "8840864571:AAFacYXDGqSJ352sRmJn2vHlRnHf28n8JjI"
ADMIN_ID = 6137921070
PRICE_PER_HOUR     = 10_000   # so'm
FSM_TIMEOUT_MINUTES = 10      # daqiqa

DB_PATH = "booking.db"
WEBAPP_URL = "https://YOUR_GITHUB_USERNAME.github.io/cyber-arena/menu.html"  # <-- o'zgartiring

bot       = Bot(token=TOKEN)
dp        = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()


# ================= DATABASE =================

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER,
                full_name     TEXT,
                username      TEXT,
                phone         TEXT,
                computer      TEXT,
                day           TEXT,
                time          TEXT,
                status        TEXT DEFAULT 'pending',
                reminder_sent INTEGER DEFAULT 0,
                created_at    TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER PRIMARY KEY
            )
        """)
        # Migration: eski DB da yo'q ustunlarni qo'shish
        existing = [row[1] async for row in await db.execute("PRAGMA table_info(bookings)")]
        if "reminder_sent" not in existing:
            await db.execute("ALTER TABLE bookings ADD COLUMN reminder_sent INTEGER DEFAULT 0")
        if "created_at" not in existing:
            await db.execute("ALTER TABLE bookings ADD COLUMN created_at TEXT DEFAULT (datetime('now'))")
        if "rating_sent" not in existing:
            await db.execute("ALTER TABLE bookings ADD COLUMN rating_sent INTEGER DEFAULT 0")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER,
                user_id    INTEGER,
                score      INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.commit()


# ================= HELPERS =================

async def is_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM banned_users WHERE user_id=?", (user_id,)
        ) as cur:
            return await cur.fetchone() is not None


def get_week_days():
    uz_days = ["Dushanba","Seshanba","Chorshanba","Payshanba","Juma","Shanba","Yakshanba"]
    result  = []
    today   = date.today()
    for i in range(7):
        d = today + timedelta(days=i)
        if   i == 0: label = f"Bugun ({d.strftime('%d.%m')})"
        elif i == 1: label = f"Ertaga ({d.strftime('%d.%m')})"
        else:        label = f"{uz_days[d.weekday()]} ({d.strftime('%d.%m')})"
        result.append((d.strftime("%Y-%m-%d"), label))
    return result


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Bron qilish",  callback_data="booking")],
        [InlineKeyboardButton(text="📅 Bronlarim",    callback_data="my_bookings")],
        [InlineKeyboardButton(text="🏆 Top Players",  callback_data="top_players")],
    ])


STATUS_EMOJI = {"pending": "🕓", "accepted": "✅", "rejected": "❌"}

def admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Barcha bronlar",   callback_data="bookings")],
        [InlineKeyboardButton(text="🕓 Pending bronlar",  callback_data="pending_bookings")],
        [InlineKeyboardButton(text="📊 Statistika",       callback_data="stats")],
        [InlineKeyboardButton(text="📅 Schedule (bugun)", callback_data="schedule")],
    ])




# ================= STATES =================

class Booking(StatesGroup):
    pc    = State()
    day   = State()
    time  = State()
    phone = State()

class Broadcast(StatesGroup):
    text = State()


# ================= FSM TIMEOUT =================

async def check_fsm_timeout(state: FSMContext, obj) -> bool:
    data = await state.get_data()
    started_at_str = data.get("started_at")
    if not started_at_str:
        return False
    started_at = datetime.fromisoformat(started_at_str)
    if (datetime.now() - started_at).seconds > FSM_TIMEOUT_MINUTES * 60:
        await state.clear()
        target = obj.message if isinstance(obj, CallbackQuery) else obj
        await target.answer("⏰ Vaqt tugadi! Qaytadan boshlang.", reply_markup=main_menu_kb())
        return True
    return False


# ================= /start =================

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    if await is_banned(message.from_user.id):
        await message.answer("⛔ Siz bloklangansiz!")
        return
    text = (
        "🎮 <b>CYBER ARENA</b>\n\n"
        "🔥 Premium Gaming Zone\n"
        "🖥 RTX Gaming PCs\n"
        f"💰 Narx: {PRICE_PER_HOUR:,} so'm/soat\n"
        "⚡ 24/7 Booking System\n"
        "☕ Chill Zone\n\n"
        "👇 Bron qilish uchun tugmani bosing"
    )
    photo = FSInputFile("banner.jpg")
    await bot.send_photo(
        chat_id=message.chat.id,
        photo=photo,
        caption=text,
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )


# ================= ADMIN PANEL =================

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Barcha bronlar",   callback_data="bookings")],
        [InlineKeyboardButton(text="🕓 Pending bronlar",  callback_data="pending_bookings")],
        [InlineKeyboardButton(text="📊 Statistika",       callback_data="stats")],
        [InlineKeyboardButton(text="📅 Schedule (bugun)", callback_data="schedule")],
    ])
    await message.answer("👑 Admin panel — boshqaruv markazi", reply_markup=kb)


# ================= BROADCAST =================

@dp.message(Command("broadcast"))
async def broadcast_cmd(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        await do_broadcast(message, parts[1])
    else:
        await message.answer("📢 Yubormoqchi bo'lgan xabaringizni yozing:")
        await state.set_state(Broadcast.text)

@dp.message(Broadcast.text)
async def broadcast_text(message: Message, state: FSMContext):
    await state.clear()
    await do_broadcast(message, message.text)

async def do_broadcast(message: Message, text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT DISTINCT user_id FROM bookings") as cur:
            rows = await cur.fetchall()
    sent = failed = 0
    for (user_id,) in rows:
        try:
            await bot.send_message(user_id, f"📢 <b>E'lon</b>\n\n{text}", parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    await message.answer(f"✅ Yuborildi: {sent} ta\n❌ Xato: {failed} ta")


# ================= CLEAR BOOKINGS =================

@dp.message(Command("clear"))
async def clear_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Barcha bronlarni o'chirish",    callback_data="clear_all")],
        [InlineKeyboardButton(text="🕓 Faqat pending'larni o'chirish", callback_data="clear_pending")],
        [InlineKeyboardButton(text="❌ Bekor",                         callback_data="cancel_clear")],
    ])
    await message.answer("⚠️ Qaysi bronlarni o'chirmoqchisiz?", reply_markup=kb)

@dp.callback_query(F.data == "clear_all")
async def clear_all(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM bookings") as cur:
            (count,) = await cur.fetchone()
        await db.execute("DELETE FROM bookings")
        await db.commit()
    await callback.message.edit_text(f"✅ {count} ta bron o'chirildi!")
    await callback.answer()

@dp.callback_query(F.data == "clear_pending")
async def clear_pending(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM bookings WHERE status='pending'") as cur:
            (count,) = await cur.fetchone()
        await db.execute("DELETE FROM bookings WHERE status='pending'")
        await db.commit()
    await callback.message.edit_text(f"✅ {count} ta pending bron o'chirildi!")
    await callback.answer()

@dp.callback_query(F.data == "cancel_clear")
async def cancel_clear(callback: CallbackQuery):
    await callback.message.edit_text("❌ Bekor qilindi")
    await callback.answer()


# ================= DEL BOOKING (ADMIN) =================
# Ishlatish: /del 5        → ID bo'yicha o'chirish
#            /del PC3      → PC nomi bo'yicha barcha bronlarni o'chirish
#            /del          → so'nggi 10 bronni ID bilan ko'rsatadi

@dp.message(Command("del"))
async def del_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    args = message.text.split(maxsplit=1)

    # Argument yo'q — so'nggi 10 bronni ko'rsat
    if len(args) < 2:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM bookings ORDER BY id DESC LIMIT 10"
            ) as cur:
                rows = await cur.fetchall()
        if not rows:
            await message.answer("📭 Hali hech qanday bron yo'q")
            return
        emoji_map = {"pending": "🕓", "accepted": "✅", "rejected": "❌"}
        text = "📋 <b>So'nggi bronlar:</b>\n\n"
        for r in rows:
            e = emoji_map.get(r["status"], "❓")
            text += f"<code>/del {r['id']}</code> | {e} {r['computer']} | {r['day']} {r['time']} | {r['full_name']}\n"
        text += "\n<i>O'chirish uchun ID ni bosing yoki yozing</i>"
        await message.answer(text, parse_mode="HTML")
        return

    arg = args[1].strip()

    # PC nomi bo'yicha (masalan: PC3)
    if arg.upper().startswith("PC"):
        pc = arg.upper()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM bookings WHERE computer=?", (pc,)
            ) as cur:
                (count,) = await cur.fetchone()
            if count == 0:
                await message.answer(f"❌ {pc} uchun bronlar topilmadi")
                return
            await db.execute("DELETE FROM bookings WHERE computer=?", (pc,))
            await db.commit()
        await message.answer(f"✅ {pc} uchun {count} ta bron o'chirildi!")
        return

    # ID bo'yicha
    if not arg.isdigit():
        await message.answer("❌ Noto'g'ri format!\n\nMisol:\n/del 5 — ID bo'yicha\n/del PC3 — PC bo'yicha\n/del — ro'yxatni ko'rish")
        return

    booking_id = int(arg)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM bookings WHERE id=?", (booking_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            await message.answer(f"❌ #{booking_id} bron topilmadi")
            return
        await db.execute("DELETE FROM bookings WHERE id=?", (booking_id,))
        await db.commit()

    # Foydalanuvchiga xabar
    try:
        await bot.send_message(
            row["user_id"],
            f"🗑 Sizning broningiz admin tomonidan o'chirildi.\n\n"
            f"💻 {row['computer']}\n📅 {row['day']}\n⏰ {row['time']}"
        )
    except Exception:
        pass

    await message.answer(
        f"✅ #{booking_id} bron o'chirildi!\n\n"
        f"👤 {row['full_name']}\n"
        f"💻 {row['computer']}\n"
        f"📅 {row['day']}\n"
        f"⏰ {row['time']}"
    )


# ================= BOOKING — PC =================

@dp.callback_query(F.data == "booking")
async def booking(callback: CallbackQuery, state: FSMContext):
    if await is_banned(callback.from_user.id):
        await callback.answer("⛔ Siz bloklangansiz!", show_alert=True)
        return
    await state.update_data(started_at=datetime.now().isoformat())
    pcs = []
    async with aiosqlite.connect(DB_PATH) as db:
        for i in range(1, 31):
            pc = f"PC{i}"
            async with db.execute(
                "SELECT 1 FROM bookings WHERE computer=? AND status='accepted'", (pc,)
            ) as cur:
                row = await cur.fetchone()
            if row:
                pcs.append([InlineKeyboardButton(text=f"🔴 {pc} | BAND",  callback_data="busy")])
            else:
                pcs.append([InlineKeyboardButton(text=f"🟢 {pc} | BO'SH", callback_data=f"pc_{pc}")])
    await callback.message.answer(
        "💻 Kompyuter tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=pcs)
    )
    await state.set_state(Booking.pc)
    await callback.answer()

@dp.callback_query(F.data == "busy")
async def busy(callback: CallbackQuery):
    await callback.answer("⛔ Bu kompyuter band! Boshqa birini tanlang.", show_alert=True)


# ================= BOOKING — KUN =================

@dp.callback_query(Booking.pc)
async def pc_selected(callback: CallbackQuery, state: FSMContext):
    if await check_fsm_timeout(state, callback):
        return
    pc = callback.data.split("_")[1]
    await state.update_data(pc=pc)
    days = get_week_days()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"day_{value}")]
        for value, label in days
    ])
    await callback.message.answer(
        f"✅ <b>{pc}</b> tanlandi\n"
        f"💰 Narx: {PRICE_PER_HOUR:,} so'm/soat\n\n"
        "📅 Sanani tanlang:",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await state.set_state(Booking.day)
    await callback.answer()


# ================= BOOKING — VAQT =================

@dp.callback_query(Booking.day)
async def day_selected(callback: CallbackQuery, state: FSMContext):
    if await check_fsm_timeout(state, callback):
        return
    day = callback.data.replace("day_", "")
    await state.update_data(day=day)
    data = await state.get_data()
    pc   = data["pc"]
    time_buttons = []
    async with aiosqlite.connect(DB_PATH) as db:
        for h in range(8, 24):
            t = f"{h:02d}:00"
            async with db.execute("""
                SELECT 1 FROM bookings
                WHERE computer=? AND day=? AND time=?
                  AND status IN ('accepted','pending')
            """, (pc, day, t)) as cur:
                row = await cur.fetchone()
            if row:
                time_buttons.append([InlineKeyboardButton(text=f"🔴 {t} | BAND", callback_data="time_busy")])
            else:
                time_buttons.append([InlineKeyboardButton(text=f"🟢 {t}", callback_data=f"time_{t}")])
    await callback.message.answer(
        "⏰ Vaqt tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=time_buttons)
    )
    await state.set_state(Booking.time)
    await callback.answer()

@dp.callback_query(F.data == "time_busy")
async def time_busy(callback: CallbackQuery):
    await callback.answer("⛔ Bu vaqt band! Iltimos boshqa vaqt tanlang.", show_alert=True)


# ================= BOOKING — TELEFON =================

@dp.callback_query(Booking.time)
async def time_selected(callback: CallbackQuery, state: FSMContext):
    if await check_fsm_timeout(state, callback):
        return
    chosen_time = callback.data.replace("time_", "")
    data = await state.get_data()
    pc, day = data["pc"], data["day"]
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT 1 FROM bookings
            WHERE computer=? AND day=? AND time=?
              AND status IN ('accepted','pending')
        """, (pc, day, chosen_time)) as cur:
            conflict = await cur.fetchone()
    if conflict:
        await callback.answer("⛔ Siz tanlagan vaqt hozir band bo'lib qoldi! Boshqa vaqt tanlang.", show_alert=True)
        return
    await state.update_data(time=chosen_time)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await callback.message.answer(
        f"✅ Tanlangan:\n\n"
        f"💻 {pc}\n"
        f"📅 {day}\n"
        f"⏰ {chosen_time}\n"
        f"💰 Narx: {PRICE_PER_HOUR:,} so'm\n\n"
        "📱 Telefon raqamingizni yuboring:",
        reply_markup=kb
    )
    await state.set_state(Booking.phone)
    await callback.answer()


# ================= BOOKING — SAQLASH =================

@dp.message(Booking.phone)
async def save(message: Message, state: FSMContext):
    if await check_fsm_timeout(state, message):
        return
    data     = await state.get_data()
    phone    = message.contact.phone_number if message.contact else message.text
    username = f"@{message.from_user.username}" if message.from_user.username else "yo'q"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO bookings
                (user_id, full_name, username, phone, computer, day, time, status)
            VALUES (?,?,?,?,?,?,?,'pending')
        """, (
            message.from_user.id, message.from_user.full_name,
            username, phone, data["pc"], data["day"], data["time"]
        ))
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cur:
            (booking_id,) = await cur.fetchone()
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Accept", callback_data=f"accept_{message.from_user.id}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_{message.from_user.id}"),
        ],
        [InlineKeyboardButton(text="🗑 Delete", callback_data=f"delete_{message.from_user.id}")],
        [InlineKeyboardButton(text="🚫 Ban",    callback_data=f"ban_{message.from_user.id}")],
    ])
    await bot.send_message(
        ADMIN_ID,
        f"📥 Yangi bron! (#{booking_id})\n\n"
        f"👤 {message.from_user.full_name}\n"
        f"🔗 {username}\n"
        f"🆔 <code>{message.from_user.id}</code>\n"
        f"📱 {phone}\n"
        f"💻 {data['pc']}\n"
        f"📅 {data['day']}\n"
        f"⏰ {data['time']}\n"
        f"💰 {PRICE_PER_HOUR:,} so'm\n\n"
        f"🔓 Unban: <code>/unban {message.from_user.id}</code>",
        reply_markup=admin_kb,
        parse_mode="HTML"
    )
    await message.answer("✅ Bron yuborildi! Admin tasdiqlashini kuting.", reply_markup=ReplyKeyboardRemove())
    await state.clear()
    await message.answer("🏠 <b>Bosh menu</b>", reply_markup=main_menu_kb(), parse_mode="HTML")


# ================= MY BOOKINGS + BEKOR QILISH =================

@dp.callback_query(F.data == "my_bookings")
async def my_bookings(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM bookings WHERE user_id=? ORDER BY id DESC",
            (callback.from_user.id,)
        ) as cur:
            rows = await cur.fetchall()
    if not rows:
        await callback.message.answer("📭 Sizda hali hech qanday bron yo'q")
        await callback.answer()
        return
    for r in rows:
        emoji = STATUS_EMOJI.get(r["status"], "❓")
        text  = f"💻 {r['computer']}\n📅 {r['day']}\n⏰ {r['time']}\n📌 {emoji} {r['status']}"
        if r["status"] == "pending":
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🚫 Bekor qilish", callback_data=f"cancel_booking_{r['id']}")
            ]])
            await callback.message.answer(text, reply_markup=kb)
        else:
            await callback.message.answer(text)
    await callback.answer()

@dp.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking_user(callback: CallbackQuery):
    booking_id = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM bookings WHERE id=? AND user_id=? AND status='pending'",
            (booking_id, callback.from_user.id)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            await callback.answer("❌ Bron topilmadi yoki u allaqachon bekor qilingan!", show_alert=True)
            return
        await db.execute("DELETE FROM bookings WHERE id=?", (booking_id,))
        await db.commit()
    await callback.message.edit_text(
        f"✅ Bron bekor qilindi!\n💻 {row['computer']}\n📅 {row['day']}\n⏰ {row['time']}"
    )
    await bot.send_message(
        ADMIN_ID,
        f"🚫 Foydalanuvchi bronni bekor qildi!\n"
        f"👤 {callback.from_user.full_name}\n"
        f"💻 {row['computer']}\n📅 {row['day']}\n⏰ {row['time']}"
    )
    await callback.answer()


# ================= REMINDER =================

async def check_reminders():
    target   = datetime.now() + timedelta(minutes=30)
    day_str  = target.strftime("%Y-%m-%d")
    time_str = target.strftime("%H:00")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM bookings
            WHERE day=? AND time=? AND status='accepted' AND reminder_sent=0
        """, (day_str, time_str)) as cur:
            rows = await cur.fetchall()
        for row in rows:
            try:
                await bot.send_message(
                    row["user_id"],
                    f"⏰ <b>Eslatma!</b>\n\n"
                    f"Sizning broningiz <b>30 daqiqadan so'ng</b> boshlanadi!\n\n"
                    f"💻 {row['computer']}\n📅 {row['day']}\n⏰ {row['time']}\n\nTayyor bo'ling! 🎮",
                    parse_mode="HTML"
                )
                await db.execute("UPDATE bookings SET reminder_sent=1 WHERE id=?", (row["id"],))
                await db.commit()
            except Exception as e:
                print(f"Reminder xato: {e}")


# ================= ACCEPT / REJECT / DELETE / BAN =================

@dp.callback_query(F.data.startswith("accept_"))
async def accept(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    user_id = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE bookings SET status='accepted' WHERE user_id=? AND status='pending'", (user_id,)
        )
        await db.commit()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM bookings WHERE user_id=? AND status='accepted' ORDER BY id DESC LIMIT 1",
            (user_id,)
        ) as cur:
            booking = await cur.fetchone()

    booking_info = ""
    if booking:
        booking_info = f"\n💻 {booking['computer']} | 📅 {booking['day']} | ⏰ {booking['time']}"

    menu_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🍔 Menyu — Zakaz berish", web_app=WebAppInfo(url=WEBAPP_URL))]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await bot.send_message(
        user_id,
        f"✅ Bron tasdiqlandi!{booking_info}\n\n"
        "O'yin paytida ovqat yoki ichimlik buyurtma qilmoqchimisiz? 👇",
        reply_markup=menu_kb
    )
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✅ Broningiz tasdiqlandi! O'yin boshlanishidan oldin tayyor bo'ling 🎮", reply_markup=admin_panel_kb())
    await callback.answer()

@dp.callback_query(F.data.startswith("reject_"))
async def reject(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    user_id = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE bookings SET status='rejected' WHERE user_id=? AND status='pending'", (user_id,)
        )
        await db.commit()
    await bot.send_message(user_id, "❌ Afsuski, broningiz rad etildi. Boshqa vaqt tanlang.")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("❌ Afsuski, broningiz rad etildi. Boshqa vaqt tanlang.", reply_markup=admin_panel_kb())
    await callback.answer()

@dp.callback_query(F.data.startswith("delete_"))
async def delete_booking_admin(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    user_id = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM bookings WHERE user_id=? AND status='pending'", (user_id,)
        )
        await db.commit()
    await bot.send_message(user_id, "🗑 Broningiz admin tomonidan bekor qilindi.")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("🗑 Bron muvaffaqiyatli o'chirildi!", reply_markup=admin_panel_kb())
    await callback.answer()

@dp.callback_query(F.data.startswith("ban_"))
async def ban(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    user_id = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO banned_users(user_id) VALUES(?)", (user_id,)
        )
        await db.commit()
    await bot.send_message(user_id, "🚫 Siz tizimdan bloklangansiz. Muammo bo'lsa adminga murojaat qiling.")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("🚫 Foydalanuvchi bloklandi!", reply_markup=admin_panel_kb())
    await callback.answer()


# ================= PENDING BRONLAR =================

@dp.callback_query(F.data == "pending_bookings")
async def pending_bookings(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM bookings WHERE status='pending' ORDER BY id DESC") as cur:
            rows = await cur.fetchall()
    if not rows:
        await callback.message.answer("📭 Kutayotgan bronlar yo'q")
        await callback.answer()
        return
    for r in rows:
        await callback.message.answer(
            f"#{r['id']} | 👤 {r['full_name']}\n🔗 {r['username']}\n"
            f"📱 {r['phone']}\n💻 {r['computer']}\n📅 {r['day']}\n⏰ {r['time']}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Accept", callback_data=f"accept_{r['user_id']}"),
                InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_{r['user_id']}"),
            ]])
        )
    await callback.answer()


# ================= BARCHA BRONLAR =================

@dp.callback_query(F.data == "bookings")
async def bookings(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM bookings ORDER BY id DESC LIMIT 20") as cur:
            rows = await cur.fetchall()
    if not rows:
        await callback.message.answer("📭 Hali hech qanday bron yo'q")
        await callback.answer()
        return
    for r in rows:
        emoji = STATUS_EMOJI.get(r["status"], "❓")
        await callback.message.answer(
            f"#{r['id']} | {emoji} {r['status']}\n"
            f"👤 {r['full_name']}\n🔗 {r['username']}\n"
            f"📱 {r['phone']}\n💻 {r['computer']}\n📅 {r['day']}\n⏰ {r['time']}"
        )
    await callback.answer()


# ================= TOP PLAYERS =================

@dp.callback_query(F.data == "top_players")
async def top_players(callback: CallbackQuery):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT username, COUNT(*) AS total FROM bookings
            WHERE status='accepted' GROUP BY username ORDER BY total DESC LIMIT 10
        """) as cur:
            rows = await cur.fetchall()
    if not rows:
        await callback.message.answer("📭 Hali reyting ma'lumotlari yo'q")
        await callback.answer()
        return
    medals = ["🥇","🥈","🥉"]
    text   = "🏆 <b>TOP PLAYERS</b>\n\n"
    for i, (username, total) in enumerate(rows):
        medal  = medals[i] if i < 3 else "🎮"
        text  += f"{medal} {username} — {total} ta bron\n"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


# ================= STATISTIKA =================

@dp.callback_query(F.data == "stats")
async def stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM bookings") as cur:
            (total,)    = await cur.fetchone()
        async with db.execute("SELECT COUNT(*) FROM bookings WHERE status='accepted'") as cur:
            (accepted,) = await cur.fetchone()
        async with db.execute("SELECT COUNT(*) FROM bookings WHERE status='pending'") as cur:
            (pending,)  = await cur.fetchone()
        async with db.execute("SELECT COUNT(*) FROM banned_users") as cur:
            (banned,)   = await cur.fetchone()
    await callback.message.answer(
        f"📊 <b>Statistika</b>\n\n"
        f"📥 Jami bron:     {total}\n"
        f"✅ Tasdiqlangan:  {accepted}\n"
        f"🕓 Pending:       {pending}\n"
        f"🚫 Ban userlar:   {banned}",
        parse_mode="HTML"
    )
    await callback.answer()


# ================= SCHEDULE =================

@dp.callback_query(F.data == "schedule")
async def schedule(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    today = date.today().strftime("%Y-%m-%d")
    text  = f"📅 <b>Bugungi jadval ({today})</b>\n\n"
    async with aiosqlite.connect(DB_PATH) as db:
        for i in range(1, 31):
            pc = f"PC{i}"
            async with db.execute("""
                SELECT time FROM bookings
                WHERE computer=? AND day=? AND status IN ('accepted', 'pending')
                ORDER BY time
            """, (pc, today)) as cur:
                rows = await cur.fetchall()
            if rows:
                times = ", ".join(r[0] for r in rows)
                text += f"🔴 {pc} | {times}\n"
            else:
                text += f"🟢 {pc}\n"
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


# ================= UNBAN / BANLIST =================

@dp.message(Command("unban"))
async def unban(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❌ To'g'ri format: /unban 123456789")
        return
    user_id = int(args[1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM banned_users WHERE user_id=?", (user_id,))
        await db.commit()
    await message.answer(f"✅ {user_id} unblock qilindi!")

@dp.message(Command("banlist"))
async def banlist(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM banned_users") as cur:
            rows = await cur.fetchall()
    if not rows:
        await message.answer("📭 Bloklangan foydalanuvchilar yo'q")
        return
    text = "🚫 <b>Ban List:</b>\n\n" + "".join(f"👤 {r[0]}\n" for r in rows)
    await message.answer(text, parse_mode="HTML")


# ================= SEARCH =================

@dp.message(F.text.startswith("@"))
async def search(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM bookings WHERE username=? ORDER BY id DESC LIMIT 1",
            (message.text,)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        await message.answer("❌ Bunday foydalanuvchi topilmadi")
        return
    emoji = STATUS_EMOJI.get(row["status"], "❓")
    await message.answer(
        f"👤 {row['full_name']}\n🔗 {row['username']}\n📱 {row['phone']}\n"
        f"💻 {row['computer']}\n📅 {row['day']}\n⏰ {row['time']}\n📌 {emoji} {row['status']}"
    )


# ================= USERS (ADMIN) =================

@dp.message(Command("users"))
async def users_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT user_id, full_name, username, phone,
                   COUNT(*) as total,
                   SUM(CASE WHEN status='accepted' THEN 1 ELSE 0 END) as accepted
            FROM bookings
            GROUP BY user_id
            ORDER BY total DESC
        """) as cur:
            rows = await cur.fetchall()
    if not rows:
        await message.answer("📭 Hali hech qanday foydalanuvchi yo'q")
        return
    text = f"👥 <b>Foydalanuvchilar ({len(rows)} ta)</b>\n\n"
    for user_id, full_name, username, phone, total, accepted in rows:
        text += (
            f"👤 {full_name} | {username}\n"
            f"🆔 <code>{user_id}</code> | 📱 {phone}\n"
            f"📊 Jami: {total} | ✅ Tasdiqlangan: {accepted}\n"
            f"➖➖➖➖➖➖➖➖\n"
        )
        if len(text) > 3500:
            await message.answer(text, parse_mode="HTML")
            text = ""
    if text:
        await message.answer(text, parse_mode="HTML")


# ================= RATING TIZIMI =================

async def check_ratings():
    """Bron tugagandan 5 daqiqa o'tib reyting so'raydi."""
    now = datetime.now()
    check_time = now - timedelta(minutes=5)
    day_str  = check_time.strftime("%Y-%m-%d")
    time_str = check_time.strftime("%H:00")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM bookings
            WHERE day=? AND time=? AND status='accepted' AND rating_sent=0
        """, (day_str, time_str)) as cur:
            rows = await cur.fetchall()
        for row in rows:
            try:
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="⭐ 1", callback_data=f"rate_{row['id']}_1"),
                    InlineKeyboardButton(text="⭐ 2", callback_data=f"rate_{row['id']}_2"),
                    InlineKeyboardButton(text="⭐ 3", callback_data=f"rate_{row['id']}_3"),
                    InlineKeyboardButton(text="⭐ 4", callback_data=f"rate_{row['id']}_4"),
                    InlineKeyboardButton(text="⭐ 5", callback_data=f"rate_{row['id']}_5"),
                ]])
                await bot.send_message(
                    row["user_id"],
                    f"🎮 Sессия tugadi!\n\n"
                    f"💻 {row['computer']} da o'ynagan vaqtingiz qanday o'tdi?\n"
                    f"Baholang (1-5 yulduz):",
                    reply_markup=kb
                )
                await db.execute(
                    "UPDATE bookings SET rating_sent=1 WHERE id=?", (row["id"],)
                )
                await db.commit()
            except Exception as e:
                print(f"Rating xato: {e}")


@dp.callback_query(F.data.startswith("rate_"))
async def handle_rating(callback: CallbackQuery):
    parts      = callback.data.split("_")
    booking_id = int(parts[1])
    score      = int(parts[2])

    async with aiosqlite.connect(DB_PATH) as db:
        # Avval bu bron uchun reyting berilganmi?
        async with db.execute(
            "SELECT 1 FROM ratings WHERE booking_id=?", (booking_id,)
        ) as cur:
            exists = await cur.fetchone()
        if exists:
            await callback.answer("✅ Siz allaqachon baho berdingiz!", show_alert=True)
            return
        await db.execute(
            "INSERT INTO ratings (booking_id, user_id, score) VALUES (?,?,?)",
            (booking_id, callback.from_user.id, score)
        )
        await db.commit()

    stars = "⭐" * score
    await callback.message.edit_text(
        f"✅ Bahoyingiz qabul qilindi!\n\n{stars} ({score}/5)\n\nRahmat! 🙏"
    )

    # Adminga ham yuborish
    await bot.send_message(
        ADMIN_ID,
        f"⭐ Yangi reyting!\n\n"
        f"👤 {callback.from_user.full_name}\n"
        f"🆔 <code>{callback.from_user.id}</code>\n"
        f"{'⭐' * score} ({score}/5)",
        parse_mode="HTML"
    )
    await callback.answer()


# ================= WEB APP ORDER =================

@dp.message(F.web_app_data)
async def handle_order(message: Message):
    import json
    try:
        data  = json.loads(message.web_app_data.data)
        items = data.get("items", [])
        total = data.get("totalPrice", 0)
        user  = message.from_user

        # Userning hozirgi kompyuterini topish
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT computer, day, time FROM bookings
                WHERE user_id=? AND status='accepted'
                ORDER BY id DESC LIMIT 1
            """, (user.id,)) as cur:
                booking = await cur.fetchone()

        computer_info = ""
        admin_computer = ""
        if booking:
            computer_info = f"\n💻 {booking['computer']} | ⏰ {booking['time']}"
            admin_computer = f"💻 Kompyuter: <b>{booking['computer']}</b>\n📅 {booking['day']} | ⏰ {booking['time']}\n\n"

        # Foydalanuvchiga tasdiqlash
        lines = "\n".join(f"{i['emoji']} {i['name']} x{i['qty']} — {i['price']*i['qty']:,} so'm" for i in items)
        await message.answer(
            f"✅ Zakazingiz qabul qilindi!{computer_info}\n\n"
            f"{lines}\n\n"
            f"💰 Jami: {total:,} so'm\n\n"
            "Tez orada olib kelishadi! 🚀"
        )

        # Adminga yuborish
        username = f"@{user.username}" if user.username else "yo'q"
        admin_lines = "\n".join(f"  {i['emoji']} {i['name']} x{i['qty']} = {i['price']*i['qty']:,} so'm" for i in items)
        await bot.send_message(
            ADMIN_ID,
            f"🛒 <b>Yangi zakaz!</b>\n\n"
            f"👤 {user.full_name}\n"
            f"🔗 {username}\n"
            f"🆔 <code>{user.id}</code>\n\n"
            f"{admin_computer}"
            f"📋 Mahsulotlar:\n{admin_lines}\n\n"
            f"💰 Jami: {total:,} so'm",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Yetkazildi!", callback_data=f"order_done_{user.id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"order_reject_{user.id}"),
            ]])
        )
    except Exception as e:
        print(f"Order xato: {e}")
        await message.answer("❌ Xato yuz berdi. Qayta urinib ko'ring.")


@dp.callback_query(F.data.startswith("order_done_"))
async def order_done(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    user_id = int(callback.data.split("_")[2])
    await bot.send_message(user_id, "✅ Zakazingiz yo'lda! Biroz sabr qiling 🚀")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Tasdiqlandi!")


@dp.callback_query(F.data.startswith("order_reject_"))
async def order_reject(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    user_id = int(callback.data.split("_")[2])
    await bot.send_message(user_id, "❌ Kechirasiz, hozircha bu mahsulot mavjud emas. Boshqa narsa tanlang.")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Rad etildi!")


# ================= MAIN =================

async def main():
    await init_db()

    # Commands ro'yxati — /  yozganda chiqadi
    from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

    await bot.set_my_commands([
        BotCommand(command="start",     description="🏠 Bosh menu"),
        BotCommand(command="booking",   description="🎮 Bron qilish"),
    ], scope=BotCommandScopeDefault())

    await bot.set_my_commands([
        BotCommand(command="start",     description="🏠 Bosh menu"),
        BotCommand(command="admin",     description="👑 Admin panel — boshqaruv markazi"),
        BotCommand(command="users",     description="👥 Foydalanuvchilar ro'yxati"),
        BotCommand(command="broadcast", description="📢 Hammaga xabar yuborish"),
        BotCommand(command="clear",     description="🗑 Bronlarni tozalash"),
        BotCommand(command="del",       description="❌ Bronni o'chirish (/del 5 yoki /del PC3)"),
        BotCommand(command="banlist",   description="🚫 Ban ro'yxati"),
        BotCommand(command="unban",     description="🔓 Unban (/unban ID)"),
    ], scope=BotCommandScopeChat(chat_id=ADMIN_ID))

    scheduler.add_job(check_reminders, "interval", minutes=1)
    scheduler.add_job(check_ratings,   "interval", minutes=1)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
