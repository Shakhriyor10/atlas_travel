import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional
from aiogram.client.default import DefaultBotProperties
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiohttp import ClientSession, ClientTimeout


# -------------------- Domain models --------------------
class TripType(str, Enum):
    ONE_WAY = "one_way"
    ROUND_TRIP = "round_trip"


@dataclass
class Flight:
    flight_no: str
    airline: str
    departure_airport: str
    arrival_airport: str
    departure_time: datetime
    arrival_time: datetime
    price: int


# -------------------- Localisation --------------------
LANGUAGES = {
    "ru": "🇷🇺 Русский",
    "uz": "🇺🇿 O'zbekcha",
    "tg": "🇹🇯 Тоҷикӣ",
    "kk": "🇰🇿 Қазақша",
    "ky": "🇰🇬 Кыргызча",
    "en": "🇬🇧 English",
}


AIRLINE_NAMES: Dict[str, str] = {
    "HY": "Uzbekistan Airways",
    "SU": "Aeroflot",
    "S7": "S7 Airlines",
    "KC": "Air Astana",
    "FV": "Rossiya Airlines",
    "TK": "Turkish Airlines",
    "PC": "Pegasus Airlines",
    "FZ": "FlyDubai",
    "U6": "Ural Airlines",
    "YQ": "Tajik Air",
    "SZ": "Somon Air",
}

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "ru": {
        "start_greeting": "Добро пожаловать в Atlas Travel!",
        "choose_language": "Пожалуйста, выберите язык обслуживания:",
        "language_set": "Язык переключен на русский.",
        "choose_trip_type": "Какой тип перелёта вас интересует?",
        "one_way": "Только туда",
        "round_trip": "Туда и обратно",
        "ask_departure_city": "Введите город вылета:",
        "ask_arrival_city": "Введите город прибытия:",
        "no_airports_found": "Аэропорты в этом городе не найдены. Попробуйте другой город.",
        "choose_airport": "Выберите аэропорт:",
        "ask_date_choice": "Показать ближайшие рейсы или указать дату?",
        "nearest_flights": "Ближайшие рейсы",
        "enter_date": "Ввести дату",
        "ask_date_input": "Введите дату в формате ДД.ММ.ГГГГ:",
        "invalid_date_format": "Неверный формат даты. Попробуйте снова (ДД.ММ.ГГГГ).",
        "no_flights_found": "Рейсы не найдены.",
        "flights_found_title": "Доступные рейсы:",
        "flight_line": "{flight} • {departure} → {arrival} • {price}₽",
        "ask_return_date_choice": "Для обратного перелёта выбрать ближайшие рейсы или указать дату?",
        "ask_return_date_input": "Введите дату обратного вылета (ДД.ММ.ГГГГ):",
        "return_flights_title": "Доступные обратные рейсы:",
        "search_complete": "Спасибо! Если хотите начать заново, отправьте /start.",
    },
    "uz": {
        "start_greeting": "Atlas Travel'ga xush kelibsiz!",
        "choose_language": "Iltimos, xizmat tilini tanlang:",
        "language_set": "Til o'zbekchaga o'zgartirildi.",
        "choose_trip_type": "Qanday turdagi parvozni qidiryapsiz?",
        "one_way": "Bir tomonga",
        "round_trip": "Borib kelish",
        "ask_departure_city": "Jo'nash shahrini kiriting:",
        "ask_arrival_city": "Yetib borish shahrini kiriting:",
        "no_airports_found": "Bu shaharda aeroport topilmadi. Boshqa shahar kiriting.",
        "choose_airport": "Aeroportni tanlang:",
        "ask_date_choice": "Yaquin parvozlarni ko'rsatishmi yoki sanani kiritasizmi?",
        "nearest_flights": "Eng yaqin parvozlar",
        "enter_date": "Sanani kiritish",
        "ask_date_input": "Sana kiriting (KK.OO.YYYY):",
        "invalid_date_format": "Sana formati noto'g'ri. Qayta urinib ko'ring (KK.OO.YYYY).",
        "no_flights_found": "Parvozlar topilmadi.",
        "flights_found_title": "Mavjud parvozlar:",
        "flight_line": "{flight} • {departure} → {arrival} • {price}₽",
        "ask_return_date_choice": "Qaytish uchun yaqin parvozlarni ko'rsataymi yoki sanani kiritasizmi?",
        "ask_return_date_input": "Qaytish sanasini kiriting (KK.OO.YYYY):",
        "return_flights_title": "Qaytish parvozlarga mos variantlar:",
        "search_complete": "Rahmat! Qayta boshlash uchun /start yuboring.",
    },
    "tg": {
        "start_greeting": "Хуш омадед ба Atlas Travel!",
        "choose_language": "Лутфан забонро интихоб кунед:",
        "language_set": "Забон ба тоҷикӣ иваз шуд.",
        "choose_trip_type": "Шумо кадом навъи парвозро меҷӯед?",
        "one_way": "Яктарафа",
        "round_trip": "Ду тараф",
        "ask_departure_city": "Шаҳри парвозро ворид кунед:",
        "ask_arrival_city": "Шаҳри фурудро ворид кунед:",
        "no_airports_found": "Дар ин шаҳр фурудгоҳ ёфт нашуд. Шаҳри дигарро санҷед.",
        "choose_airport": "Фурудгоҳро интихоб кунед:",
        "ask_date_choice": "Парвозҳои наздикро нишон диҳам ё сана ворид мекунед?",
        "nearest_flights": "Парвозҳои наздик",
        "enter_date": "Ворид намудани сана",
        "ask_date_input": "Санаро ворид кунед (РР.ММ.СССС):",
        "invalid_date_format": "Формати сана нодуруст аст. Лутфан боз кӯшиш кунед (РР.ММ.СССС).",
        "no_flights_found": "Парвозҳо ёфт нашуданд.",
        "flights_found_title": "Парвозҳои мавҷуда:",
        "flight_line": "{flight} • {departure} → {arrival} • {price}₽",
        "ask_return_date_choice": "Барои парвози бозгашт парвозҳои наздикро нишон диҳам ё сана ворид мекунед?",
        "ask_return_date_input": "Санаи бозгаштро ворид кунед (РР.ММ.СССС):",
        "return_flights_title": "Парвозҳои бозгашт:",
        "search_complete": "Ташаккур! Барои оғоз аз нав /start-ро фиристед.",
    },
    "kk": {
        "start_greeting": "Atlas Travel-ге қош келдіңіз!",
        "choose_language": "Қызмет тілін таңдаңыз:",
        "language_set": "Тіл қазақшаға ауыстырылды.",
        "choose_trip_type": "Қай бағыттағы сапар керек?",
        "one_way": "Бір бағыт",
        "round_trip": "Бару-қайту",
        "ask_departure_city": "Ұшып шығатын қаланы енгізіңіз:",
        "ask_arrival_city": "Ұшып баратын қаланы енгізіңіз:",
        "no_airports_found": "Бұл қалада әуежай табылмады. Басқа қала енгізіңіз.",
        "choose_airport": "Әуежайды таңдаңыз:",
        "ask_date_choice": "Жақын рейстерді көрсету ме әлде күнді енгізесіз бе?",
        "nearest_flights": "Жақын рейстер",
        "enter_date": "Күнді енгізу",
        "ask_date_input": "Күнді енгізіңіз (КК.АА.ЖЖЖЖ):",
        "invalid_date_format": "Күн форматы қате. Қайта енгізіңіз (КК.АА.ЖЖЖЖ).",
        "no_flights_found": "Рейстер табылмады.",
        "flights_found_title": "Қол жетімді рейстер:",
        "flight_line": "{flight} • {departure} → {arrival} • {price}₽",
        "ask_return_date_choice": "Қайту рейстерін көрсету ме әлде күнді енгізесіз бе?",
        "ask_return_date_input": "Қайту күнін енгізіңіз (КК.АА.ЖЖЖЖ):",
        "return_flights_title": "Қайту рейстері:",
        "search_complete": "Рақмет! Тағы бастау үшін /start жіберіңіз.",
    },
    "ky": {
        "start_greeting": "Atlas Travel'ге кош келиңиз!",
        "choose_language": "Кызмат тилин тандаңыз:",
        "language_set": "Тил кыргызчага өзгөрдү.",
        "choose_trip_type": "Кандай каттам издегиңиз келет?",
        "one_way": "Бир тарап",
        "round_trip": "Барып келүү",
        "ask_departure_city": "Учуп чыгуучу шаарды жазыңыз:",
        "ask_arrival_city": "Учуп баруучу шаарды жазыңыз:",
        "no_airports_found": "Бул шаарда аэропорт табылган жок. Башка шаар жазыңыз.",
        "choose_airport": "Аэропортту тандаңыз:",
        "ask_date_choice": "Жакынкы каттамдарды көрсөтөйүнбү же датаны киретесизби?",
        "nearest_flights": "Жакынкы каттамдар",
        "enter_date": "Датаны киргизүү",
        "ask_date_input": "Датаны жазыңыз (КК.АА.ЖЖЖЖ):",
        "invalid_date_format": "Дата форматы туура эмес. Кайрадан жазыңыз (КК.АА.ЖЖЖЖ).",
        "no_flights_found": "Каттамдар табылган жок.",
        "flights_found_title": "Мүмкүн болгон каттамдар:",
        "flight_line": "{flight} • {departure} → {arrival} • {price}₽",
        "ask_return_date_choice": "Кайтуу үчүн жакынкы каттамдарды көрсөтөйүнбү же датаны киретесизби?",
        "ask_return_date_input": "Кайтуу датасын жазыңыз (КК.АА.ЖЖЖЖ):",
        "return_flights_title": "Кайтуу каттамдар:",
        "search_complete": "Рахмат! Кайра баштоо үчүн /start жибериңиз.",
    },
    "en": {
        "start_greeting": "Welcome to Atlas Travel!",
        "choose_language": "Please choose your preferred language:",
        "language_set": "Language set to English.",
        "choose_trip_type": "What type of flight are you looking for?",
        "one_way": "One-way",
        "round_trip": "Round trip",
        "ask_departure_city": "Enter your departure city:",
        "ask_arrival_city": "Enter your destination city:",
        "no_airports_found": "No airports found in that city. Try another one.",
        "choose_airport": "Select an airport:",
        "ask_date_choice": "Show next available flights or enter a specific date?",
        "nearest_flights": "Next flights",
        "enter_date": "Enter date",
        "ask_date_input": "Enter a date (DD.MM.YYYY):",
        "invalid_date_format": "Invalid date format. Please try again (DD.MM.YYYY).",
        "no_flights_found": "No flights found.",
        "flights_found_title": "Available flights:",
        "flight_line": "{flight} • {departure} → {arrival} • {price}₽",
        "ask_return_date_choice": "For the return trip, show next flights or enter a date?",
        "ask_return_date_input": "Enter the return date (DD.MM.YYYY):",
        "return_flights_title": "Return flights:",
        "search_complete": "Thank you! Send /start to search again.",
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    template = TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, key)
    return template.format(**kwargs)


