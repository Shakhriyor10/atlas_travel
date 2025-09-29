import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message


logging.basicConfig(level=logging.INFO)

def get_env_variable(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} must be set")
    return value


class FlightSearchStates(StatesGroup):
    waiting_for_language = State()
    waiting_for_origin = State()
    waiting_for_destination = State()
    waiting_for_date = State()


LANGUAGES = {
    "ru": {
        "name": "🇷🇺 Русский",
        "messages": {
            "start": "Выберите язык обслуживания:",
            "ask_origin": "Введите город или IATA-код вылета (например, Tashkent или TAS):",
            "ask_destination": "Введите город или IATA-код прилёта:",
            "ask_date": (
                "Введите дату вылета в формате YYYY-MM-DD или отправьте '-' чтобы использовать сегодняшнюю дату:"
            ),
            "invalid_date": "Пожалуйста, введите дату в формате YYYY-MM-DD или '-'.",
            "searching": "Ищу ближайшие рейсы...",
            "no_flights": "Рейсов не найдено.",
            "flight": (
                "✈️ {flight_number} ({airline})\n"
                "📍 {departure_airport} ➡️ {arrival_airport}\n"
                "🕒 Вылет: {departure_time}\n"
                "🕒 Прилёт: {arrival_time}"
            ),
            "error": "Произошла ошибка при поиске рейсов. Попробуйте позже.",
        },
    },
    "uz": {
        "name": "🇺🇿 Ўзбекча",
        "messages": {
            "start": "Хизмат тилини танланг:",
            "ask_origin": "Учиш шаҳри ёки IATA-кодини киритинг (масалан, Tashkent ёки TAS):",
            "ask_destination": "Қўниш шаҳри ёки IATA-кодини киритинг:",
            "ask_date": "Санани YYYY-MM-DD форматида киритинг ёки '-' юборинг:",
            "invalid_date": "Илтимос, YYYY-MM-DD форматидаги санани ёки '-' юборинг.",
            "searching": "Рейслар қидирилмоқда...",
            "no_flights": "Рейс топилмади.",
            "flight": (
                "✈️ {flight_number} ({airline})\n"
                "📍 {departure_airport} ➡️ {arrival_airport}\n"
                "🕒 Учиш: {departure_time}\n"
                "🕒 Қўниш: {arrival_time}"
            ),
            "error": "Рейсларни излашда хатолик юз берди. Кейинроқ уриниб кўринг.",
        },
    },
    "tg": {
        "name": "🇹🇯 Тоҷикӣ",
        "messages": {
            "start": "Лутфан забони хизматро интихоб кунед:",
            "ask_origin": "Шаҳри парвоз ё IATA-кодро ворид кунед (масалан, Dushanbe ё DYU):",
            "ask_destination": "Шаҳри фуруд ё IATA-кодро ворид кунед:",
            "ask_date": "Санаро дар формати YYYY-MM-DD ворид кунед ё '-' фиристед:",
            "invalid_date": "Лутфан санаи дуруст ё '-' фиристед.",
            "searching": "Парвозҳо ҷустуҷӯ мешаванд...",
            "no_flights": "Ҳеҷ парвози мувофиқ ёфт нашуд.",
            "flight": (
                "✈️ {flight_number} ({airline})\n"
                "📍 {departure_airport} ➡️ {arrival_airport}\n"
                "🕒 Парвоз: {departure_time}\n"
                "🕒 Фуруд: {arrival_time}"
            ),
            "error": "Ҳангоми ҷустуҷӯи парвозҳо хато рух дод. Баъдтар кӯшиш кунед.",
        },
    },
    "kk": {
        "name": "🇰🇿 Қазақша",
        "messages": {
            "start": "Қызмет тілін таңдаңыз:",
            "ask_origin": "Ұшатын қаланы немесе IATA-кодты енгізіңіз (мысалы, Almaty немесе ALA):",
            "ask_destination": "Қонатын қаланы немесе IATA-кодты енгізіңіз:",
            "ask_date": "Күнді YYYY-MM-DD форматында енгізіңіз немесе '-' жіберіңіз:",
            "invalid_date": "Күнді YYYY-MM-DD форматында енгізіңіз немесе '-'.",
            "searching": "Рейстер ізделуде...",
            "no_flights": "Рейстер табылмады.",
            "flight": (
                "✈️ {flight_number} ({airline})\n"
                "📍 {departure_airport} ➡️ {arrival_airport}\n"
                "🕒 Ұшу: {departure_time}\n"
                "🕒 Қону: {arrival_time}"
            ),
            "error": "Рейстерді іздеу кезінде қате пайда болды. Кейінірек көріңіз.",
        },
    },
    "kg": {
        "name": "🇰🇬 Кыргызча",
        "messages": {
            "start": "Тилди тандаңыз:",
            "ask_origin": "Учуп чыгуу шаарын же IATA-кодду киргизиңиз (мисалы, Bishkek же FRU):",
            "ask_destination": "Конуу шаарын же IATA-кодду киргизиңиз:",
            "ask_date": "Датаны YYYY-MM-DD форматында киргизиңиз же '-' жибериңиз:",
            "invalid_date": "Сураныч, датаны YYYY-MM-DD форматында же '-' жибериңиз.",
            "searching": "Рейстер изденүүдө...",
            "no_flights": "Рейстер табылган жок.",
            "flight": (
                "✈️ {flight_number} ({airline})\n"
                "📍 {departure_airport} ➡️ {arrival_airport}\n"
                "🕒 Учуу: {departure_time}\n"
                "🕒 Конуу: {arrival_time}"
            ),
            "error": "Рейстерди издөөдө ката кетти. Кийинчерээк аракет кылыңыз.",
        },
    },
    "en": {
        "name": "🇬🇧 English",
        "messages": {
            "start": "Please choose your language:",
            "ask_origin": "Enter the departure city or IATA code (e.g., Tashkent or TAS):",
            "ask_destination": "Enter the arrival city or IATA code:",
            "ask_date": "Enter the departure date in YYYY-MM-DD or send '-' for today:",
            "invalid_date": "Please provide a valid date in YYYY-MM-DD or '-'.",
            "searching": "Searching for flights...",
            "no_flights": "No flights found.",
            "flight": (
                "✈️ {flight_number} ({airline})\n"
                "📍 {departure_airport} ➡️ {arrival_airport}\n"
                "🕒 Departure: {departure_time}\n"
                "🕒 Arrival: {arrival_time}"
            ),
            "error": "An error occurred while searching for flights. Try again later.",
        },
    },
}


