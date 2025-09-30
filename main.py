import asyncio
import json
import logging
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error, parse, request

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

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

PAGE_SIZE = 200
MAX_PAGES = 10
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
        "back": "⬅️ Назад",
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
        "back": "⬅️ Ortga",
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
        "back": "⬅️ Бозгашт",
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
        "back": "⬅️ Артқа",
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
        "back": "⬅️ Артка",
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
        "back": "⬅️ Back",
        "departure": "Departure",
        "arrival": "Arrival",
        "airline": "Airline",
        "flight_number": "Flight",
        "price": "Price",
        "aircraft": "Aircraft",
    },
}

class FlightSearch(StatesGroup):
    waiting_for_language = State()
    waiting_for_action = State()
    waiting_for_origin = State()
    waiting_for_destination = State()
    waiting_for_date = State()


def get_message(language: str, key: str) -> str:
    language_data = MESSAGES.get(language, MESSAGES["en"])
    if key in language_data:
        return language_data[key]
    return MESSAGES["en"].get(key, "")


LANGUAGE_LABEL_TO_CODE = {label: code for code, label in LANGUAGE_OPTIONS}


def build_language_keyboard() -> ReplyKeyboardMarkup:
    buttons: List[List[KeyboardButton]] = []
    row: List[KeyboardButton] = []
    for idx, (_, label) in enumerate(LANGUAGE_OPTIONS, start=1):
        row.append(KeyboardButton(text=label))
        if idx % 2 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=True)

def build_main_menu(language: str) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text=get_message(language, "search_flights"))],
        [KeyboardButton(text=get_message(language, "change_language"))],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