# -------------------- Dataset --------------------
AIRPORTS_BY_CITY: Dict[str, List[Dict[str, str]]] = {
    "москва": [
        {"code": "SVO", "name": "Sheremetyevo"},
        {"code": "DME", "name": "Domodedovo"},
        {"code": "VKO", "name": "Vnukovo"},
    ],
    "moscow": [
        {"code": "SVO", "name": "Sheremetyevo"},
        {"code": "DME", "name": "Domodedovo"},
        {"code": "VKO", "name": "Vnukovo"},
    ],
    "ташкент": [{"code": "TAS", "name": "Tashkent International"}],
    "tashkent": [{"code": "TAS", "name": "Tashkent International"}],
    "алматы": [{"code": "ALA", "name": "Almaty International"}],
    "almaty": [{"code": "ALA", "name": "Almaty International"}],
    "астана": [{"code": "NQZ", "name": "Astana Nursultan Nazarbayev"}],
    "astana": [{"code": "NQZ", "name": "Astana Nursultan Nazarbayev"}],
    "бишкек": [{"code": "FRU", "name": "Bishkek Manas"}],
    "bishkek": [{"code": "FRU", "name": "Bishkek Manas"}],
    "душанбе": [{"code": "DYU", "name": "Dushanbe International"}],
    "dushanbe": [{"code": "DYU", "name": "Dushanbe International"}],
    "самарканд": [{"code": "SKD", "name": "Samarkand International"}],
    "samarkand": [{"code": "SKD", "name": "Samarkand International"}],
}


