import asyncio
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
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
AUTOCOMPLETE_URL = "https://autocomplete.travelpayouts.com/places2"
AIRLINES_URL = "https://api.travelpayouts.com/data/airlines.json"

DATABASE_PATH = Path("bot_data.db")

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

LANGUAGE_TO_LOCALE = {
    "ru": "ru",
    "uz": "ru",
    "tg": "ru",
    "kk": "ru",
    "ky": "ru",
    "en": "en",
}

SHOW_NEAREST_CALLBACK = "date:any"
ACTION_SEARCH = "action:search"
ACTION_CHANGE_LANGUAGE = "action:change_language"
MAX_RESULTS = 200
TELEGRAM_MESSAGE_LIMIT = 3500

_AIRLINES_CACHE: Optional[Dict[str, Dict[str, Any]]] = None
_AIRLINES_LOCK = asyncio.Lock()

AIRLINE_LANGUAGE_PREFERENCES: Dict[str, Tuple[str, ...]] = {
    "en": ("en", "ru"),
    "ru": ("ru", "en"),
    "uz": ("ru", "en"),
    "tg": ("ru", "en"),
    "kk": ("ru", "en"),
    "ky": ("ru", "en"),
}

MESSAGES: Dict[str, Dict[str, str]] = {
    "ru": {
        "choose_language": "Выберите язык обслуживания:",
        "choose_action": "Что вы хотите сделать?",
        "search_flights": "Поиск авиабилетов",
        "change_language": "Изменить язык",
        "ask_origin": "✈️ Введите город отправления или его IATA-код (например, Москва или MOW).",
        "ask_destination": "📍 Теперь укажите город назначения или IATA-код (например, Дубай или DXB).",
        "ask_date": "📅 Введите дату вылета в формате ГГГГ-ММ-ДД или воспользуйтесь кнопкой ниже, чтобы показать ближайшие рейсы.",
        "invalid_date": "Неверный формат даты. Пожалуйста, используйте ГГГГ-ММ-ДД.",
        "invalid_city": "Не удалось распознать город. Попробуйте указать название или IATA-код.",
        "searching": "🔎 Ищу подходящие рейсы...",
        "error_fetch": "Не удалось получить данные о рейсах. Попробуйте позже.",
        "no_flights": "Ближайших рейсов не найдено.",
        "results_header": "Вот что удалось найти:",
        "new_search": "Введите новый город отправления, чтобы искать снова, или используйте /start для смены языка.",
        "missing_data": "Данные поиска устарели. Нажмите /start, чтобы начать заново.",
        "nearest_button": "Показать ближайшие рейсы",
        "departure": "Вылет",
        "arrival": "Прилет",
        "airline": "Авиакомпания",
        "flight_number": "Рейс",
        "price": "Цена",
        "aircraft": "Самолет",
    },
    "uz": {
        "choose_language": "Tilni tanlang:",
        "choose_action": "Qaysi amalni bajaramiz?",
        "search_flights": "Aviabilet qidirish",
        "change_language": "Tilni o'zgartirish",
        "ask_origin": "✈️ Uchish shahrining nomini yoki IATA kodini kiriting (masalan, Toshkent yoki TAS).",
        "ask_destination": "📍 Endi boradigan manzilning nomini yoki IATA kodini yozing (masalan, Dubay yoki DXB).",
        "ask_date": "📅 Parvoz sanasini YYYY-MM-DD formatida kiriting yoki quyidagi tugmadan eng yaqin reyslarni tanlang.",
        "invalid_date": "Sana formati noto'g'ri. Iltimos, YYYY-MM-DD formatidan foydalaning.",
        "invalid_city": "Shaharni aniqlab bo'lmadi. Nomini yoki IATA kodini qaytadan kiriting.",
        "searching": "🔎 Parvozlar qidirilmoqda...",
        "error_fetch": "Parvoz ma'lumotlarini olish muvaffaqийatsiz tugadi. Birozdan so'ng qayта urinib ko'ring.",
        "no_flights": "Yaqqin reyslar topilmadi.",
        "results_header": "Topilgan variantlar:",
        "new_search": "Qayta qidirish uchun yangi uchish shahrini kiriting yoki tilni almashtirish uchun /start yuboring.",
        "missing_data": "Qidiruv ma'lumotlari eskirdi. /start yuborib yangidan boshlang.",
        "nearest_button": "Eng yaqin reyslar",
        "departure": "Uchish",
        "arrival": "Qo'nish",
        "airline": "Aviakompaniya",
        "flight_number": "Reys",
        "price": "Narxi",
        "aircraft": "Samolyot",
    },
    "tg": {
        "choose_language": "Забони хизматрасониро интихоб кунед:",
        "choose_action": "Амали лозимиро интихоб кунед:",
        "search_flights": "Ҷустуҷӯи парвозҳо",
        "change_language": "Тағйири забон",
        "ask_origin": "✈️ Номи шаҳр ё рамзи IATA-и парвозро ворид кунед (масалан, Душанбе ё DYU).",
        "ask_destination": "📍 Акнун номи самт ё рамзи IATA-ро нависед (масалан, Дубай ё DXB).",
        "ask_date": "📅 Санаи парвозро ба шакли YYYY-MM-DD ворид кунед ё аз тугмаи поён барои парвозҳои наздик истифода баред.",
        "invalid_date": "Сана нодуруст аст. Формати YYYY-MM-DD-ро истифода баред.",
        "invalid_city": "Шаҳр шинохта нашуд. Лутфан ном ё рамзи IATA-ро ворид кунед.",
        "searching": "🔎 Парвозҳо ҷустуҷӯ мешаванд...",
        "error_fetch": "Маълумот дар бораи парвозҳо дастнорас аст. Лутфан дертар кӯшиш кунед.",
        "no_flights": "Парвозҳои наздик ёфт нашуданд.",
        "results_header": "Ин натиҷаҳо дастрасанд:",
        "new_search": "Барои ҷустуҷӯи дубора шаҳрро аз нав ворид кунед ё барои иваз кардани забон /start-ро истифода баред.",
        "missing_data": "Маълумоти ҷустуҷӯ куҳна шуд. Барои оғоз аз нав /start-ро фиристед.",
        "nearest_button": "Парвозҳои наздик",
        "departure": "Парвоз",
        "arrival": "Фуруд",
        "airline": "Ширкати ҳавопаймоӣ",
        "flight_number": "Шумораи парвоз",
        "price": "Нарх",
        "aircraft": "Ҳавопаймо",
    },
    "kk": {
        "choose_language": "Қай тілде жалғасамыз?",
        "choose_action": "Әрі қарай не істейміз?",
        "search_flights": "Әуе билеттерін іздеу",
        "change_language": "Тілді өзгерту",
        "ask_origin": "✈️ Ұшатын қаланың атауын немесе IATA кодын енгізіңіз (мысалы, Алматы немесе ALA).",
        "ask_destination": "📍 Енді баратын бағыттың атауын немесе IATA кодын жазыңыз (мысалы, Дубай немесе DXB).",
        "ask_date": "📅 Ұшу күнін YYYY-MM-DD форматында енгізіңіз немесе төмендегі түймені пайдаланып жақын рейстерді көріңіз.",
        "invalid_date": "Күн форматы дұрыс емес. YYYY-MM-DD форматты пайдаланыңыз.",
        "invalid_city": "Қаланы анықтау мүмкін болмады. Атауын немесе IATA кодын көрсетіңіз.",
        "searching": "🔎 Рейстер ізделуде...",
        "error_fetch": "Рейстер туралы ақпарат алу мүмкін болмады. Кейінірек қайта көріңіз.",
        "no_flights": "Жақын рейстер табылмады.",
        "results_header": "Табылған ұсыныстар:",
        "new_search": "Жаңа іздеу үшін ұшу қаласын қайта енгізіңіз немесе тілді ауыстыру үшін /start командасын пайдаланыңыз.",
        "missing_data": "Іздеу деректері ескірді. Қайта бастау үшін /start жіберіңіз.",
        "nearest_button": "Жақын рейстер",
        "departure": "Ұшу",
        "arrival": "Қону",
        "airline": "Әуе компаниясы",
        "flight_number": "Рейс",
        "price": "Бағасы",
        "aircraft": "Ұшақ",
    },
    "ky": {
        "choose_language": "Тилди тандаңыз:",
        "choose_action": "Кайсы иш-аракетти тандайбыз?",
        "search_flights": "Авиа билет издөө",
        "change_language": "Тилди алмаштыруу",
        "ask_origin": "✈️ Учуп чыгуучу шаардын атын же IATA кодун жазыңыз (мисалы, Бишкек же FRU).",
        "ask_destination": "📍 Эми бара турган шаардын атын же IATA кодун киргизиңиз (мисалы, Дубай же DXB).",
        "ask_date": "📅 Учуу күнүн YYYY-MM-DD форматында жазыңыз же төмөнкү баскыч аркылуу жакынкы рейстерди көрүңүз.",
        "invalid_date": "Дата туура эмес. YYYY-MM-DD форматында жазыңыз.",
        "invalid_city": "Шаар табылган жок. Атын же IATA кодун жазыңыз.",
        "searching": "🔎 Рейстер издөөдө...",
        "error_fetch": "Рейстер боюнча маалымат алуу мүмкүн эмес. Кийин кайра аракет кылыңыз.",
        "no_flights": "Жакынкы рейстер табылган жок.",
        "results_header": "Табылган варианттар:",
        "new_search": "Жаңы издөө үчүн учуп чыгуучу шаардын кодун кайра жазыңыз же тилди алмаштыруу үчүн /start колдонуңуз.",
        "missing_data": "Издөө маалыматы эскирди. /start жөнөтүп кайра баштаңыз.",
        "nearest_button": "Жакынкы рейстер",
        "departure": "Учуу",
        "arrival": "Кону",
        "airline": "Авиакампания",
        "flight_number": "Рейс",
        "price": "Баасы",
        "aircraft": "Учак",
    },
    "en": {
        "choose_language": "Please choose your language:",
        "choose_action": "What would you like to do?",
        "search_flights": "Search flights",
        "change_language": "Change language",
        "ask_origin": "✈️ Enter the departure city's name or IATA code (e.g. London or LON).",
        "ask_destination": "📍 Now provide the destination city's name or IATA code (e.g. Dubai or DXB).",
        "ask_date": "📅 Type the departure date in YYYY-MM-DD format or use the button below to see the nearest flights.",
        "invalid_date": "The date format is invalid. Use YYYY-MM-DD.",
        "invalid_city": "Could not recognise the city. Please enter the name or the IATA code.",
        "searching": "🔎 Looking for available flights...",
        "error_fetch": "Could not retrieve flight data. Please try again later.",
        "no_flights": "No nearby flights were found.",
        "results_header": "Here are the available options:",
        "new_search": "Enter a new departure city to search again or use /start to change the language.",
        "missing_data": "Search data is outdated. Send /start to begin again.",
        "nearest_button": "Show nearest flights",
        "departure": "Departure",
        "arrival": "Arrival",
        "airline": "Airline",
        "flight_number": "Flight",
        "price": "Price",
        "aircraft": "Aircraft",
    },
}

