# -*- coding: utf-8 -*-
# Polytech RPG — игровой Telegram-бот про студента и босса-сессию
# aiogram 3.x + SQLite. Токен берётся из переменной окружения TELEGRAM_BOT_TOKEN.

import os
import sqlite3
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# ---------------- НАСТРОЙКИ ----------------

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# Папка для базы данных: на хостинге платформа подставит DATA_DIR=/app/data,
# локально база создастся рядом с файлом.
DATA_DIR = Path(os.environ.get("DATA_DIR", "."))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "dangers.db"

bot = Bot(token=TOKEN)
dp = Dispatcher()

db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
db.execute("""
    CREATE TABLE IF NOT EXISTS players (
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        skips INTEGER DEFAULT 0,
        hp INTEGER DEFAULT 100,
        has_shpargalka INTEGER DEFAULT 0,
        has_energetik INTEGER DEFAULT 0,
        stickers INTEGER DEFAULT 0,
        last_bonus TEXT DEFAULT ''
    )
""")
db.commit()

# ---------------- КЛАВИАТУРА ----------------

def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Мой персонаж"), KeyboardButton(text="🗺️ Карта Политеха")],
            [KeyboardButton(text="💥 Атаковать босса"), KeyboardButton(text="💀 Пропустил пары")],
            [KeyboardButton(text="🛒 Магазин"), KeyboardButton(text="🎁 Зачётка")],
        ],
        resize_keyboard=True
    )

# ---------------- ВСПОМОГАТЕЛЬНОЕ ----------------

def get_player(user_id):
    cur = db.execute("SELECT * FROM players WHERE user_id=?", (user_id,))
    return cur.fetchone()

def player_is_new(user_id):
    return get_player(user_id) is None

def add_xp(user_id, amount):
    """Добавляет XP и автоматически повышает уровень."""
    cur = db.execute("SELECT xp, level FROM players WHERE user_id=?", (user_id,))
    xp, level = cur.fetchone()
    xp += amount
    while xp >= level * 100:
        xp -= level * 100
        level += 1
        db.execute("UPDATE players SET xp=?, level=? WHERE user_id=?", (xp, level, user_id))
        db.commit()
        return level  # вернём новый уровень, чтобы поздравить
    db.execute("UPDATE players SET xp=? WHERE user_id=?", (xp, user_id))
    db.commit()
    return None

def rank_title(level):
    ranks = {
        1: "Новичок",
        2: "Первокурсник",
        3: "Студент",
        4: "Отличник",
        5: "Староста",
        6: "Магистр Политеха",
    }
    return ranks.get(level, f"Легенда ({level} lvl)")

# ---------------- КОМАНДЫ ----------------

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if player_is_new(message.from_user.id):
        name = message.from_user.first_name or "Студент"
        db.execute("INSERT INTO players (user_id, name) VALUES (?, ?)", (message.from_user.id, name))
        db.commit()
        await message.answer(
            f"Привет, {name}! Добро пожаловать в Polytech RPG! 🎓\n\n"
            "Ты — студент Политеха. Твой главный враг — босс-сессия.\n"
            "Каждый пропуск пар усиливает босса, а зачистки зон дают XP.\n\n"
            "Выбирай действие в меню ниже 👇"
        )
    else:
        name = get_player(message.from_user.id)[1]
        await message.answer(f"С возвращением, {name}! Босс-сессия не дремлет. 👇")

# ---------------- ПРОФИЛЬ ----------------

@dp.message(lambda m: m.text == "👤 Мой персонаж")
async def show_profile(message: types.Message):
    p = get_player(message.from_user.id)
    if p is None:
        await message.answer("Сначала создай персонажа — напиши /start")
        return
    (_, name, xp, level, skips, hp, shp, ener, stick, _) = p
    need = level * 100
    inventory = []
    if shp:
        inventory.append("📜 Шпаргалка")
    if ener:
        inventory.append("⚡ Энергетик")
    if stick:
        inventory.append(f"🏷 Стикеры: {stick}")
    inv_text = ", ".join(inventory) if inventory else "пусто"
    await message.answer(
        f"👤 {name}\n"
        f"🏅 Звание: {rank_title(level)} (уровень {level})\n"
        f"✨ XP: {xp}/{need}\n"
        f"❤️ HP: {hp}\n"
        f"💀 Пропуски: {skips}\n"
        f"🎒 Инвентарь: {inv_text}"
    )

# ---------------- КАРТА (текстовая) ----------------

@dp.message(lambda m: m.text == "🗺️ Карта Политеха")
async def show_map(message: types.Message):
    await message.answer(
        "🗺️ Карта Политеха:\n\n"
        "🏛 Главный корпус — тут висит расписание (+5 XP за визит).\n"
        "🏋️ Спортзал — зачистка даёт +15 XP.\n"
        "📚 Библиотека — можно поднять HP.\n"
        "🍜 Столовая — восстанавливает силы.\n"
        "🧪 Лаборатория — случайное событие: бонус или штраф."
    )

# ---------------- БОСС-СЕССИЯ ----------------