LANGUAGE_BUTTONS = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text=data["name"], callback_data=code)]
        for code, data in LANGUAGES.items()
    ]
)


def get_message(language: str, key: str) -> str:
    return LANGUAGES.get(language, LANGUAGES["en"])["messages"][key]


async def fetch_flights(
    session: aiohttp.ClientSession,
    origin: str,
    destination: str,
    date: str,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    access_key = get_env_variable("AVIATIONSTACK_KEY")
    url = "http://api.aviationstack.com/v1/flights"
    def build_location_params(prefix: str, value: str) -> Dict[str, str]:
        cleaned = value.strip()
        params: Dict[str, str] = {}
        if cleaned:
            title_case = cleaned.title()
            params[f"{prefix}_city"] = title_case
            if len(cleaned) == 3 and cleaned.isalpha():
                params[f"{prefix}_iata"] = cleaned.upper()
        return params

    params: Dict[str, Any] = {
        "access_key": access_key,
        "flight_date": date,
        "limit": limit,
    }
    params.update(build_location_params("dep", origin))
    params.update(build_location_params("arr", destination))
    async with session.get(url, params=params, timeout=30) as response:
        response.raise_for_status()
        payload = await response.json()
        return payload.get("data", [])


def format_time(time_str: Optional[str]) -> str:
    if not time_str:
        return "-"
    try:
        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return time_str


async def handle_flight_search(
    message: Message,
    state: FSMContext,
    language: str,
    origin: str,
    destination: str,
    date: str,
) -> None:
    await message.answer(get_message(language, "searching"))
    try:
        async with aiohttp.ClientSession() as session:
            flights = await fetch_flights(session, origin, destination, date)
    except Exception as exc:  # noqa: BLE001
        logging.exception("Failed to fetch flights: %s", exc)
        await message.answer(get_message(language, "error"))
        await state.clear()
        return

    if not flights:
        await message.answer(get_message(language, "no_flights"))
        await state.clear()
        return

    for flight in flights:
        airline = (flight.get("airline") or {}).get("name", "-")
        flight_number = (flight.get("flight") or {}).get("number", "-")
        departure = flight.get("departure") or {}
        arrival = flight.get("arrival") or {}
        text = get_message(language, "flight").format(
            flight_number=flight_number,
            airline=airline,
            departure_airport=departure.get("airport", "-"),
            arrival_airport=arrival.get("airport", "-"),
            departure_time=format_time(departure.get("scheduled")),
            arrival_time=format_time(arrival.get("scheduled")),
        )
        await message.answer(text)

    await state.clear()


async def main() -> None:
    token = get_env_variable("BOT_TOKEN")
    bot = Bot(token=token, parse_mode="HTML")
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext) -> None:  # noqa: WPS430
        await state.set_state(FlightSearchStates.waiting_for_language)
        language_list = "\n".join(data["name"] for data in LANGUAGES.values())
        await message.answer(
            f"🌐\n{language_list}\n\nPlease choose your language:",
            reply_markup=LANGUAGE_BUTTONS,
        )

    @dp.callback_query(StateFilter(FlightSearchStates.waiting_for_language))
    async def select_language(callback: CallbackQuery, state: FSMContext) -> None:  # noqa: WPS430
        language_code = callback.data
        if language_code not in LANGUAGES:
            await callback.answer()
            return
        await state.update_data(language=language_code)
        await state.set_state(FlightSearchStates.waiting_for_origin)
        await callback.message.answer(get_message(language_code, "ask_origin"))
        await callback.answer()

    @dp.message(StateFilter(FlightSearchStates.waiting_for_origin))
    async def process_origin(message: Message, state: FSMContext) -> None:  # noqa: WPS430
        data = await state.get_data()
        language = data.get("language", "en")
        origin = message.text.strip()
        if not origin:
            await message.answer(get_message(language, "ask_origin"))
            return
        await state.update_data(origin=origin)
        await state.set_state(FlightSearchStates.waiting_for_destination)
        await message.answer(get_message(language, "ask_destination"))

    @dp.message(StateFilter(FlightSearchStates.waiting_for_destination))
    async def process_destination(message: Message, state: FSMContext) -> None:  # noqa: WPS430
        data = await state.get_data()
        language = data.get("language", "en")
        destination = message.text.strip()
        if not destination:
            await message.answer(get_message(language, "ask_destination"))
            return
        await state.update_data(destination=destination)
        await state.set_state(FlightSearchStates.waiting_for_date)
        await message.answer(get_message(language, "ask_date"))

    @dp.message(StateFilter(FlightSearchStates.waiting_for_date))
    async def process_date(message: Message, state: FSMContext) -> None:  # noqa: WPS430
        data = await state.get_data()
        language = data.get("language", "en")
        text = message.text.strip()
        if text == "-":
            date_str = datetime.utcnow().strftime("%Y-%m-%d")
        else:
            try:
                date = datetime.strptime(text, "%Y-%m-%d")
                date_str = date.strftime("%Y-%m-%d")
            except ValueError:
                await message.answer(get_message(language, "invalid_date"))
                return

        origin = data.get("origin")
        destination = data.get("destination")
        await handle_flight_search(message, state, language, origin, destination, date_str)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