class FlightSearch(StatesGroup):
    waiting_for_action = State()
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


def build_nearest_keyboard(language: str) -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(
        text=get_message(language, "nearest_button"),
        callback_data=SHOW_NEAREST_CALLBACK,
    )
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


def build_main_menu(language: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=get_message(language, "search_flights"), callback_data=ACTION_SEARCH)],
        [InlineKeyboardButton(text=get_message(language, "change_language"), callback_data=ACTION_CHANGE_LANGUAGE)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_locale(language: str) -> str:
    return LANGUAGE_TO_LOCALE.get(language, "en")


LANGUAGE_TO_CURRENCY: Dict[str, str] = {
    "ru": "RUB",
    "uz": "UZS",
    "tg": "TJS",
    "kk": "KZT",
    "ky": "KGS",
    "en": "USD",
}


def get_currency(language: str) -> str:
    return LANGUAGE_TO_CURRENCY.get(language, "USD")


def init_db() -> None:
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                language TEXT NOT NULL
            )
            """
        )
        conn.commit()


async def set_user_language(user_id: int, language: str) -> None:
    loop = asyncio.get_running_loop()

    def _set() -> None:
        with sqlite3.connect(DATABASE_PATH) as conn:
            conn.execute(
                "INSERT INTO user_settings(user_id, language) VALUES(?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET language=excluded.language",
                (user_id, language),
            )
            conn.commit()

    await loop.run_in_executor(None, _set)


async def get_user_language(user_id: int) -> Optional[str]:
    loop = asyncio.get_running_loop()

    def _get() -> Optional[str]:
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.execute(
                "SELECT language FROM user_settings WHERE user_id = ?", (user_id,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    return await loop.run_in_executor(None, _get)


async def ensure_language(state: FSMContext, user_id: int) -> str:
    data = await state.get_data()
    language = data.get("language")
    if isinstance(language, str) and language in MESSAGES:
        return language
    saved = await get_user_language(user_id)
    if isinstance(saved, str) and saved in MESSAGES:
        await state.update_data(language=saved)
        return saved
    return "en"


async def fetch_iata_code(query: str, language: str) -> Optional[str]:
    params = {
        "term": query,
        "locale": get_locale(language),
    }
    url = f"{AUTOCOMPLETE_URL}?{parse.urlencode(params)}"
    req = request.Request(url, headers={"User-Agent": "atlas-travel-bot/1.0"})

    loop = asyncio.get_running_loop()

    def _do_request() -> Optional[str]:
        try:
            with request.urlopen(req, timeout=10) as response:
                payload = response.read().decode("utf-8")
        except error.URLError as exc:  # pragma: no cover - network errors are handled gracefully
            logging.error("Failed to fetch location suggestions: %s", exc)
            return None

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            logging.error("Failed to decode location suggestions: %s", exc)
            return None

        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                code = item.get("code")
                place_type = item.get("type")
                if isinstance(code, str):
                    normalized = code.strip().upper()
                    if len(normalized) == 3 and normalized.isalpha() and place_type in {"city", "airport"}:
                        return normalized
                city_code = item.get("city_code")
                if isinstance(city_code, str):
                    normalized_city = city_code.strip().upper()
                    if len(normalized_city) == 3 and normalized_city.isalpha():
                        return normalized_city
        return None

    return await loop.run_in_executor(None, _do_request)


async def resolve_location(value: str, language: str) -> Optional[str]:
    query = value.strip()
    if not query:
        return None
    candidate = query.upper()
    if len(candidate) == 3 and candidate.isalpha():
        return candidate
    return await fetch_iata_code(query, language)


async def load_airlines() -> Dict[str, Dict[str, Any]]:
    global _AIRLINES_CACHE
    if _AIRLINES_CACHE is not None:
        return _AIRLINES_CACHE

    async with _AIRLINES_LOCK:
        if _AIRLINES_CACHE is not None:
            return _AIRLINES_CACHE

        loop = asyncio.get_running_loop()

        def _do_request() -> Dict[str, Dict[str, Any]]:
            try:
                req = request.Request(
                    AIRLINES_URL,
                    headers={"User-Agent": "atlas-travel-bot/1.0"},
                )
                with request.urlopen(req, timeout=15) as response:
                    payload = response.read().decode("utf-8")
            except error.URLError as exc:  # pragma: no cover - best effort lookup
                logging.error("Failed to fetch airlines directory: %s", exc)
                return {}

            try:
                data = json.loads(payload)
            except json.JSONDecodeError as exc:
                logging.error("Failed to parse airlines directory: %s", exc)
                return {}

            airlines: Dict[str, Dict[str, Any]] = {}
            if isinstance(data, list):
                for entry in data:
                    if not isinstance(entry, dict):
                        continue
                    code_value = entry.get("iata") or entry.get("code")
                    if not isinstance(code_value, str):
                        continue
                    code = code_value.strip().upper()
                    if len(code) != 2 or not code.isalpha():
                        continue
                    translations = entry.get("name_translations")
                    airlines[code] = {
                        "name": entry.get("name"),
                        "name_translations": translations if isinstance(translations, dict) else {},
                    }
            return airlines

        _AIRLINES_CACHE = await loop.run_in_executor(None, _do_request)
        return _AIRLINES_CACHE


def choose_airline_name(language: str, airline_info: Optional[Dict[str, Any]], code: str) -> str:
    if not airline_info:
        return code

    preference = AIRLINE_LANGUAGE_PREFERENCES.get(language, ("en", "ru"))
    translations = airline_info.get("name_translations")
    if isinstance(translations, dict):
        for locale in preference:
            translated = translations.get(locale)
            if isinstance(translated, str) and translated.strip():
                return translated.strip()

    name = airline_info.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()

    return code


async def enrich_airline_names(language: str, flights: List[Dict[str, Any]]) -> None:
    directory = await load_airlines()
    for flight in flights:
        code = flight.get("airline")
        if not isinstance(code, str):
            continue
        airline_code = code.strip().upper()
        if not airline_code:
            continue
        airline_info = directory.get(airline_code)
        flight["airline_name"] = choose_airline_name(language, airline_info, airline_code)


async def perform_search(
    chat_id: int,
    language: str,
    origin: Optional[str],
    destination: Optional[str],
    departure_date: Optional[datetime],
    state: FSMContext,
) -> None:
    if not origin or not destination:
        await bot.send_message(chat_id, get_message(language, "missing_data"))
        await state.update_data(origin=None, destination=None)
        await state.set_state(FlightSearch.waiting_for_origin)
        await bot.send_message(chat_id, get_message(language, "ask_origin"))
        return

    await bot.send_message(chat_id, get_message(language, "searching"))
    flights = await fetch_flights(origin, destination, departure_date, language)
    if flights is None:
        await bot.send_message(chat_id, get_message(language, "error_fetch"))
    elif not flights:
        await bot.send_message(chat_id, get_message(language, "no_flights"))
    else:
        await enrich_airline_names(language, flights)
        flights.sort(key=lambda item: str(item.get("departure_at", "")))
        for chunk in format_flights(language, flights):
            await bot.send_message(chat_id, chunk)

    await state.update_data(origin=None, destination=None)
    await state.set_state(FlightSearch.waiting_for_origin)
    await bot.send_message(chat_id, get_message(language, "ask_origin"))


async def fetch_flights(
    origin: str,
    destination: str,
    departure_date: Optional[datetime],
    language: str,
) -> Optional[List[Dict[str, Any]]]:
    currency = get_currency(language)
    params = {
        "origin": origin.upper(),
        "destination": destination.upper(),
        "limit": MAX_RESULTS,
        "one_way": "true",
        "token": API_TOKEN,
        "currency": currency,
        "sorting": "price",
        "unique": "false",
        "trip_class": 0,
        "page": 1,
        "locale": get_locale(language),
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
    tz_suffix = ""
    if dt.tzinfo is not None:
        offset = dt.tzinfo.utcoffset(dt)
        if offset is not None:
            total_minutes = int(offset.total_seconds() // 60)
            hours, minutes = divmod(abs(total_minutes), 60)
            sign = "+" if total_minutes >= 0 else "-"
            tz_suffix = f" (UTC{sign}{hours:02d}:{minutes:02d})"
    return dt.strftime("%Y-%m-%d %H:%M") + tz_suffix


def format_flights(language: str, flights: List[Dict[str, Any]]) -> List[str]:
    header = get_message(language, "results_header")
    tail = get_message(language, "new_search")
    segments: List[str] = []
    current = header
    labels = {
        "departure": get_message(language, "departure"),
        "arrival": get_message(language, "arrival"),
        "airline": get_message(language, "airline"),
        "flight_number": get_message(language, "flight_number"),
        "price": get_message(language, "price"),
        "aircraft": get_message(language, "aircraft"),
    }
    for flight in flights:
        departure = format_datetime(str(flight.get("departure_at", "-")))
        arrival = format_datetime(str(flight.get("return_at", "-"))) if flight.get("return_at") else None
        airline = flight.get("airline_name") or flight.get("airline") or "-"
        flight_number = flight.get("flight_number") or flight.get("number") or "-"
        price = flight.get("price")
        currency = flight.get("currency", "USD")
        price_value = f"{price} {currency}" if price is not None else "-"
        aircraft = flight.get("aircraft") or flight.get("aircraft_code") or "-"

        flight_lines = [f"• {labels['departure']}: {departure}"]
        if arrival:
            flight_lines.append(f"  {labels['arrival']}: {arrival}")
        flight_lines.append(f"  {labels['airline']}: {airline}")
        flight_lines.append(f"  {labels['flight_number']}: {flight_number}")
        flight_lines.append(f"  {labels['price']}: {price_value}")
        flight_lines.append(f"  {labels['aircraft']}: {aircraft}")

        block = "\n".join(flight_lines)
        addition = ("\n\n" if current else "") + block
        if len(current) + len(addition) > TELEGRAM_MESSAGE_LIMIT:
            if current:
                segments.append(current)
            current = block
        else:
            current += addition

    if tail:
        addition = ("\n\n" if current else "") + tail
        if len(current) + len(addition) <= TELEGRAM_MESSAGE_LIMIT:
            current += addition
        else:
            if current:
                segments.append(current)
            current = tail

    if current:
        segments.append(current)

    return segments


bot = Bot(
    token=TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

init_db()


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
    await set_user_language(callback.from_user.id, language_code)
    await state.update_data(language=language_code, origin=None, destination=None)
    await state.set_state(FlightSearch.waiting_for_action)
    await callback.message.answer(
        get_message(language_code, "choose_action"),
        reply_markup=build_main_menu(language_code),
    )


@dp.callback_query(F.data == ACTION_SEARCH)
async def handle_search_action(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    language = await ensure_language(state, callback.from_user.id)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await state.set_state(FlightSearch.waiting_for_origin)
    await callback.message.answer(get_message(language, "ask_origin"))


@dp.callback_query(F.data == ACTION_CHANGE_LANGUAGE)
async def handle_change_language(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    keyboard = build_language_keyboard()
    await callback.message.answer(f"👋\n{LANGUAGE_PROMPT}", reply_markup=keyboard)


@dp.message(FlightSearch.waiting_for_origin)
async def process_origin(message: Message, state: FSMContext) -> None:
    language = await ensure_language(state, message.from_user.id)
    user_data = await state.get_data()
    raw_origin = message.text or ""
    origin = await resolve_location(raw_origin, language)
    if not origin:
        if raw_origin.strip():
            await message.answer(get_message(language, "invalid_city"))
        await message.answer(get_message(language, "ask_origin"))
        return
    await state.update_data(origin=origin)
    await message.answer(get_message(language, "ask_destination"))
    await state.set_state(FlightSearch.waiting_for_destination)


@dp.message(FlightSearch.waiting_for_destination)
async def process_destination(message: Message, state: FSMContext) -> None:
    language = await ensure_language(state, message.from_user.id)
    user_data = await state.get_data()
    raw_destination = message.text or ""
    destination = await resolve_location(raw_destination, language)
    if not destination:
        if raw_destination.strip():
            await message.answer(get_message(language, "invalid_city"))
        await message.answer(get_message(language, "ask_destination"))
        return
    await state.update_data(destination=destination)
    await message.answer(
        get_message(language, "ask_date"),
        reply_markup=build_nearest_keyboard(language),
    )
    await state.set_state(FlightSearch.waiting_for_date)


@dp.message(FlightSearch.waiting_for_date)
async def process_date(message: Message, state: FSMContext) -> None:
    language = await ensure_language(state, message.from_user.id)
    user_data = await state.get_data()
    raw_date = message.text.strip()

    departure_date: Optional[datetime] = None
    if raw_date:
        try:
            departure_date = datetime.strptime(raw_date, "%Y-%m-%d")
        except ValueError:
            await message.answer(
                get_message(language, "invalid_date"),
                reply_markup=build_nearest_keyboard(language),
            )
            return

    origin = user_data.get("origin", "")
    destination = user_data.get("destination", "")
    await perform_search(message.chat.id, language, origin, destination, departure_date, state)


@dp.callback_query(F.data == SHOW_NEAREST_CALLBACK)
async def show_nearest(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    language = await ensure_language(state, callback.from_user.id)
    user_data = await state.get_data()
    origin = user_data.get("origin")
    destination = user_data.get("destination")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:  # pragma: no cover - message may be missing or already updated
        pass

    await perform_search(callback.message.chat.id, language, origin, destination, None, state)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
