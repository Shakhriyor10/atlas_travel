import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib import error, parse, request

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)

API_TOKEN = "a89e7cbe4ff3ee19f171cab072b53881"
TELEGRAM_TOKEN = "8396669139:AAFvr8gWi7uXDMwPLBePF9NmYf16wsHmtPU"
API_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"

LANGUAGE_OPTIONS = [
    ("ru", "🇷🇺 Русский"),
    ("uz", "🇺🇿 O'zbek"),
    ("tg", "🇹🇯 Тоҷикӣ"),
    ("kk", "🇰🇿 Қазақша"),
    ("ky", "🇰🇬 Кыргызча"),
    ("en", "🇬🇧 English"),
]

LANGUAGE_PROMPT = (
    "🇷🇺 Выберите язык обслуживания\n"
    "🇺🇿 Tilni tanlang\n"
    "🇹🇯 Забонро интихоб кунед\n"
    "🇰🇿 Тілді таңдаңыз\n"
    "🇰🇬 Тилди тандаңыз\n"
    "🇬🇧 Please choose your language"
)

MESSAGES: Dict[str, Dict[str, str]] = {
    "ru": {
        "choose_language": "Выберите язык обслуживания:",
        "ask_origin": "✈️ Введите IATA-код города отправления (например, TAS).",
        "ask_destination": "📍 Теперь укажите пункт назначения (IATA-код, например, DXB).",
        "ask_date": "📅 Введите дату вылета в формате ГГГГ-ММ-ДД или отправьте '-' чтобы показать ближайшие рейсы.",
        "invalid_date": "Неверный формат даты. Пожалуйста, используйте ГГГГ-ММ-ДД или '-' для пропуска.",
        "searching": "🔎 Ищу подходящие рейсы...",
        "error_fetch": "Не удалось получить данные о рейсах. Попробуйте позже.",
        "no_flights": "Ближайших рейсов не найдено.",
        "results_header": "Вот что удалось найти:",
        "new_search": "Введите новый город отправления, чтобы искать снова, или используйте /start для смены языка.",
        "departure": "Вылет",
        "arrival": "Прилет",
        "airline": "Авиакомпания",
        "flight_number": "Рейс",
        "price": "Цена",
    },
    "uz": {
        "choose_language": "Tilni tanlang:",
        "ask_origin": "✈️ Uchish shahri IATA kodini kiriting (masalan, TAS).",
        "ask_destination": "📍 Endi boradigan manzilning IATA kodini yozing (masalan, DXB).",
        "ask_date": "📅 Parvoz sanasini YYYY-MM-DD formatida kiriting yoki '-' yuboring va yaqin reyslarni ko'rsatamiz.",
        "invalid_date": "Sana formati noto'g'ri. Iltimos, YYYY-MM-DD formatidan foydalaning yoki '-' yuboring.",
        "searching": "🔎 Parvozlar qidirilmoqda...",
        "error_fetch": "Parvoz ma'lumotlarini olish muvaffaqийatsiz tugadi. Birozdan so'ng qayта urinib ko'ring.",
        "no_flights": "Yaqqin reyslar topilmadi.",
        "results_header": "Topilgan variantlar:",
        "new_search": "Qayta qidirish uchun yangi uchish shahrini kiriting yoki tilni almashtirish uchun /start yuboring.",
        "departure": "Uchish",
        "arrival": "Qo'nish",
        "airline": "Aviakompaniya",
        "flight_number": "Reys",
        "price": "Narxi",
    },
    "tg": {
        "choose_language": "Забони хизматрасониро интихоб кунед:",
        "ask_origin": "✈️ Рамзи IATA фурудгоҳи парвозро ворид кунед (масалан, DYU).",
        "ask_destination": "📍 Акнун рамзи IATA самтро нависед (масалан, DXB).",
        "ask_date": "📅 Санаи парвозро ба шакли YYYY-MM-DD ворид кунед ё '-' фиристед, то парвозҳои наздик нишон дода шаванд.",
        "invalid_date": "Сана нодуруст аст. Формати YYYY-MM-DD-ро истифода баред ё '-' фиристед.",
        "searching": "🔎 Парвозҳо ҷустуҷӯ мешаванд...",
        "error_fetch": "Маълумот дар бораи парвозҳо дастнорас аст. Лутфан дертар кӯшиш кунед.",
        "no_flights": "Парвозҳои наздик ёфт нашуданд.",
        "results_header": "Ин натиҷаҳо дастрасанд:",
        "new_search": "Барои ҷустуҷӯи дубора шаҳрро аз нав ворид кунед ё барои иваз кардани забон /start-ро истифода баред.",
        "departure": "Парвоз",
        "arrival": "Фуруд",
        "airline": "Ширкати ҳавопаймоӣ",
        "flight_number": "Шумораи парвоз",
        "price": "Нарх",
    },
    "kk": {
        "choose_language": "Қай тілде жалғасамыз?",
        "ask_origin": "✈️ Ұшатын қаланың IATA кодын енгізіңіз (мысалы, ALA).",
        "ask_destination": "📍 Енді баратын бағыттың IATA кодын жазыңыз (мысалы, DXB).",
        "ask_date": "📅 Ұшу күнін YYYY-MM-DD форматында жазыңыз немесе жақын рейстер үшін '-' жіберіңіз.",
        "invalid_date": "Күн форматы дұрыс емес. YYYY-MM-DD форматын пайдаланыңыз немесе '-' жіберіңіз.",
        "searching": "🔎 Рейстер ізделуде...",
        "error_fetch": "Рейстер туралы ақпарат алу мүмкін болмады. Кейінірек қайта көріңіз.",
        "no_flights": "Жақын рейстер табылмады.",
        "results_header": "Табылған ұсыныстар:",
        "new_search": "Жаңа іздеу үшін ұшу қаласын қайта енгізіңіз немесе тілді ауыстыру үшін /start командасын пайдаланыңыз.",
        "departure": "Ұшу",
        "arrival": "Қону",
        "airline": "Әуе компаниясы",
        "flight_number": "Рейс",
        "price": "Бағасы",
    },
    "ky": {
        "choose_language": "Тилди тандаңыз:",
        "ask_origin": "✈️ Учуп чыгуучу шаардын IATA кодун жазыңыз (мисалы, FRU).",
        "ask_destination": "📍 Эми бара турган жердин IATA кодун киргизиңиз (мисалы, DXB).",
        "ask_date": "📅 Учуу күнүн YYYY-MM-DD форматында жазыңыз же жакынкы рейстер үчүн '-' жөнөтүңүз.",
        "invalid_date": "Дата туура эмес. YYYY-MM-DD форматында жазыңыз же '-' жөнөтүңүз.",
        "searching": "🔎 Рейстер издөөдө...",
        "error_fetch": "Рейстер боюнча маалымат алуу мүмкүн эмес. Кийин кайра аракет кылыңыз.",
        "no_flights": "Жакынкы рейстер табылган жок.",
        "results_header": "Табылган варианттар:",
        "new_search": "Жаңы издөө үчүн учуп чыгуучу шаардын кодун кайра жазыңыз же тилди алмаштыруу үчүн /start колдонуңуз.",
        "departure": "Учуу",
        "arrival": "Кону",
        "airline": "Авиакампания",
        "flight_number": "Рейс",
        "price": "Баасы",
    },
    "en": {
        "choose_language": "Please choose your language:",
        "ask_origin": "✈️ Enter the departure city's IATA code (e.g. LON).",
        "ask_destination": "📍 Now provide the destination IATA code (e.g. DXB).",
        "ask_date": "📅 Type the departure date in YYYY-MM-DD format or send '-' to see the nearest flights.",
        "invalid_date": "The date format is invalid. Use YYYY-MM-DD or '-' to skip.",
        "searching": "🔎 Looking for available flights...",
        "error_fetch": "Could not retrieve flight data. Please try again later.",
        "no_flights": "No nearby flights were found.",
        "results_header": "Here are the available options:",
        "new_search": "Enter a new departure city to search again or use /start to change the language.",
        "departure": "Departure",
        "arrival": "Arrival",
        "airline": "Airline",
        "flight_number": "Flight",
        "price": "Price",
    },
}