def generate_sample_flights() -> List[Flight]:
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    flights: List[Flight] = []
    routes = [
        ("SVO", "TAS", "Uzbekistan Airways"),
        ("TAS", "SVO", "Uzbekistan Airways"),
        ("DME", "ALA", "Aeroflot"),
        ("ALA", "DME", "Aeroflot"),
        ("NQZ", "FRU", "Air Astana"),
        ("FRU", "NQZ", "Air Astana"),
        ("VKO", "DYU", "Somon Air"),
        ("DYU", "VKO", "Somon Air"),
        ("TAS", "SKD", "Uzbekistan Airways"),
        ("SKD", "TAS", "Uzbekistan Airways"),
    ]

    for idx, (dep, arr, airline) in enumerate(routes, start=1):
        for offset in range(1, 6):
            departure = now + timedelta(days=offset, hours=idx % 5)
            arrival = departure + timedelta(hours=3)
            flights.append(
                Flight(
                    flight_no=f"{airline.split()[0][:2].upper()}{idx:02d}{offset}",
                    airline=airline,
                    departure_airport=dep,
                    arrival_airport=arr,
                    departure_time=departure,
                    arrival_time=arrival,
                    price=20000 + (idx * 1500) + offset * 500,
                )
            )
    return flights


FLIGHT_SCHEDULE = generate_sample_flights()


