import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- НАСТРОЙКИ ---
BOT_TOKEN = "ВАШ_ТОКЕН_БОТА_ОТ_BOTFATHER"
ADMIN_ID = 123456789  # Ваш Telegram ID (узнать можно у @userinfobot)
YOUR_TG = "@ваш_юзернейм" # Куда переводить пользователя
PRICE = "150 руб."

# Настройка логирования
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Состояния для FSM (чтобы понимать, что юзер нажал "Купить")
class OrderState(StatesGroup):
    waiting_for_username = State()

# --- КЛАВИАТУРЫ ---
def main_menu():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Купить 100 звёзд", callback_data="buy_stars")],
        [InlineKeyboardButton(text="ℹ️ Правила", callback_data="rules")]
    ])
    return kb

# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    text = (
        f"👋 Привет! Это магазин звёзд Telegram.\n\n"
        f"💰 Цена: **100 звёзд = {PRICE}**\n\n"
        f"Нажми на кнопку ниже, чтобы оформить заказ."
    )
    await message.answer(text, reply_markup=main_menu(), parse_mode="Markdown")

@dp.callback_query(F.data == "rules")
async def show_rules(callback: types.CallbackQuery):
    await callback.message.answer(
        "📜 **Правила:**\n"
        "1. Оплата производится вручную.\n"
        f"2. После нажатия «Купить» бот даст ссылку на менеджера ({YOUR_TG}).\n"
        "3. Менеджер проверит оплату и отправит вам звёзды.\n"
        "4. Обман/скам карается баном."
    )
    await callback.answer()

@dp.callback_query(F.data == "buy_stars")
async def process_buy(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ваш **юзернейм** в Telegram (без @), чтобы мы знали, кому отправить звёзды:\n\nНапример: `ivan_ivanov`")
    await state.set_state(OrderState.waiting_for_username)
    await callback.answer()

@dp.message(OrderState.waiting_for_username)
async def get_username(message: types.Message, state: FSMContext):
    target_username = message.text.strip()
    
    # Сохраняем данные
    await state.update_data(target=target_username)
    
    # Сообщение пользователю
    text_user = (
        f"✅ Заявка принята!\n\n"
        f"Вы хотите купить **100 звёзд** для `@{target_username}`.\n"
        f"К оплате: **{PRICE}**.\n\n"
        f"👉 Для оплаты и получения звёзд напишите нашему менеджеру: {YOUR_TG}\n"
        f"Пришлите ему этот чек: `ORDER-{message.from_user.id}`"
    )
    await message.answer(text_user, parse_mode="Markdown")
    
    # Уведомление админу (вам)
    admin_text = (
        f"🔔 **НОВЫЙ ЗАКАЗ!**\n\n"
        f"Покупатель: {message.from_user.full_name} (@{message.from_user.username or 'нет'})\n"
        f"ID покупателя: `{message.from_user.id}`\n"
        f"Получатель звёзд: `@{target_username}`\n"
        f"Сумма: {PRICE}"
    )
    
    try:
        await bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Не удалось отправить сообщение админу: {e}")
        
    await state.clear()

# --- ЗАПУСК ---
async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
