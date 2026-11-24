import os
from pathlib import Path
import logging
logging.basicConfig(level=logging.INFO)
import asyncio
import sqlite3
import random
from datetime import date
import os

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton

# ================= НАСТРОЙКИ =================
# ВСТАВЬ СЮДА СВОЙ НОВЫЙ ТОКЕН ОТ BOTFATHER

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================= БАЗА ДАННЫХ =================
# Создаем папку для данных, если её нет
data_dir = Path(os.environ.get("DATA_DIR", "."))
data_dir.mkdir(parents=True, exist_ok=True)

# Подключаемся к базе внутри этой папки
db = sqlite3.connect(str(data_dir / "dangers.db"), check_same_thread=False)
db.execute("""CREATE TABLE IF NOT EXISTS heroes(
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    xp INTEGER DEFAULT 0,
    missed INTEGER DEFAULT 0)""")
db.execute("""CREATE TABLE IF NOT EXISTS quests(
    user_id INTEGER,
    quest TEXT,
    done INTEGER DEFAULT 0)""")
db.execute("""CREATE TABLE IF NOT EXISTS boss(
    id INTEGER PRIMARY KEY,
    health INTEGER DEFAULT 100,
    difficulty_multiplier REAL DEFAULT 1.0)""")
db.execute("""CREATE TABLE IF NOT EXISTS inventory(
    user_id INTEGER,
    item TEXT)""")
db.execute("""CREATE TABLE IF NOT EXISTS daily(
    user_id INTEGER PRIMARY KEY,
    last_date TEXT)""")

# если босса ещё нет в базе — создаём
if db.execute("SELECT 1 FROM boss").fetchone() is None:
    db.execute("INSERT INTO boss (id, health, difficulty_multiplier) VALUES (1, 100, 1.0)")
db.commit()

# ================= ЗВАНИЯ =================
def rank_of(xp: int) -> str:
    if xp >= 500:
        return "🏆 Легенда Политеха"
    if xp >= 300:
        return "🎓 Староста"
    if xp >= 150:
        return "📚 Отличник"
    if xp >= 50:
        return "✏️ Стипендиат"
    return "🐣 Первокурсник"

# ================= КЛАВИАТУРА =================
kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👤 Мой персонаж"), KeyboardButton(text="🗺️ Карта Политеха")],
        [KeyboardButton(text="⚔️ Зачистить зону"), KeyboardButton(text="💥 Атаковать босса")],
        [KeyboardButton(text="💀 Пропустил пары"), KeyboardButton(text="🛒 Магазин")],
        [KeyboardButton(text="🎁 Зачётка")],
    ],
    resize_keyboard=True
)

# ================= /START =================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    name = message.from_user.first_name or "Студент"
    row = db.execute("SELECT user_id FROM heroes WHERE user_id=?", (uid,)).fetchone()
    if not row:
        db.execute("INSERT INTO heroes (user_id, name) VALUES (?, ?)", (uid, name))
        db.commit()
        await message.answer(
            f"Привет, {name}! Ты — студент Политеха. "
            "Твоя цель: прокачать XP зачистками и повергнуть БОССА СЕССИИ! 💥\n\n"
            "Но берегись: за каждый пропуск пар босс становится сильнее (+20 HP)."
        )
    else:
        await message.answer("С возвращением в Политех! 👋")
    await message.answer("Выбирай действие:", reply_markup=kb)

# ================= ПРОФИЛЬ =================
@dp.message(F.text == "👤 Мой персонаж")
async def cmd_profile(message: types.Message):
    uid = message.from_user.id
    row = db.execute("SELECT name, xp, missed FROM heroes WHERE user_id=?", (uid,)).fetchone()
    if not row:
        await message.answer("Сначала создай героя: /start")
        return
    name, xp, missed = row
    inv = db.execute("SELECT item FROM inventory WHERE user_id=?", (uid,)).fetchall()
    inv_text = ", ".join(SHOP[i][0] for i in inv) if inv else "пусто"
    await message.answer(
        f"👤 {name}\n"
        f"⭐ XP: {xp} — {rank_of(xp)}\n"
        f"💀 Пропуски: {missed}\n"
        f"🎒 Инвентарь: {inv_text}"
    )

