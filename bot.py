import asyncio
import logging
from itertools import count

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# ====== НАСТРОЙКИ ======
BOT_TOKEN = "ВАШ_ТОКЕН_ОТ_BOTFATHER"
ADMIN_ID = 123456789  # ваш Telegram ID (узнать: @userinfobot)

CARD_NUMBER = "0000 0000 0000 0000"  # номер вашей карты
CARD_OWNER = "Иван И."               # имя на карте / банк
PRICE_RUB = 150
STARS_AMOUNT = 100
# =======================

logging.basicConfig(level=logging.INFO)
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

order_ids = count(1)
orders: dict[int, dict] = {}  # order_id -> {"user_id", "username", "status"}


def buy_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"⭐ {STARS_AMOUNT} звёзд — {PRICE_RUB} ₽",
                    callback_data="buy",
                )
            ]
        ]
    )


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Привет! Здесь можно купить Telegram Stars.\n\n"
        f"Пакет: {STARS_AMOUNT} ⭐ за {PRICE_RUB} ₽",
        reply_markup=buy_kb(),
    )


@dp.callback_query(F.data == "buy")
async def buy(call: CallbackQuery):
    order_id = next(order_ids)
    orders[order_id] = {
        "user_id": call.from_user.id,
        "username": call.from_user.username,
        "status": "waiting_payment",
    }
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Я оплатил", callback_data=f"paid:{order_id}"
                )
            ]
        ]
    )
    await call.message.answer(
        f"Заказ №{order_id}\n\n"
        f"Переведите {PRICE_RUB} ₽ на карту:\n"
        f"`{CARD_NUMBER}`\n"
        f"Получатель: {CARD_OWNER}\n\n"
        "После перевода нажмите «Я оплатил» и пришлите скриншот чека.",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    await call.answer()


@dp.callback_query(F.data.startswith("paid:"))
async def paid(call: CallbackQuery):
    order_id = int(call.data.split(":")[1])
    order = orders.get(order_id)
    if not order or order["user_id"] != call.from_user.id:
        return await call.answer("Заказ не найден", show_alert=True)
    order["status"] = "waiting_screenshot"
    await call.message.answer(
        f"Пришлите скриншот оплаты заказа №{order_id} одним фото."
    )
    await call.answer()


@dp.message(F.photo)
async def screenshot(message: Message):
    # берём последний заказ пользователя, ожидающий скриншот
    order_id = next(
        (
            oid
            for oid, o in reversed(list(orders.items()))
            if o["user_id"] == message.from_user.id
            and o["status"] == "waiting_screenshot"
        ),
        None,
    )
    if order_id is None:
        return await message.answer("Сначала создайте заказ: /start")

    orders[order_id]["status"] = "checking"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить", callback_data=f"ok:{order_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить", callback_data=f"no:{order_id}"
                ),
            ]
        ]
    )
    uname = f"@{message.from_user.username}" if message.from_user.username else "без username"
    await bot.send_photo(
        ADMIN_ID,
        message.photo[-1].file_id,
        caption=(
            f"Заказ №{order_id}\n"
            f"Пользователь: {uname} (ID {message.from_user.id})\n"
            f"Сумма: {PRICE_RUB} ₽ → {STARS_AMOUNT} ⭐"
        ),
        reply_markup=kb,
    )
    await message.answer("Скриншот получен, проверяем оплату. Обычно это быстро.")


@dp.callback_query(F.data.startswith(("ok:", "no:")))
async def admin_decision(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return await call.answer("Нет доступа", show_alert=True)

    action, oid = call.data.split(":")
    order = orders.get(int(oid))
    if not order or order["status"] != "checking":
        return await call.answer("Заказ уже обработан", show_alert=True)

    if action == "ok":
        order["status"] = "done"
        await deliver_stars(order["user_id"], STARS_AMOUNT)
        await bot.send_message(
            order["user_id"],
            f"✅ Оплата подтверждена! {STARS_AMOUNT} ⭐ будут отправлены вам.",
        )
        await call.message.edit_caption(
            caption=call.message.caption + "\n\n✅ ПОДТВЕРЖДЕНО"
        )
    else:
        order["status"] = "rejected"
        await bot.send_message(
            order["user_id"],
            "❌ Оплата не найдена. Если это ошибка — напишите в поддержку.",
        )
        await call.message.edit_caption(
            caption=call.message.caption + "\n\n❌ ОТКЛОНЕНО"
        )
    await call.answer()


async def deliver_stars(user_id: int, amount: int):
    """
    Здесь выдача звёзд. Telegram Bot API не умеет переводить звёзды
    на баланс пользователя, поэтому варианты такие:
    1) отправить вручную (через Fragment / подарок);
    2) подключить API стороннего сервиса продажи звёзд.
    Пока бот просто уведомляет вас.
    """
    await bot.send_message(
        ADMIN_ID, f"⚠️ Отправьте {amount} ⭐ пользователю ID {user_id}"
    )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