def build_search_keyboard(language: str, include_nearest: bool = False) -> ReplyKeyboardMarkup:
    buttons: List[List[KeyboardButton]] = []
    if include_nearest:
        buttons.append([KeyboardButton(text=get_message(language, "nearest_button"))])
    buttons.append([KeyboardButton(text=get_message(language, "back"))])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


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
        await bot.send_message(
            chat_id,
            get_message(language, "ask_origin"),
            reply_markup=build_search_keyboard(language),
        )
        return

    await bot.send_message(chat_id, get_message(language, "searching"))
    flights = await fetch_flights(origin, destination, departure_date, language)
    if flights is None:
        await bot.send_message(chat_id, get_message(language, "error_fetch"))
    elif not flights:
        await bot.send_message(chat_id, get_message(language, "no_flights"))
    else:
        fallback_dt = datetime.max.replace(tzinfo=timezone.utc)

        def flight_sort_key(item: Dict[str, Any]) -> Tuple[datetime, str]:
            departure_raw = item.get("departure_at")
            if isinstance(departure_raw, str):
                try:
                    parsed = datetime.fromisoformat(departure_raw.replace("Z", "+00:00"))
                except ValueError:
                    parsed = None
                if parsed is not None:
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    else:
                        parsed = parsed.astimezone(timezone.utc)
                    return parsed, departure_raw
            return fallback_dt, str(departure_raw or "")

        flights.sort(key=flight_sort_key)
        if departure_date is None:
            flights = flights[:5]

        await enrich_airline_names(language, flights)
        for chunk in format_flights(language, flights):
            await bot.send_message(chat_id, chunk)

    await state.update_data(origin=None, destination=None)
    await state.set_state(FlightSearch.waiting_for_origin)
    await bot.send_message(
        chat_id,
        get_message(language, "ask_origin"),
        reply_markup=build_search_keyboard(language),
    )


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
        "limit": PAGE_SIZE,
        "one_way": "true",
        "token": API_TOKEN,
        "currency": currency,
        "sorting": "price",
        "unique": "false",
        "trip_class": 0,
        "page": 1,
        "locale": get_locale(language),
        "direct": "false",
    }
    date_filter: Optional[date] = None
    date_filter_str: Optional[str] = None
    if departure_date:
        date_filter = departure_date.date()
        date_filter_str = departure_date.strftime("%Y-%m-%d")
        params["departure_at"] = date_filter_str
        params["depart_date"] = f"{date_filter_str}:{date_filter_str}"

    loop = asyncio.get_running_loop()

    base_params = params.copy()

    def _do_request() -> Optional[List[Dict[str, Any]]]:
        collected: List[Dict[str, Any]] = []
        seen: set[Tuple[Any, ...]] = set()
        page_number = 1
        next_url: Optional[str] = f"{API_URL}?{parse.urlencode(base_params)}"
        pages_fetched = 0
        while next_url and pages_fetched < MAX_PAGES:
            pages_fetched += 1
            req = request.Request(
                next_url,
                headers={"User-Agent": "atlas-travel-bot/1.0"},
            )
            try:
                with request.urlopen(req, timeout=15) as response:
                    payload = response.read().decode("utf-8")
            except error.URLError as exc:  # pragma: no cover - network errors are handled gracefully
                logging.error("Failed to fetch flights: %s", exc)
                return collected or None
            try:
                body = json.loads(payload)
            except json.JSONDecodeError as exc:
                logging.error("Failed to decode response: %s", exc)
                return collected or None
            data = body.get("data")
            if not isinstance(data, list):
                break
            for item in data:
                key = (
                    item.get("flight_number") or item.get("number"),
                    item.get("departure_at"),
                    item.get("airline"),
                    item.get("return_at"),
                    item.get("price"),
                )
                if key in seen:
                    continue
                seen.add(key)
                collected.append(item)

            meta = body.get("meta")
            next_link: Optional[str] = None
            if isinstance(meta, dict):
                links = meta.get("links")
                if isinstance(links, dict):
                    raw_next = links.get("next")
                    if isinstance(raw_next, str) and raw_next:
                        next_link = raw_next

            if next_link:
                parsed = parse.urlparse(next_link)
                if not parsed.scheme:
                    base = API_URL if API_URL.endswith("/") else API_URL + "/"
                    next_url = parse.urljoin(base, next_link)
                else:
                    next_url = next_link
            elif len(data) < PAGE_SIZE:
                break
            else:
                page_number += 1
                next_params = base_params.copy()
                next_params["page"] = page_number
                next_url = f"{API_URL}?{parse.urlencode(next_params)}"
        if date_filter is not None:
            filtered: List[Dict[str, Any]] = []
            for item in collected:
                departure_at = item.get("departure_at")
                if not isinstance(departure_at, str):
                    continue
                try:
                    parsed_dt = datetime.fromisoformat(departure_at.replace("Z", "+00:00"))
                except ValueError:
                    if date_filter_str and departure_at.startswith(date_filter_str):
                        filtered.append(item)
                    continue
                if parsed_dt.date() == date_filter:
                    filtered.append(item)
            collected = filtered
        return collected

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
        currency = get_currency(language)
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
    await state.set_state(FlightSearch.waiting_for_language)
    await message.answer(f"👋\n{LANGUAGE_PROMPT}", reply_markup=keyboard)


def resolve_language_choice(text: str) -> Optional[str]:
    cleaned = text.strip()
    if not cleaned:
        return None
    direct = LANGUAGE_LABEL_TO_CODE.get(cleaned)
    if direct:
        return direct
    lower = cleaned.casefold()
    for code, label in LANGUAGE_OPTIONS:
        if lower in {code.casefold(), label.casefold()}:
            return code
    return None


@dp.message(FlightSearch.waiting_for_language)
async def language_chosen(message: Message, state: FSMContext) -> None:
    text = message.text or ""
    language_code = resolve_language_choice(text)
    if not language_code:
        keyboard = build_language_keyboard()
        await message.answer(f"👋\n{LANGUAGE_PROMPT}", reply_markup=keyboard)
        return

    if language_code not in MESSAGES:
        language_code = "en"

    await set_user_language(message.from_user.id, language_code)
    await state.update_data(language=language_code, origin=None, destination=None)
    await state.set_state(FlightSearch.waiting_for_action)
    await message.answer(
        get_message(language_code, "choose_action"),
        reply_markup=build_main_menu(language_code),
    )