@dp.message(lambda m: m.text == "💥 Атаковать босса")
async def attack_boss(message: types.Message):
    p = get_player(message.from_user.id)
    if p is None:
        await message.answer("Сначала создай персонажа — напиши /start")
        return
    (_, name, xp, level, skips, hp, shp, ener, stick, _) = p

    boss_hp = 50 + level * 20 + skips * 10
    damage = 10 + level * 2
    if shp:
        damage += 15  # шпаргалка усиливает атаку

    if skips >= 5:
        await message.answer(
            f"😱 Босс-сессия слишком силён: {skips} пропусков дают ему щит.\n"
            "Сначала закрой долги — сходи на пару!"
        )
        return

    if xp >= boss_hp:
        gain = 30 + level * 10
        db.execute("UPDATE players SET xp=0, skips=0 WHERE user_id=?", (message.from_user.id,))
        db.commit()
        new_level = add_xp(message.from_user.id, gain)
        text = (
            f"⚔️ Ты атакуешь босса-сессию на {damage} урона...\n"
            f"🏆 ПОБЕДА! Босс повержен!\n"
            f"Долги по пропускам обнулены, получено +{gain} XP!"
        )
        if new_level:
            text += f"\n🎉 Новый уровень! Тебе присвоено звание: {rank_title(new_level)}"
        await message.answer(text)
    else:
        db.execute("UPDATE players SET xp=? WHERE user_id=?", (max(0, xp - damage // 2), message.from_user.id))
        db.commit()
        await message.answer(
            f"⚔️ Ты атакуешь босса-сессию на {damage} урона!\n"
            f"🛡 HP босса: {boss_hp}/{boss_hp}\n"
            f"Босс пока сильнее. Накопи XP и пробуй снова!\n"
            f"(Твои XP: {max(0, xp - damage // 2)})"
        )

# ---------------- ПРОПУСКИ ----------------

@dp.message(lambda m: m.text == "💀 Пропустил пары")
async def skip_classes(message: types.Message):
    p = get_player(message.from_user.id)
    if p is None:
        await message.answer("Сначала создай персонажа — напиши /start")
        return
    db.execute("UPDATE players SET skips=skips+1 WHERE user_id=?", (message.from_user.id,))
    db.commit()
    p = get_player(message.from_user.id)
    await message.answer(
        f"💀 Ты пропустил пары...\n"
        f"Босс-сессия стал сильнее! Теперь у него {50 + p[2] * 20 + p[4] * 10} HP.\n"
        f"Пропусков всего: {p[4]}\n"
        + ("⚠️ При 5 пропусках босс станет неуязвим — закрывай долги!" if p[4] >= 3 else "")
    )

# ---------------- ЗАЧЁТКА (ежедневная награда) ----------------

@dp.message(lambda m: m.text == "🎁 Зачётка")
async def daily_bonus(message: types.Message):
    p = get_player(message.from_user.id)
    if p is None:
        await message.answer("Сначала создай персонажа — напиши /start")
        return
    today = datetime.now().strftime("%Y-%m-%d")
    if p[9] == today:
        await message.answer("🎁 Зачётка уже проставлена сегодня. Приходи завтра!")
        return
    db.execute("UPDATE players SET last_bonus=? WHERE user_id=?", (today, message.from_user.id))
    db.commit()
    new_level = add_xp(message.from_user.id, 20)
    text = "🎁 Зачётка проставлена! +20 XP"
    if new_level:
        text += f"\n🎉 Новый уровень! Тебе присвоено звание: {rank_title(new_level)}"
    await message.answer(text)

# ---------------- МАГАЗИН ----------------

@dp.message(lambda m: m.text == "🛒 Магазин")
async def shop(message: types.Message):
    p = get_player(message.from_user.id)
    if p is None:
        await message.answer("Сначала создай персонажа — напиши /start")
        return
    await message.answer(
        "🛒 Магазин Политеха:\n\n"
        "📜 Шпаргалка — 50 XP (+15 урона боссу)\n"
        "⚡ Энергетик — 30 XP (один пропуск не засчитается)\n"
        "🏷 Стикер Политеха — 20 XP (коллекционный предмет)\n\n"
        "Чтобы купить, напиши: шпаргалка / энергетик / стикер"
    )

@dp.message(lambda m: m.text and m.text.lower() in ("шпаргалка", "энергетик", "стикер"))
async def buy_item(message: types.Message):
    p = get_player(message.from_user.id)
    if p is None:
        await message.answer("Сначала создай персонажа — напиши /start")
        return
    (_, name, xp, level, skips, hp, shp, ener, stick, _) = p
    item = message.text.lower()

    prices = {"шпаргалка": 50, "энергетик": 30, "стикер": 20}
    if xp < prices[item]:
        await message.answer(f"💸 Не хватает XP! Нужно {prices[item]}, у тебя {xp}.")
        return

    if item == "шпаргалка":
        if shp:
            await message.answer("📜 Шпаргалка уже есть в инвентаре!")
            return
        db.execute("UPDATE players SET xp=xp-50, has_shpargalka=1 WHERE user_id=?", (message.from_user.id,))
    elif item == "энергетик":
        if ener:
            await message.answer("⚡ Энергетик уже есть! Выпей перед боем с боссом.")
            return
        db.execute("UPDATE players SET xp=xp-30, has_energetik=1 WHERE user_id=?", (message.from_user.id,))
    else:
        db.execute("UPDATE players SET xp=xp-20, stickers=stickers+1 WHERE user_id=?", (message.from_user.id,))

    db.commit()
    await message.answer(f"✅ Куплено: {item.capitalize()}! Загляни в профиль, чтобы проверить инвентарь.")

# ---------------- ЗАПУСК ----------------

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
