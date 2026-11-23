import asyncio
import logging
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from github import Github, GithubException
from github.Repository import Repository

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = "ВАШ_ТОКЕН_БОТА_ОТ_BOTFATHER"
GITHUB_TOKEN = "ВАШ_PERSONAL_ACCESS_TOKEN_С_GITHUB"  # Нужен для проверки репозиториев и постановки звёзд
# --------------------

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Инициализация GitHub
gh = Github(GITHUB_TOKEN)

# --- БАЗА ДАННЫХ (SQLite) ---
def init_db():
    conn = sqlite3.connect("star_exchange.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            github_username TEXT,
            credits INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS repos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_telegram_id INTEGER,
            repo_full_name TEXT UNIQUE,
            last_verified TIMESTAMP,
            FOREIGN KEY (owner_telegram_id) REFERENCES users (telegram_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exchanges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user_id INTEGER,
            to_repo_id INTEGER,
            timestamp TIMESTAMP,
            FOREIGN KEY (from_user_id) REFERENCES users (telegram_id),
            FOREIGN KEY (to_repo_id) REFERENCES repos (id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_user(telegram_id: int):
    conn = sqlite3.connect("star_exchange.db")
    cursor = conn.cursor()
    cursor.execute("SELECT credits FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def add_credits(telegram_id: int, amount: int):
    conn = sqlite3.connect("star_exchange.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (telegram_id, credits) VALUES (?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET credits = credits + ?
    """, (telegram_id, amount, amount))
    conn.commit()
    conn.close()

# --- СОСТОЯНИЯ FSM ---
class RegisterRepo(StatesGroup):
    waiting_for_repo = State()

# --- ХЕНДЛЕРЫ ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    welcome_text = (
        "👋 Добро пожаловать в **GitHub Star Exchange Bot**!\n\n"
        "Я помогаю разработчикам обмениваться звёздами на GitHub.\n\n"
        "**Как это работает:**\n"
        "1. Добавьте свой репозиторий через /add_repo.\n"
        "2. Ставьте звёзды другим репозиториям из списка /list_repos, зарабатывая кредиты.\n"
        "3. Тратьте кредиты, чтобы другие поставили звёзды вашему проекту.\n\n"
        "💰 Ваш баланс кредитов: **{}**".format(get_user(message.from_user.id))
    )
    await message.answer(welcome_text, parse_mode="Markdown")

@dp.message(Command("add_repo"))
async def cmd_add_repo(message: types.Message, state: FSMContext):
    await message.answer("🔗 Отправьте полное имя вашего GitHub-репозитория в формате `владелец/название` (например, `octocat/Hello-World`):")
    await state.set_state(RegisterRepo.waiting_for_repo)

@dp.message(RegisterRepo.waiting_for_repo)
async def process_repo_name(message: types.Message, state: FSMContext):
    repo_full_name = message.text.strip()
    if "/" not in repo_full_name:
        await message.answer("❌ Неверный формат. Используйте `владелец/название`.")
        return

    try:
        repo: Repository = gh.get_repo(repo_full_name)
    except GithubException:
        await message.answer("❌ Репозиторий не найден или недоступен. Проверьте название и права доступа токена.")
        await state.clear()
        return

    conn = sqlite3.connect("star_exchange.db")
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO repos (owner_telegram_id, repo_full_name) VALUES (?, ?)",
            (message.from_user.id, repo_full_name)
        )
        conn.commit()
        await message.answer(f"✅ Репозиторий **{repo_full_name}** успешно добавлен в систему обмена!")
    except sqlite3.IntegrityError:
        await message.answer("❌ Этот репозиторий уже зарегистрирован.")
    finally:
        conn.close()
        await state.clear()

@dp.message(Command("list_repos"))
async def cmd_list_repos(message: types.Message):
    conn = sqlite3.connect("star_exchange.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id, r.repo_full_name, u.credits 
        FROM repos r
        JOIN users u ON r.owner_telegram_id = u.telegram_id
        WHERE r.owner_telegram_id != ?
        LIMIT 10
    """, (message.from_user.id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await message.answer("📭 Пока нет других репозиториев для обмена. Пригласите коллег!")
        return

    keyboard = []
    for repo_id, full_name, _ in rows:
        keyboard.append([InlineKeyboardButton(text=f"⭐ {full_name}", callback_data=f"star:{repo_id}")])
    keyboard.append([InlineKeyboardButton(text="🔄 Обновить список", callback_data="refresh_list")])

    await message.answer(
        "Выберите репозиторий, чтобы поставить звезду и получить **1 кредит**:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@dp.callback_query(F.data.startswith("star:"))
async def process_star_callback(callback: types.CallbackQuery):
    repo_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    conn = sqlite3.connect("star_exchange.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.repo_full_name, r.owner_telegram_id 
        FROM repos r 
        WHERE r.id = ?
    """, (repo_id,))
    repo_row = cursor.fetchone()
    conn.close()

    if not repo_row:
        await callback.answer("Репозиторий не найден.", show_alert=True)
        return

    repo_full_name, owner_id = repo_row

    if owner_id == user_id:
        await callback.answer("Вы не можете ставить звёзды своему репозиторию.", show_alert=True)
        return

    # Проверка, не ставил ли уже пользователь звезду (упрощённая)
    conn = sqlite3.connect("star_exchange.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM exchanges 
        WHERE from_user_id = ? AND to_repo_id = ?
    """, (user_id, repo_id))
    already_exchanged = cursor.fetchone()
    conn.close()

    if already_exchanged:
        await callback.answer("Вы уже ставили звезду этому репозиторию.", show_alert=True)
        return

    try:
        repo: Repository = gh.get_repo(repo_full_name)
        repo.add_to_stargazers()
    except GithubException as e:
        await callback.answer(f"Ошибка GitHub API: {e.data.get('message', 'Не удалось поставить звезду')}", show_alert=True)
        return

    # Начисляем кредит и записываем обмен
    conn = sqlite3.connect("star_exchange.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO exchanges (from_user_id, to_repo_id, timestamp) VALUES (?, ?, ?)",
        (user_id, repo_id, datetime.now())
    )
    conn.commit()
    conn.close()

    add_credits(user_id, 1)  # Пользователь получает кредит

    await callback.answer("✅ Звезда поставлена! Вы получили 1 кредит.")
    await callback.message.edit_text(
        f"Вы поставили звезду **{repo_full_name}** и заработали 1 кредит.\n"
        f"Ваш баланс: **{get_user(user_id)}** кредитов.",
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "refresh_list")
async def process_refresh(callback: types.CallbackQuery):
    await callback.answer("Список обновлён")
    await cmd_list_repos(callback.message)

# --- ЗАПУСК ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