# ================= ЗАЧИСТКА ЗОНЫ =================
@dp.message(F.text == "⚔️ Зачистить зону")
async def cmd_grind(message: types.Message):
    uid = message.from_user.id
    row = db.execute("SELECT xp FROM heroes WHERE user_id=?", (uid,)).fetchone()
    if not row:
        await message.answer("Сначала создай героя: /start")
        return
    # случайное событие: 10% шанс
    if random.random() < 0.10:
        db.execute("UPDATE heroes SET xp = xp + 30 WHERE user_id=?", (uid,))
        db.commit()
        await message.answer("🎉 Событие! Препод не пришёл на пару — свободный XP! +30 XP")
        return
    db.execute("UPDATE heroes SET xp = xp + 15 WHERE user_id=?", (uid,))
    db.commit()
    await message.answer("⚔️ Ты зачистил зону: конспекты, лабы, семинары. +15 XP")

# ================= ПРОПУСК ПАР =================
@dp.message(F.text == "💀 Пропустил пары")
async def cmd_miss(message: types.Message):
    uid = message.from_user.id
    row = db.execute("SELECT missed FROM heroes WHERE user_id=?", (uid,)).fetchone()
    if not row:
        await message.answer("Сначала создай героя: /start")
        return
    db.execute("UPDATE heroes SET missed = missed + 1 WHERE user_id=?", (uid,))
    db.commit()
    await message.answer(
        "💀 Ты пропустил пары. Босс Сессии стал сильнее (+20 HP)!\n"
        "Не увлекайся — с 6+ пропусками XP за победу над боссом не дадут."
    )

# ================= БОСС =================
@dp.message(F.text == "💥 Атаковать босса")
async def fight_boss(message: types.Message):
    uid = message.from_user.id
    hero_row = db.execute("SELECT xp, missed FROM heroes WHERE user_id=?", (uid,)).fetchone()
    boss_row = db.execute("SELECT health, difficulty_multiplier FROM boss").fetchone()

    if not hero_row or not boss_row:
        await message.answer("Сначала создай героя: /start")
        return

    xp, missed = hero_row
    base_health, multiplier = boss_row

    # Считаем реальное здоровье босса
    current_boss_hp = base_health + (missed * 20)

    # Урон зависит от опыта героя (чем круче, тем сильнее бьёшь)
    damage = max(5, xp // 10)

    if damage >= current_boss_hp:
        # ПОБЕДА!
        # Проверка академической задолженности
        if missed > 5:
            db.execute("UPDATE boss SET health = 100")  # босс возрождается
            db.commit()
            await message.answer(
                f"📉 Босс повержен, но... ты нарушил регламент!\n\n"
                f"У тебя {missed} пропусков — академическая задолженность.\n"
                f"Опыт не начисляется. Сначала закрой долги зачистками,\n"
                f"потом возвращайся за наградой."
            )
            return

        bonus_xp = 100 + (missed * 10)  # бонус зависит от того, сколько долгов закрыл
        db.execute("UPDATE heroes SET xp = xp + ?, missed = 0 WHERE user_id=?", (bonus_xp, uid))
        db.execute("UPDATE boss SET health = 100")  # Сброс босса
        db.commit()
        await message.answer(
            f"💥 КРИТИЧЕСКИЙ УДАР! БОСС ПОВЕРЖЕН! 💥\n\n"
            f"Ты закрыл все долги и сдал сессию!\n"
            f"+{bonus_xp} XP! Пропуски сброшены.\n"
            f"Звание обновлено: {rank_of(xp + bonus_xp)}"
        )
    else:
        # Промежуточный бой: запоминаем урон в базе
        new_health = max(0, current_boss_hp - damage - int(missed * 20))
        db.execute("UPDATE boss SET health = ?", (new_health,))
        db.commit()
        await message.answer(
            f"⚔️ Ты нанёс {damage} урона!\n"
            f"🩸 У босса осталось {current_boss_hp - damage} HP.\n\n"
            "Продолжай зачищать зоны и качать XP — босс ждёт."
        )

# ================= МАГАЗИН =================
SHOP = {
    "cheat":   ("📌 Шпаргалка", 50, "спасает на экзамене"),
    "energy":  ("☕ Энергетик", 30, "закрывает один пропуск"),
    "sticker": ("🎫 Стикер Политеха", 100, "коллекционный флекс"),
}

@dp.message(F.text == "🛒 Магазин")
async def cmd_shop(message: types.Message):
    uid = message.from_user.id
    row = db.execute("SELECT xp FROM heroes WHERE user_id=?", (uid,)).fetchone()
    if not row:
        await message.answer("Сначала создай героя: /start")
        return
    kb_inline = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{SHOP[k][0]} — {SHOP[k][1]} XP", callback_data=f"buy_{k}")]
        for k in SHOP
    ])
    await message.answer(
        f"🛒 Магазин студсовета\nТвой баланс: {row[0]} XP\nВыбирай товар:",
        reply_markup=kb_inline
    )

