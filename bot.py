import os
import sqlite3
import random
import time
from datetime import date

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# ---------------------------------------------------------------------------
# Настройки
# ---------------------------------------------------------------------------

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DATA_DIR = os.environ.get("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "game.db")

if not TOKEN:
    raise SystemExit(
        "ОШИБКА: не задана переменная окружения TELEGRAM_BOT_TOKEN.\n"
        "Добавь её в настройках хостинга и перезапусти бота."
    )

bot = Bot(token=TOKEN)
dp = Dispatcher()

ZONE_COOLDOWN = 60          # секунд между зачистками зон
XP_PER_LEVEL = 100          # сколько XP даёт уровень

ZONES = {
    "🏋️ Спортзал":   {"xp": (10, 20), "coins": (5, 12),  "risk": 0.25},
    "📚 Библиотека": {"xp": (12, 24), "coins": (8, 15),  "risk": 0.20},
    "🍜 Столовая":   {"xp": (8, 15),  "coins": (10, 20), "risk": 0.10},
    "🧪 Лаборатория":{"xp": (15, 30), "coins": (12, 25), "risk": 0.35},
}

SHOP = {
    "☕ Кофе (30 монет)":        {"price": 30,  "key": "coffee"},
    "🍬 Энергетик (50 монет)":   {"price": 50,  "key": "energy"},
    "📄 Шпаргалка (120 монет)":  {"price": 120, "key": "cheat"},
}

TITLES = [
    (0, "Первокурсник"),
    (100, "Студент-середнячок"),
    (300, "Опытный курсачодав"),
    (600, "Магистр Политеха"),
    (1000, "Легенда Политеха"),
]

# ---------------------------------------------------------------------------
# База данных
# ---------------------------------------------------------------------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                user_id      INTEGER PRIMARY KEY,
                name         TEXT,
                xp           INTEGER DEFAULT 0,
                coins        INTEGER DEFAULT 0,
                skips        INTEGER DEFAULT 0,
                hp           INTEGER DEFAULT 100,
                boss_hp      INTEGER DEFAULT 0,
                buffs        INTEGER DEFAULT 0,
                last_zone    REAL    DEFAULT 0,
                last_zachet  TEXT    DEFAULT ''
            )
        """)


def get_player(uid: int):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM players WHERE user_id = ?", (uid,)
        ).fetchone()
        return dict(row) if row else None


def create_player(uid: int, name: str):
    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO players (user_id, name) VALUES (?, ?)",
            (uid, name),
        )


def update_player(uid: int, **fields):
    sets = ", ".join(f"{k} = ?" for k in fields)
    with db() as conn:
        conn.execute(
            f"UPDATE players SET {sets} WHERE user_id = ?",
            (*fields.values(), uid),
        )


def level_of(xp: int) -> int:
    return xp // XP_PER_LEVEL + 1


def title_of(xp: int) -> str:
    title = TITLES[0][1]
    for need, t in TITLES:
        if xp >= need:
            title = t
    return title


def boss_max_hp(level: int, skips: int) -> int:
    return 60 + level * 25 + skips * 10

# ---------------------------------------------------------------------------
# Клавиатуры
# ---------------------------------------------------------------------------

def main_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="🧍 Мой персонаж")
    kb.button(text="⚔️ Зачистка зоны")
    kb.button(text="💥 Атаковать босса")
    kb.button(text="🎁 Зачётка")
    kb.button(text="💀 Пропустил пары")
    kb.button(text="🛒 Магазин")
    kb.button(text="🗺️ Карта Политеха")
    kb.adjust(2)
    return kb.as_markup()


def zones_kb():
    kb = ReplyKeyboardBuilder()
    for zone in ZONES:
        kb.button(text=zone)
    kb.button(text="↩️ Назад")
    kb.adjust(2)
    return kb.as_markup()


def shop_kb():
    kb = ReplyKeyboardBuilder()
    for item in SHOP:
        kb.button(text=item)
    kb.button(text="↩️ Назад")
    kb.adjust(1)
    return kb.as_markup()

# ---------------------------------------------------------------------------
# Хендлеры
# ---------------------------------------------------------------------------

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    name = message.from_user.first_name or "Студент"
    create_player(message.from_user.id, name)
    await message.answer(
        f"Привет, {name}! Ты — студент Политеха.\n\n"
        "🎯 Твоя цель: прокачать персонаж, зачищать зоны кампуса,\n"
        "и главное — победить босса-сессию!\n\n"
        "⚠️ Каждый пропуск пары усиливает босса: после 5 пропусков\n"
        "он становится неуязвим, пока ты не закроешь долги.\n\n"
        "Выбирай действие кнопками ниже 👇",
        reply_markup=main_kb(),
    )


@dp.message(F.text == "🧍 Мой персонаж")
async def show_profile(message: types.Message):
    p = get_player(message.from_user.id)
    if not p:
        await message.answer("Сначала напиши /start")
        return
    lvl = level_of(p["xp"])
    next_lvl = lvl * XP_PER_LEVEL
    await message.answer(
        f"🧍 {p['name']}\n\n"
        f"⭐ Звание: {title_of(p['xp'])}\n"
        f"🎚 Уровень: {lvl}\n"
        f"📊 XP: {p['xp']} (до {next_lvl} — следующий уровень)\n"
        f"❤️ HP: {p['hp']}/100\n"
        f"💰 Монеты: {p['coins']}\n"
        f"💀 Пропуски: {p['skips']}\n"
        f"📄 Шпаргалки в рюкзаке: {p['buffs']}"
    )


@dp.message(F.text == "⚔️ Зачистка зоны")
async def zones_menu(message: types.Message):
    if not get_player(message.from_user.id):
        await message.answer("Сначала напиши /start")
        return
    await message.answer(
        "🗺️ Выбирай зону для зачистки.\n"
        "Чем опаснее зона — тем больше награда и шанс нарваться на неприятности:",
        reply_markup=zones_kb(),
    )


@dp.message(F.text.in_(ZONES.keys()))
async def do_zone(message: types.Message):
    p = get_player(message.from_user.id)
    if not p:
        await message.answer("Сначала напиши /start")
        return

    now = time.time()
    left = int(ZONE_COOLDOWN - (now - p["last_zone"]))
    if left > 0:
        await message.answer(
            f"⏳ Ты только что зачищал зону. Отдохни ещё {left} сек."
        )
        return

    zone = ZONES[message.text]
    hp = p["hp"]
    if hp <= 0:
        update_player(message.from_user.id, hp=50)
        hp = 50
        await message.answer("🚑 Ты очнулся в медпункте. HP восстановлено до 50.")
        return

    if random.random() < zone["risk"] and hp <= 30:
        # слабый герой рискует вырубиться
        update_player(message.from_user.id, hp=0, last_zone=now)
        await message.answer(
            f"😵 В зоне «{message.text}» тебя прижали!\n"
            "Сил не хватило — ты вырубился. HP: 0.\n"
            "Восстанови силы в столовой или купи кофе!"
        )
        return

    if random.random() < zone["risk"]:
        dmg = random.randint(10, 25)
        hp = max(0, hp - dmg)
        update_player(message.from_user.id, hp=hp, last_zone=now)
        await message.answer(
            f"⚠️ Зона «{message.text}» оказалась опасной: ты получил {dmg} урона.\n"
            f"❤️ HP: {hp}/100"
        )
        return

    xp_gain = random.randint(*zone["xp"])
    coin_gain = random.randint(*zone["coins"])
    update_player(
        message.from_user.id,
        xp=p["xp"] + xp_gain,
        coins=p["coins"] + coin_gain,
        last_zone=now,
    )
    await message.answer(
        f"✅ Зона «{message.text}» зачищена!\n"
        f"+{xp_gain} XP, +{coin_gain} монет.\n"
        f"📊 XP: {p['xp'] + xp_gain} | 💰 Монеты: {p['coins'] + coin_gain}"
    )


@dp.message(F.text == "💥 Атаковать босса")
async def attack_boss(message: types.Message):
    p = get_player(message.from_user.id)
    if not p:
        await message.answer("Сначала напиши /start")
        return

    lvl = level_of(p["xp"])
    uid = message.from_user.id

    if p["skips"] >= 5:
        await message.answer(
            f"😱 Босс-сессия слишком силён: {p['skips']} пропусков дают ему щит.\n"
            "Сначала закрой долги — сходи на пару (нажми 🎁 Зачётка)!"
        )
        return

    boss_max = boss_max_hp(lvl, p["skips"])
    boss_hp = p["boss_hp"]
    if boss_hp <= 0 or boss_hp > boss_max:
        boss_hp = boss_max  # босс восстановился / встречаем впервые

    damage = 10 + lvl * 2 + p["buffs"] * 15
    used_buffs = p["buffs"]
    new_buffs = 0
    buff_note = ""
    if used_buffs:
        buff_note = f" (шпаргалка добавила +{used_buffs * 15} урона!)"

    if p["hp"] <= 0:
        await message.answer(
            "🚑 У тебя 0 HP — босс даже не заметил твою атаку.\n"
            "Восстанови силы: столовая или ☕ кофе из магазина."
        )
        return

    if damage >= boss_hp:
        gain = 30 + lvl * 10
        new_boss = boss_max_hp(lvl + 1, 0)  # следующий босс чуть сильнее
        update_player(
            uid,
            xp=p["xp"] + gain,
            coins=p["coins"] + 20,
            skips=0,
            boss_hp=new_boss,
            buffs=0,
        )
        await message.answer(
            f"⚔️ Ты наносишь {damage} урона{buff_note}...\n"
            "🏆 ПОБЕДА! Босс-сессия повержена!\n"
            f"Долги по пропускам обнулены, +{gain} XP и +20 монет!\n"
            f"🔥 Из-за двери уже выглядывает следующий босс (HP: {new_boss})!"
        )
        return

    # босс выстоял и бьёт в ответ
    boss_hp -= damage
    taken = random.randint(5, 15)
    hp = max(0, p["hp"] - taken)
    update_player(uid, boss_hp=boss_hp, hp=hp, buffs=new_buffs)
    await message.answer(
        f"⚔️ Ты наносишь {damage} урона{buff_note}!\n"
        f"🛡 HP босса: {boss_hp}/{boss_max}\n"
        f"💥 Босс бьёт в ответ: -{taken} HP (у тебя {hp}/100)\n\n"
        "Копи силы и шпаргалки — и пробуй снова!"
    )


@dp.message(F.text == "🎁 Зачётка")
async def zachetka(message: types.Message):
    p = get_player(message.from_user.id)
    if not p:
        await message.answer("Сначала напиши /start")
        return

    today = date.today().isoformat()
    if p["last_zachet"] == today:
        await message.answer(
            "📚 Ты уже закрывал зачётку сегодня. Приходи завтра!"
        )
        return

    bonus = 20
    update_player(message.from_user.id, xp=p["xp"] + bonus, last_zachet=today)
    await message.answer(
        f"🎓 Зачёт закрыт! +{bonus} XP.\n"
        f"📊 Всего XP: {p['xp'] + bonus}"
    )


@dp.message(F.text == "💀 Пропустил пары")
async def skip_pair(message: types.Message):
    p = get_player(message.from_user.id)
    if not p:
        await message.answer("Сначала напиши /start")
        return

    if p["skips"] >= 5:
        await message.answer(
            "⚠️ У тебя уже 5 пропусков! Босс-сессия неуязвим, пока долги не закрыты.\n"
            "Иди на пару (🎁 Зачётка), а не прогуливай!"
        )
        return

    coins = 15
    update_player(message.from_user.id, skips=p["skips"] + 1, coins=p["coins"] + coins)
    skips = p["skips"] + 1
    warn = (
        "\n🚨 Босс-сессия станет НЕУЯЗВИМЫМ, если пропусков станет 5!"
        if skips == 4 else ""
    )
    await message.answer(
        f"💀 Ты прогулял пару. Соулсмейт-босс стал на {skips * 10} HP сильнее.\n"
        f"Зато в столовой сгоняли за тебя: +{coins} монет.\n"
        f"💀 Пропусков: {skips}/5{warn}"
    )


@dp.message(F.text == "🛒 Магазин")
async def shop_menu(message: types.Message):
    p = get_player(message.from_user.id)
    if not p:
        await message.answer("Сначала напиши /start")
        return
    await message.answer(
        f"🛒 Магазин Политеха. У тебя {p['coins']} монет.\n\n"
        "☕ Кофе — +30 HP\n"
        "🍬 Энергетик — +25 XP\n"
        "📄 Шпаргалка — +15 урона боссу в следующей атаке\n\n"
        "Жми на товар, чтобы купить:",
        reply_markup=shop_kb(),
    )


@dp.message(F.text.in_(SHOP.keys()))
async def buy_item(message: types.Message):
    p = get_player(message.from_user.id)
    if not p:
        await message.answer("Сначала напиши /start")
        return

    item = SHOP[message.text]
    if p["coins"] < item["price"]:
        await message.answer(
            f"💸 Не хватает монет! Нужно {item['price']}, у тебя {p['coins']}.\n"
            "Зачищай зоны или гони с пар на подработки 💀"
        )
        return

    key = item["key"]
    if key == "coffee":
        hp = min(100, p["hp"] + 30)
        update_player(message.from_user.id, coins=p["coins"] - item["price"], hp=hp)
        await message.answer(f"☕ Глотнул кофе. ❤️ HP: {hp}/100")
    elif key == "energy":
        update_player(message.from_user.id, coins=p["coins"] - item["price"], xp=p["xp"] + 25)
        await message.answer(
            f"🍬 Энергетик втянут залпом! +25 XP.\n📊 Всего XP: {p['xp'] + 25}"
        )
    elif key == "cheat":
        update_player(
            message.from_user.id,
            coins=p["coins"] - item["price"],
            buffs=p["buffs"] + 1,
        )
        await message.answer(
            f"📄 Шпаргалка спрятана в рукав. Шпаргалок: {p['buffs'] + 1}.\n"
            "Следующая атака по боссу будет больнее на +15 за каждую!"
        )


@dp.message(F.text == "🗺️ Карта Политеха")
async def map_text(message: types.Message):
    await message.answer(
        "🗺️ Карта Политеха:\n\n"
        "🏛 Главный корпус — здесь висит расписание и закрывается зачётка.\n"
        "🏋️ Спортзал — зачистка даёт XP, но можно получить по башке.\n"
        "📚 Библиотека — спокойная зона, хороший XP.\n"
        "🍜 Столовая — безопасно, много монет.\n"
        "🧪 Лаборатория — самый большой XP, но и самый большой риск.\n\n"
        "💪 Босс-сессия ждёт тебя в аудитории 301."
    )


@dp.message(F.text == "↩️ Назад")
async def go_back(message: types.Message):
    await message.answer("Возвращаемся в главное меню 👇", reply_markup=main_kb())


@dp.message()
async def fallback(message: types.Message):
    await message.answer(
        "Не понял команду 🤔 Пользуйся кнопками ниже!",
        reply_markup=main_kb(),
    )

# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------

async def main():
    init_db()
    print("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