DATE_SKIP_ALIASES = {
    "-",
    "skip",
    "пропустить",
    "ближайшие",
    "отмена",
    "yaqin",
    "yo'q",
    "cancel",
}


class FlightSearch(StatesGroup):
    waiting_for_origin = State()
    waiting_for_destination = State()
    waiting_for_date = State()


def get_message(language: str, key: str) -> str:
    language_data = MESSAGES.get(language, MESSAGES["en"])
    if key in language_data:
        return language_data[key]
    return MESSAGES["en"].get(key, "")


def build_language_keyboard() -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for idx, (code, label) in enumerate(LANGUAGE_OPTIONS, start=1):
        row.append(InlineKeyboardButton(text=label, callback_data=f"lang:{code}"))
        if idx % 2 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def fetch_flights(origin: str, destination: str, departure_date: Optional[datetime]) -> Optional[List[Dict[str, Any]]]:
    params = {
        "origin": origin.upper(),
        "destination": destination.upper(),
        "limit": 5,
        "one_way": "true",
        "token": API_TOKEN,
        "sorting": "price",
    }
    if departure_date:
        params["departure_at"] = departure_date.strftime("%Y-%m-%d")

    query = parse.urlencode(params)
    req = request.Request(
        f"{API_URL}?{query}",
        headers={"User-Agent": "atlas-travel-bot/1.0"},
    )

    loop = asyncio.get_running_loop()

    def _do_request() -> Optional[List[Dict[str, Any]]]:
        try:
            with request.urlopen(req, timeout=15) as response:
                payload = response.read().decode("utf-8")
        except error.URLError as exc:  # pragma: no cover - network errors are handled gracefully
            logging.error("Failed to fetch flights: %s", exc)
            return None
        try:
            body = json.loads(payload)
        except json.JSONDecodeError as exc:
            logging.error("Failed to decode response: %s", exc)
            return None
        data = body.get("data")
        if isinstance(data, list):
            return data
        return None

    return await loop.run_in_executor(None, _do_request)