@dp.callback_query(F.data.startswith("buy_"))
async def buy_item(callback: types.CallbackQuery):
    uid = callback.from_user.id
    key = callback.data[4:]
    name, price, desc = SHOP[key]
    row = db.execute("SELECT xp FROM heroes WHERE user_id=?", (uid,)).fetchone()
    if not row:
        await callback.answer("Сначала создай героя: /start", show_alert=True)
        return
    if row[0] < price:
        await callback.answer("Не хватает XP! Иди зачищать зоны.", show_alert=True)
        return
    db.execute("UPDATE heroes SET xp = xp - ? WHERE user_id=?", (price, uid))
    db.execute("INSERT INTO inventory VALUES (?, ?)", (uid, key))
    if key == "energy":
        db.execute("UPDATE heroes SET missed = MAX(missed - 1, 0) WHERE user_id=?", (uid,))
    db.commit()
    await callback.answer(f"Куплено: {name} — {desc}!")

# ================= ЗАЧЁТКА (ЕЖЕДНЕВНАЯ НАГРАДА) =================
@dp.message(F.text == "🎁 Зачётка")
async def cmd_daily(message: types.Message):
    uid = message.from_user.id
    row = db.execute("SELECT last_date FROM daily WHERE user_id=?", (uid,)).fetchone()
    today = date.today().isoformat()
    if row and row[0] == today:
        await message.answer("🎁 Зачётка сегодня уже получена. Приходи завтра!")
        return
    if row:
        db.execute("UPDATE daily SET last_date=? WHERE user_id=?", (today, uid))
    else:
        db.execute("INSERT INTO daily VALUES (?, ?)", (uid, today))
    db.execute("UPDATE heroes SET xp = xp + 20 WHERE user_id=?", (uid,))
    db.commit()
    await message.answer("🎁 Ты открыл зачётку: +20 XP! Возвращайся завтра.")

# ================= КАРТА ПОЛИТЕХА =================
@dp.message(F.text == "🗺️ Карта Политеха")
async def cmd_map(message: types.Message):
    path = "img/map.png"
    if os.path.exists(path):
        await message.answer_photo(
            FSInputFile(path),
            caption="🗺️ Карта Политеха. Зачисти зоны — и босс не пройдёт!"
        )
    else:
        await message.answer(
            "🗺️ Карта Политеха (файл img/map.png не найден — положи картинку в папку img)\n"
            "Зачисти зоны — и босс не пройдёт!"
        )

# ================= ЗАПУСК =================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