TRAVELPAYOUTS_TOKEN = os.getenv("TRAVELPAYOUTS_TOKEN")
TRAVELPAYOUTS_MARKER = os.getenv("TRAVELPAYOUTS_MARKER")
TRAVELPAYOUTS_CURRENCY = os.getenv("TRAVELPAYOUTS_CURRENCY", "rub")
TRAVELPAYOUTS_TIMEOUT = float(os.getenv("TRAVELPAYOUTS_TIMEOUT", "10"))


def parse_iso_datetime(value: Optional[str]) -> datetime:
    if not value:
        raise ValueError("Datetime value is empty")
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


async def fetch_live_flights(
    departure_airport: str,
    arrival_airport: str,
    date: Optional[datetime],
    limit: int,
) -> List[Flight]:
    if not TRAVELPAYOUTS_TOKEN:
        return []

    url = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
    params = {
        "origin": departure_airport,
        "destination": arrival_airport,
        "limit": limit,
        "currency": TRAVELPAYOUTS_CURRENCY,
        "sorting": "price",
        "unique": False,
        "direct": True,
    }

    if TRAVELPAYOUTS_MARKER:
        params["marker"] = TRAVELPAYOUTS_MARKER

    if date is not None:
        params["departure_at"] = date.strftime("%Y-%m-%d")

    headers = {"X-Access-Token": TRAVELPAYOUTS_TOKEN}

    try:
        async with ClientSession(timeout=ClientTimeout(total=TRAVELPAYOUTS_TIMEOUT)) as session:
            async with session.get(url, params=params, headers=headers) as response:
                if response.status != 200:
                    return []
                payload = await response.json()
    except Exception:
        return []

    data = payload.get("data") or []
    flights: List[Flight] = []

    for item in data:
        price = item.get("price")
        departure_at = item.get("departure_at")

        if price is None or departure_at is None:
            continue

        try:
            departure_time = parse_iso_datetime(departure_at)
        except ValueError:
            continue

        arrival_time: datetime
        arrival_at = item.get("return_at")

        if arrival_at:
            try:
                arrival_time = parse_iso_datetime(arrival_at)
            except ValueError:
                arrival_time = departure_time + timedelta(hours=3)
        else:
            duration_minutes = item.get("duration")
            if isinstance(duration_minutes, (int, float)):
                arrival_time = departure_time + timedelta(minutes=duration_minutes)
            else:
                arrival_time = departure_time + timedelta(hours=3)

        airline_code = (item.get("airline") or "").upper()
        airline_name = AIRLINE_NAMES.get(airline_code, airline_code or "Unknown carrier")
        flight_number = item.get("flight_number")
        flight_no = f"{airline_code}{flight_number}" if flight_number else (airline_code or "N/A")

        flights.append(
            Flight(
                flight_no=flight_no,
                airline=airline_name,
                departure_airport=departure_airport,
                arrival_airport=arrival_airport,
                departure_time=departure_time,
                arrival_time=arrival_time,
                price=int(price),
            )
        )

    return flights


def find_airports(city_name: str) -> List[Dict[str, str]]:
    return AIRPORTS_BY_CITY.get(city_name.lower(), [])


async def find_flights(
    departure_airport: str,
    arrival_airport: str,
    date: Optional[datetime] = None,
    limit: int = 5,
) -> List[Flight]:
    live_flights = await fetch_live_flights(departure_airport, arrival_airport, date, limit)
    if live_flights:
        return live_flights[:limit]

    flights = [
        flight
        for flight in FLIGHT_SCHEDULE
        if flight.departure_airport == departure_airport
        and flight.arrival_airport == arrival_airport
        and (date is None or flight.departure_time.date() == date.date())
        and flight.departure_time >= datetime.now()
    ]
    flights.sort(key=lambda f: f.departure_time)
    if date is None:
        return flights[:limit]
    return flights