def format_datetime(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return dt.strftime("%Y-%m-%d %H:%M")


def format_flights(language: str, flights: List[Dict[str, Any]]) -> str:
    message_lines = [get_message(language, "results_header")]
    labels = {
        "departure": get_message(language, "departure"),
        "arrival": get_message(language, "arrival"),
        "airline": get_message(language, "airline"),
        "flight_number": get_message(language, "flight_number"),
        "price": get_message(language, "price"),
    }
    for flight in flights:
        departure = format_datetime(str(flight.get("departure_at", "-")))
        arrival = format_datetime(str(flight.get("return_at", "-"))) if flight.get("return_at") else None
        airline = flight.get("airline", "-")
        flight_number = flight.get("flight_number") or flight.get("number") or "-"
        price = flight.get("price")
        currency = flight.get("currency", "USD")
        price_value = f"{price} {currency}" if price is not None else "-"

        flight_lines = [f"• {labels['departure']}: {departure}"]
        if arrival:
            flight_lines.append(f"  {labels['arrival']}: {arrival}")
        flight_lines.append(f"  {labels['airline']}: {airline}")
        flight_lines.append(f"  {labels['flight_number']}: {flight_number}")
        flight_lines.append(f"  {labels['price']}: {price_value}")

        if flight.get("link"):
            flight_lines.append(f"  🔗 {flight['link']}")
        message_lines.append("\n".join(flight_lines))

    message_lines.append("")
    message_lines.append(get_message(language, "new_search"))
    return "\n\n".join(message_lines)


bot = Bot(
    token=TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    keyboard = build_language_keyboard()
    await message.answer(f"👋\n{LANGUAGE_PROMPT}", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("lang:"))
async def language_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    language_code = callback.data.split(":", maxsplit=1)[1]
    if language_code not in MESSAGES:
        language_code = "en"
    await state.update_data(language=language_code)
    await callback.message.answer(get_message(language_code, "ask_origin"))
    await state.set_state(FlightSearch.waiting_for_origin)


@dp.message(FlightSearch.waiting_for_origin)
async def process_origin(message: Message, state: FSMContext) -> None:
    user_data = await state.get_data()
    language = user_data.get("language", "en")
    origin = message.text.strip().upper()
    if not origin:
        await message.answer(get_message(language, "ask_origin"))
        return
    await state.update_data(origin=origin)
    await message.answer(get_message(language, "ask_destination"))
    await state.set_state(FlightSearch.waiting_for_destination)


@dp.message(FlightSearch.waiting_for_destination)
async def process_destination(message: Message, state: FSMContext) -> None:
    user_data = await state.get_data()
    language = user_data.get("language", "en")
    destination = message.text.strip().upper()
    if not destination:
        await message.answer(get_message(language, "ask_destination"))
        return
    await state.update_data(destination=destination)
    await message.answer(get_message(language, "ask_date"))
    await state.set_state(FlightSearch.waiting_for_date)


@dp.message(FlightSearch.waiting_for_date)
async def process_date(message: Message, state: FSMContext) -> None:
    user_data = await state.get_data()
    language = user_data.get("language", "en")
    raw_date = message.text.strip()

    departure_date: Optional[datetime] = None
    if raw_date and raw_date.lower() not in DATE_SKIP_ALIASES:
        try:
            departure_date = datetime.strptime(raw_date, "%Y-%m-%d")
        except ValueError:
            await message.answer(get_message(language, "invalid_date"))
            return

    await message.answer(get_message(language, "searching"))
    origin = user_data.get("origin", "")
    destination = user_data.get("destination", "")

    flights = await fetch_flights(origin, destination, departure_date)
    if flights is None:
        await message.answer(get_message(language, "error_fetch"))
    elif not flights:
        await message.answer(get_message(language, "no_flights"))
    else:
        await message.answer(format_flights(language, flights))

    await state.set_state(FlightSearch.waiting_for_origin)
    await message.answer(get_message(language, "ask_origin"))


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
