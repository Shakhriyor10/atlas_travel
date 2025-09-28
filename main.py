import asyncio
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message


class BookingStates(StatesGroup):
    choosing_language = State()
    entering_origin = State()
    choosing_origin = State()
    entering_destination = State()
    choosing_destination = State()
    awaiting_custom_date = State()


LANGUAGES: Dict[str, Dict[str, Any]] = {
    "ru": {
        "flag": "🇷🇺",
        "label": "Русский",
        "locale": "ru",
        "texts": {
            "greeting": "Добро пожаловать в Atlas Travel!",
            "choose_language": "Пожалуйста, выберите язык.",
            "ask_origin": "Введите город вылета.",
            "origin_options": "Выберите подходящий аэропорт вылета:",
            "ask_destination": "Введите город назначения.",
            "destination_options": "Выберите подходящий аэропорт назначения:",
            "origin_saved": "Город вылета: {city} ({code}).",
            "destination_saved": "Город назначения: {city} ({code}).",
            "searching": "Ищу ближайшие рейсы...",
            "nearest_title": "Ближайшие рейсы:",
            "no_flights": "К сожалению, рейсы не найдены. Попробуйте другую дату или направление.",
            "ask_date": "Введите желаемую дату вылета в формате ГГГГ-ММ-ДД.",
            "invalid_date": "Неверный формат даты. Попробуйте снова в формате ГГГГ-ММ-ДД.",
            "custom_results": "Рейсы на {date}:",
            "another_date": "Вы можете ввести другую дату или нажать /start для нового поиска.",
            "api_error": "Не удалось получить данные. Повторите попытку позже.",
        },
    },
    "uz": {
        "flag": "🇺🇿",
        "label": "O'zbekcha",
        "locale": "uz",
        "texts": {
            "greeting": "Atlas Travel botiga xush kelibsiz!",
            "choose_language": "Iltimos, tilni tanlang.",
            "ask_origin": "Jo'nash shahrini kiriting.",
            "origin_options": "Jo'nash aeroportini tanlang:",
            "ask_destination": "Borish shahrini kiriting.",
            "destination_options": "Borish aeroportini tanlang:",
            "origin_saved": "Jo'nash shahri: {city} ({code}).",
            "destination_saved": "Borish shahri: {city} ({code}).",
            "searching": "Yaqin reyslarni qidiryapman...",
            "nearest_title": "Yaqin reyslar:",
            "no_flights": "Afsuski, reys topilmadi. Boshqa sana yoki yo'nalishni sinab ko'ring.",
            "ask_date": "Sana kiriting (YYYY-MM-DD).",
            "invalid_date": "Sana noto'g'ri formatda. Iltimos, YYYY-MM-DD ko'rinishida kiriting.",
            "custom_results": "{date} sanasidagi reyslar:",
            "another_date": "Boshqa sanani kiriting yoki yangi qidiruv uchun /start bosing.",
            "api_error": "Ma'lumotlarni olish imkoni bo'lmadi. Iltimos, keyinroq urinib ko'ring.",
        },
    },
    "tg": {
        "flag": "🇹🇯",
        "label": "Тоҷикӣ",
        "locale": "ru",
        "texts": {
            "greeting": "Ба Atlas Travel хуш омадед!",
            "choose_language": "Лутфан забонро интихоб кунед.",
            "ask_origin": "Шаҳри парвозро ворид кунед.",
            "origin_options": "Фурудгоҳи парвозро интихоб кунед:",
            "ask_destination": "Шаҳри таъинотро ворид кунед.",
            "destination_options": "Фурудгоҳи таъинотро интихоб кунед:",
            "origin_saved": "Шаҳри парвоз: {city} ({code}).",
            "destination_saved": "Шаҳри таъинот: {city} ({code}).",
            "searching": "Парвозҳои наздиктаринро ҷустуҷӯ дорам...",
            "nearest_title": "Парвозҳои наздиктарин:",
            "no_flights": "Мутаассифона, парвоз ёфт нашуд. Лутфан сана ё самти дигарро санҷед.",
            "ask_date": "Санаи парвозро дар шакли YYYY-MM-DD ворид кунед.",
            "invalid_date": "Сана дуруст ворид нашуд. Лутфан шакли YYYY-MM-DD-ро истифода баред.",
            "custom_results": "Парвозҳо барои {date}:",
            "another_date": "Шумо метавонед санаи дигарро ворид кунед ё барои ҷустуҷӯи нав /start пахш кунед.",
            "api_error": "Дарёфти маълумот имконпазир нашуд. Баъдтар кӯшиш кунед.",
        },
    },
    "kk": {
        "flag": "🇰🇿",
        "label": "Қазақ тілі",
        "locale": "ru",
        "texts": {
            "greeting": "Atlas Travel ботына қош келдіңіз!",
            "choose_language": "Тілді таңдаңыз.",
            "ask_origin": "Ұшып шығатын қаланы енгізіңіз.",
            "origin_options": "Ұшу әуежайын таңдаңыз:",
            "ask_destination": "Баратын қаланы енгізіңіз.",
            "destination_options": "Бару әуежайын таңдаңыз:",
            "origin_saved": "Ұшу қаласы: {city} ({code}).",
            "destination_saved": "Бару қаласы: {city} ({code}).",
            "searching": "Жақын рейстерді іздеп жатырмын...",
            "nearest_title": "Жақын рейстер:",
            "no_flights": "Өкінішке қарай, рейстер табылмады. Басқа күнді немесе бағытты байқап көріңіз.",
            "ask_date": "Күнді YYYY-MM-DD форматында енгізіңіз.",
            "invalid_date": "Күн форматы қате. Күнді YYYY-MM-DD түрінде енгізіңіз.",
            "custom_results": "{date} күнгі рейстер:",
            "another_date": "Басқа күнді енгізіңіз немесе жаңа іздеу үшін /start басыңыз.",
            "api_error": "Деректерді алу мүмкін болмады. Кейінірек қайта көріңіз.",
        },
    },
    "ky": {
        "flag": "🇰🇬",
        "label": "Кыргызча",
        "locale": "ru",
        "texts": {
            "greeting": "Atlas Travel ботун куттуктайбыз!",
            "choose_language": "Тилди тандаңыз.",
            "ask_origin": "Учуп чыгуучу шаардын атын жазыңыз.",
            "origin_options": "Учуу аэропортун тандаңыз:",
            "ask_destination": "Бараткан шаардын атын жазыңыз.",
            "destination_options": "Баруучу аэропортту тандаңыз:",
            "origin_saved": "Учуп чыгуу шаары: {city} ({code}).",
            "destination_saved": "Бараткан шаары: {city} ({code}).",
            "searching": "Жакынкы рейстерди издеп жатам...",
            "nearest_title": "Жакынкы рейстер:",
            "no_flights": "Тилекке каршы, рейстер табылган жок. Башка күндү же багытты тандап көрүңүз.",
            "ask_date": "Күндү YYYY-MM-DD форматында жазыңыз.",
            "invalid_date": "Күн туура эмес. YYYY-MM-DD форматында жазыңыз.",
            "custom_results": "{date} күнүндөгү рейстер:",
            "another_date": "Башка күндү жазыңыз же жаңы издөө үчүн /start басыңыз.",
            "api_error": "Маалыматты алуу мүмкүн болбоду. Кийинчерээк дагы аракет кылыңыз.",
        },
    },
    "en": {
        "flag": "🇬🇧",
        "label": "English",
        "locale": "en",
        "texts": {
            "greeting": "Welcome to Atlas Travel!",
            "choose_language": "Please choose a language.",
            "ask_origin": "Enter your departure city.",
            "origin_options": "Select your departure airport:",
            "ask_destination": "Enter your destination city.",
            "destination_options": "Select your destination airport:",
            "origin_saved": "Departure city: {city} ({code}).",
            "destination_saved": "Destination city: {city} ({code}).",
            "searching": "Looking for the nearest flights...",
            "nearest_title": "Closest flights:",
            "no_flights": "Sorry, no flights found. Try another date or route.",
            "ask_date": "Enter a departure date in YYYY-MM-DD format.",
            "invalid_date": "Invalid date format. Please use YYYY-MM-DD.",
            "custom_results": "Flights on {date}:",
            "another_date": "You can enter another date or press /start to begin a new search.",
            "api_error": "Failed to retrieve data. Please try again later.",
        },
    },
}