# -------------------- FSM states --------------------
class LanguageState(StatesGroup):
    choosing = State()


class SearchState(StatesGroup):
    choosing_trip = State()
    entering_departure_city = State()
    choosing_departure_airport = State()
    entering_arrival_city = State()
    choosing_arrival_airport = State()
    choosing_departure_date_action = State()
    entering_departure_date = State()
    choosing_return_date_action = State()
    entering_return_date = State()


# -------------------- Keyboards --------------------
def language_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"lang:{code}")]
        for code, name in LANGUAGES.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def trip_type_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "one_way"), callback_data=f"trip:{TripType.ONE_WAY.value}")],
            [InlineKeyboardButton(text=t(lang, "round_trip"), callback_data=f"trip:{TripType.ROUND_TRIP.value}")],
        ]
    )


def airports_keyboard(airports: List[Dict[str, str]]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"{item['name']} ({item['code']})", callback_data=f"apt:{item['code']}")]
        for item in airports
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def date_choice_keyboard(lang: str, prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "nearest_flights"), callback_data=f"{prefix}:nearest")],
            [InlineKeyboardButton(text=t(lang, "enter_date"), callback_data=f"{prefix}:date")],
        ]
    )


# -------------------- Bot handlers --------------------
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(LanguageState.choosing)
    await message.answer(
        "\n".join([
            TRANSLATIONS["en"]["start_greeting"],
            TRANSLATIONS["ru"]["start_greeting"],
        ]),
        reply_markup=language_keyboard(),
    )


async def choose_language(callback: CallbackQuery, state: FSMContext) -> None:
    lang_code = callback.data.split(":", 1)[1]
    await state.update_data(language=lang_code)
    await callback.message.edit_text(t(lang_code, "language_set"))
    await callback.answer()
    await state.set_state(SearchState.choosing_trip)
    await callback.message.answer(
        t(lang_code, "choose_trip_type"), reply_markup=trip_type_keyboard(lang_code)
    )