@dp.message(FlightSearch.waiting_for_action)
async def handle_action_choice(message: Message, state: FSMContext) -> None:
    language = await ensure_language(state, message.from_user.id)
    text = (message.text or "").strip()
    search_text = get_message(language, "search_flights")
    change_text = get_message(language, "change_language")

    if text == search_text:
        await state.set_state(FlightSearch.waiting_for_origin)
        await message.answer(
            get_message(language, "ask_origin"),
            reply_markup=build_search_keyboard(language),
        )
        return

    if text == change_text:
        await state.clear()
        keyboard = build_language_keyboard()
        await state.set_state(FlightSearch.waiting_for_language)
        await message.answer(f"👋\n{LANGUAGE_PROMPT}", reply_markup=keyboard)
        return

    await message.answer(
        get_message(language, "choose_action"),
        reply_markup=build_main_menu(language),
    )


@dp.message(FlightSearch.waiting_for_origin)
async def process_origin(message: Message, state: FSMContext) -> None:
    language = await ensure_language(state, message.from_user.id)
    text = (message.text or "").strip()
    back_text = get_message(language, "back")
    if text == back_text:
        await state.update_data(origin=None, destination=None)
        await state.set_state(FlightSearch.waiting_for_action)
        await message.answer(
            get_message(language, "choose_action"),
            reply_markup=build_main_menu(language),
        )
        return

    origin = await resolve_location(text, language)
    if not origin:
        if text:
            await message.answer(get_message(language, "invalid_city"))
        await message.answer(
            get_message(language, "ask_origin"),
            reply_markup=build_search_keyboard(language),
        )
        return
    await state.update_data(origin=origin)
    await message.answer(
        get_message(language, "ask_destination"),
        reply_markup=build_search_keyboard(language),
    )
    await state.set_state(FlightSearch.waiting_for_destination)


@dp.message(FlightSearch.waiting_for_destination)
async def process_destination(message: Message, state: FSMContext) -> None:
    language = await ensure_language(state, message.from_user.id)
    text = (message.text or "").strip()
    back_text = get_message(language, "back")
    if text == back_text:
        await state.update_data(destination=None)
        await state.set_state(FlightSearch.waiting_for_origin)
        await message.answer(
            get_message(language, "ask_origin"),
            reply_markup=build_search_keyboard(language),
        )
        return

    destination = await resolve_location(text, language)
    if not destination:
        if text:
            await message.answer(get_message(language, "invalid_city"))
        await message.answer(
            get_message(language, "ask_destination"),
            reply_markup=build_search_keyboard(language),
        )
        return
    await state.update_data(destination=destination)
    await message.answer(
        get_message(language, "ask_date"),
        reply_markup=build_search_keyboard(language, include_nearest=True),
    )
    await state.set_state(FlightSearch.waiting_for_date)


@dp.message(FlightSearch.waiting_for_date)
async def process_date(message: Message, state: FSMContext) -> None:
    language = await ensure_language(state, message.from_user.id)
    user_data = await state.get_data()
    text = (message.text or "").strip()
    back_text = get_message(language, "back")
    nearest_text = get_message(language, "nearest_button")

    if text == back_text:
        await state.update_data(destination=None)
        await state.set_state(FlightSearch.waiting_for_destination)
        await message.answer(
            get_message(language, "ask_destination"),
            reply_markup=build_search_keyboard(language),
        )
        return

    departure_date: Optional[datetime] = None
    if text and text != nearest_text:
        try:
            departure_date = datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            await message.answer(
                get_message(language, "invalid_date"),
                reply_markup=build_search_keyboard(language, include_nearest=True),
            )
            return
    elif text == nearest_text:
        departure_date = None
    else:
        await message.answer(
            get_message(language, "ask_date"),
            reply_markup=build_search_keyboard(language, include_nearest=True),
        )
        return

    origin = user_data.get("origin", "")
    destination = user_data.get("destination", "")
    await perform_search(message.chat.id, language, origin, destination, departure_date, state)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())