AVIASALES_TOKEN: Optional[str] = None


def build_language_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"{data['flag']} {data['label']}", callback_data=f"lang:{code}")]
        for code, data in LANGUAGES.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_location_keyboard(options: List[Dict[str, str]], prefix: str) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{opt['name']} ({opt['code']}, {opt['country']})",
                callback_data=f"{prefix}:{opt['code']}"
            )
        ]
        for opt in options
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_text(lang: str, key: str, **kwargs: Any) -> str:
    template = LANGUAGES[lang]["texts"][key]
    return template.format(**kwargs)


async def fetch_json(
    session: aiohttp.ClientSession,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    try:
        async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                return await resp.json()
    except (asyncio.TimeoutError, aiohttp.ClientError):
        return None
    return None


async def fetch_city_options(session: aiohttp.ClientSession, query: str, locale: str) -> List[Dict[str, str]]:
    url = "https://autocomplete.travelpayouts.com/places2"
    params = {"term": query, "locale": locale, "types[]": ["city", "airport"]}
    data = await fetch_json(session, url, params=params)
    if not data:
        return []
    options = []
    for item in data[:6]:
        code = item.get("code") or item.get("iata")
        if not code:
            continue
        options.append(
            {
                "code": code,
                "name": item.get("name", "Unknown"),
                "country": item.get("country_name", ""),
            }
        )
    return options


async def fetch_flights(
    session: aiohttp.ClientSession,
    origin: str,
    destination: str,
    departure_date: Optional[datetime] = None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    if not AVIASALES_TOKEN:
        return []
    url = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
    params: Dict[str, Any] = {
        "origin": origin,
        "destination": destination,
        "unique": "true",
        "sorting": "price",
        "direct": "false",
        "limit": limit,
        "currency": "USD",
    }
    if departure_date:
        params["departure_at"] = departure_date.strftime("%Y-%m-%d")
    headers = {"X-Access-Token": AVIASALES_TOKEN}
    data = await fetch_json(session, url, params=params, headers=headers)
    if not data or not data.get("data"):
        return []
    return data["data"]


def format_flight_entry(flight: Dict[str, Any]) -> str:
    departure_raw = flight.get("departure_at")
    return_raw = flight.get("return_at")
    departure_date = datetime.fromisoformat(departure_raw.replace("Z", "+00:00")) if departure_raw else None
    return_date = datetime.fromisoformat(return_raw.replace("Z", "+00:00")) if return_raw else None

    price = flight.get("price")
    airline = flight.get("airline", "")
    flight_number = flight.get("flight_number")
    origin = flight.get("origin")
    destination = flight.get("destination")

    departure_str = departure_date.strftime("%d %b %Y, %H:%M") if departure_date else ""
    return_str = return_date.strftime("%d %b %Y, %H:%M") if return_date else ""

    search_link = None
    if departure_date and origin and destination:
        search_link = (
            "https://www.aviasales.com/search/"
            f"{origin}{departure_date.strftime('%d%m')}{destination}1"
        )

    parts = [
        f"{origin} → {destination}",
        f"🕒 {departure_str}",
    ]
    if return_str:
        parts.append(f"↩️ {return_str}")
    if price is not None:
        parts.append(f"💳 {price} USD")
    if airline:
        number = f" {flight_number}" if flight_number else ""
        parts.append(f"✈️ {airline}{number}")
    if search_link:
        parts.append(f"🔗 [Aviasales]({search_link})")
    return "\n".join(parts)


async def show_nearest_flights(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    origin = data.get("origin")
    destination = data.get("destination")
    if not origin or not destination:
        return

    await message.answer(get_text(lang, "searching"))
    async with aiohttp.ClientSession() as session:
        flights = await fetch_flights(session, origin, destination, limit=5)
    if not flights:
        await message.answer(get_text(lang, "no_flights"))
        return

    lines = [get_text(lang, "nearest_title")]
    for flight in flights:
        lines.append(format_flight_entry(flight))
        lines.append("—")
    lines.pop()
    await message.answer("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    await message.answer(get_text(lang, "ask_date"))
    await state.set_state(BookingStates.awaiting_custom_date)


async def show_custom_date(message: Message, state: FSMContext, lang: str, date_obj: datetime) -> None:
    data = await state.get_data()
    origin = data.get("origin")
    destination = data.get("destination")
    async with aiohttp.ClientSession() as session:
        flights = await fetch_flights(session, origin, destination, departure_date=date_obj, limit=5)
    if not flights:
        await message.answer(get_text(lang, "no_flights"))
        return

    header = get_text(lang, "custom_results", date=date_obj.strftime("%Y-%m-%d"))
    lines = [header]
    for flight in flights:
        lines.append(format_flight_entry(flight))
        lines.append("—")
    lines.pop()
    await message.answer("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    await message.answer(get_text(lang, "another_date"))


async def start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(BookingStates.choosing_language)
    keyboard = build_language_keyboard()
    await message.answer("Atlas Travel", reply_markup=keyboard)


async def language_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    lang_code = callback.data.split(":", 1)[1]
    await state.update_data(language=lang_code)
    lang_text = get_text(lang_code, "greeting")
    await callback.message.edit_text(f"{lang_text}\n\n{get_text(lang_code, 'choose_language')}")
    await callback.message.answer(get_text(lang_code, "ask_origin"))
    await state.set_state(BookingStates.entering_origin)


async def origin_entered(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    locale = LANGUAGES[lang]["locale"]
    async with aiohttp.ClientSession() as session:
        options = await fetch_city_options(session, message.text, locale)
    if not options:
        await message.answer(get_text(lang, "no_flights"))
        return
    await state.update_data(origin_options=options)
    keyboard = build_location_keyboard(options, "origin")
    await message.answer(get_text(lang, "origin_options"), reply_markup=keyboard)
    await state.set_state(BookingStates.choosing_origin)


async def origin_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    lang = data.get("language", "en")
    code = callback.data.split(":", 1)[1]
    options = data.get("origin_options", [])
    selected = next((opt for opt in options if opt["code"] == code), None)
    if not selected:
        await callback.message.answer(get_text(lang, "api_error"))
        return
    await state.update_data(origin=selected["code"], origin_name=selected["name"])
    await callback.message.answer(get_text(lang, "origin_saved", city=selected["name"], code=selected["code"]))
    await callback.message.answer(get_text(lang, "ask_destination"))
    await state.set_state(BookingStates.entering_destination)


async def destination_entered(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    locale = LANGUAGES[lang]["locale"]
    async with aiohttp.ClientSession() as session:
        options = await fetch_city_options(session, message.text, locale)
    if not options:
        await message.answer(get_text(lang, "no_flights"))
        return
    await state.update_data(destination_options=options)
    keyboard = build_location_keyboard(options, "destination")
    await message.answer(get_text(lang, "destination_options"), reply_markup=keyboard)
    await state.set_state(BookingStates.choosing_destination)


async def destination_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    data = await state.get_data()
    lang = data.get("language", "en")
    code = callback.data.split(":", 1)[1]
    options = data.get("destination_options", [])
    selected = next((opt for opt in options if opt["code"] == code), None)
    if not selected:
        await callback.message.answer(get_text(lang, "api_error"))
        return
    await state.update_data(destination=selected["code"], destination_name=selected["name"])
    await callback.message.answer(get_text(lang, "destination_saved", city=selected["name"], code=selected["code"]))
    await state.set_state(BookingStates.awaiting_custom_date)
    try:
        await show_nearest_flights(callback.message, state, lang)
    except TelegramBadRequest:
        await callback.message.answer(get_text(lang, "api_error"))


async def custom_date_entered(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    try:
        date_obj = datetime.strptime(message.text.strip(), "%Y-%m-%d")
    except ValueError:
        await message.answer(get_text(lang, "invalid_date"))
        return

    today = datetime.utcnow().date()
    if date_obj.date() < today:
        date_obj = datetime.combine(today, datetime.min.time())
    await show_custom_date(message, state, lang, date_obj)


async def main() -> None:
    global AVIASALES_TOKEN
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    AVIASALES_TOKEN = os.getenv("AVIASALES_TOKEN")
    if not telegram_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    if not AVIASALES_TOKEN:
        raise RuntimeError("AVIASALES_TOKEN is not set")

    bot = Bot(token=telegram_token, parse_mode=ParseMode.HTML)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.register(start_handler, CommandStart())
    dp.callback_query.register(language_chosen, F.data.startswith("lang:"))
    dp.message.register(origin_entered, BookingStates.entering_origin)
    dp.callback_query.register(origin_chosen, BookingStates.choosing_origin, F.data.startswith("origin:"))
    dp.message.register(destination_entered, BookingStates.entering_destination)
    dp.callback_query.register(
        destination_chosen,
        BookingStates.choosing_destination,
        F.data.startswith("destination:"),
    )
    dp.message.register(custom_date_entered, BookingStates.awaiting_custom_date)

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