async def choose_trip_type(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    trip_type_value = callback.data.split(":", 1)[1]
    trip_type = TripType(trip_type_value)
    await state.update_data(trip_type=trip_type)
    await callback.answer()
    await callback.message.edit_text(t(lang, "choose_trip_type"))
    await callback.message.answer(t(lang, "ask_departure_city"))
    await state.set_state(SearchState.entering_departure_city)


async def ask_departure_airport(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    airports = find_airports(message.text.strip())
    if not airports:
        await message.answer(t(lang, "no_airports_found"))
        return
    await state.update_data(departure_city=message.text.strip(), airports=airports)
    await message.answer(t(lang, "choose_airport"), reply_markup=airports_keyboard(airports))
    await state.set_state(SearchState.choosing_departure_airport)


async def select_departure_airport(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    airport_code = callback.data.split(":", 1)[1]
    await state.update_data(departure_airport=airport_code)
    await callback.answer()
    await callback.message.edit_text(t(lang, "choose_airport"))
    await callback.message.answer(t(lang, "ask_arrival_city"))
    await state.set_state(SearchState.entering_arrival_city)


async def ask_arrival_airport(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    airports = find_airports(message.text.strip())
    if not airports:
        await message.answer(t(lang, "no_airports_found"))
        return
    await state.update_data(arrival_city=message.text.strip(), arrival_airports=airports)
    await message.answer(t(lang, "choose_airport"), reply_markup=airports_keyboard(airports))
    await state.set_state(SearchState.choosing_arrival_airport)


async def select_arrival_airport(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    airport_code = callback.data.split(":", 1)[1]
    await state.update_data(arrival_airport=airport_code)
    await callback.answer()
    await callback.message.edit_text(t(lang, "choose_airport"))
    await callback.message.answer(
        t(lang, "ask_date_choice"),
        reply_markup=date_choice_keyboard(lang, prefix="depdate"),
    )
    await state.set_state(SearchState.choosing_departure_date_action)


async def handle_departure_date_choice(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    action = callback.data.split(":", 1)[1]
    await callback.answer()
    if action == "nearest":
        await present_flights(callback.message, state, is_return=False, date=None)
    else:
        await callback.message.answer(t(lang, "ask_date_input"))
        await state.set_state(SearchState.entering_departure_date)


async def handle_departure_date_input(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    try:
        departure_date = datetime.strptime(message.text.strip(), "%d.%m.%Y")
    except ValueError:
        await message.answer(t(lang, "invalid_date_format"))
        return
    await state.update_data(departure_date=departure_date)
    await present_flights(message, state, is_return=False, date=departure_date)


async def handle_return_date_choice(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    action = callback.data.split(":", 1)[1]
    await callback.answer()
    if action == "nearest":
        await present_flights(callback.message, state, is_return=True, date=None)
    else:
        await callback.message.answer(t(lang, "ask_return_date_input"))
        await state.set_state(SearchState.entering_return_date)


async def handle_return_date_input(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    try:
        return_date = datetime.strptime(message.text.strip(), "%d.%m.%Y")
    except ValueError:
        await message.answer(t(lang, "invalid_date_format"))
        return
    await state.update_data(return_date=return_date)
    await present_flights(message, state, is_return=True, date=return_date)


def format_flight_line(lang: str, flight: Flight) -> str:
    departure_time = flight.departure_time.strftime("%d.%m %H:%M")
    arrival_time = flight.arrival_time.strftime("%d.%m %H:%M")
    return t(
        lang,
        "flight_line",
        flight=f"{flight.flight_no} {flight.airline}",
        departure=f"{flight.departure_airport} {departure_time}",
        arrival=f"{flight.arrival_airport} {arrival_time}",
        price=flight.price,
    )


async def present_flights(
    message_source, state: FSMContext, is_return: bool, date: Optional[datetime]
) -> None:
    data = await state.get_data()
    lang = data.get("language", "en")
    if is_return:
        departure_airport = data.get("arrival_airport")
        arrival_airport = data.get("departure_airport")
    else:
        departure_airport = data.get("departure_airport")
        arrival_airport = data.get("arrival_airport")

    if not departure_airport or not arrival_airport:
        await message_source.answer(t(lang, "no_flights_found"))
        return

    flights = await find_flights(departure_airport, arrival_airport, date=date)

    if not flights:
        await message_source.answer(t(lang, "no_flights_found"))
    else:
        lines = [t(lang, "return_flights_title" if is_return else "flights_found_title")]
        lines.extend(format_flight_line(lang, flight) for flight in flights)
        await message_source.answer("\n".join(lines), parse_mode=ParseMode.HTML)

    trip_type: TripType = data.get("trip_type", TripType.ONE_WAY)
    if trip_type == TripType.ROUND_TRIP and not is_return:
        await state.set_state(SearchState.choosing_return_date_action)
        await message_source.answer(
            t(lang, "ask_return_date_choice"),
            reply_markup=date_choice_keyboard(lang, prefix="retdate"),
        )
    else:
        await message_source.answer(t(lang, "search_complete"))
        await state.clear()


# -------------------- Dispatcher setup --------------------
def register_handlers(dp: Dispatcher) -> None:
    dp.message.register(cmd_start, CommandStart())
    dp.callback_query.register(choose_language, F.data.startswith("lang:"), LanguageState.choosing)
    dp.callback_query.register(
        choose_trip_type, F.data.startswith("trip:"), SearchState.choosing_trip
    )
    dp.message.register(ask_departure_airport, SearchState.entering_departure_city)
    dp.callback_query.register(
        select_departure_airport, F.data.startswith("apt:"), SearchState.choosing_departure_airport
    )
    dp.message.register(ask_arrival_airport, SearchState.entering_arrival_city)
    dp.callback_query.register(
        select_arrival_airport, F.data.startswith("apt:"), SearchState.choosing_arrival_airport
    )
    dp.callback_query.register(
        handle_departure_date_choice,
        F.data.startswith("depdate:"),
        SearchState.choosing_departure_date_action,
    )
    dp.message.register(handle_departure_date_input, SearchState.entering_departure_date)
    dp.callback_query.register(
        handle_return_date_choice,
        F.data.startswith("retdate:"),
        SearchState.choosing_return_date_action,
    )
    dp.message.register(handle_return_date_input, SearchState.entering_return_date)


async def main() -> None:
    bot_token = "8396669139:AAFvr8gWi7uXDMwPLBePF9NmYf16wsHmtPU"
    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    register_handlers(dp)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())