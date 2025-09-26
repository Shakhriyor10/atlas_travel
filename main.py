"""Atlas Travel Telegram bot.

This module provides a multi-language Telegram bot that lets users search for
flight itineraries via an external flights API. The bot guides the user through
language selection, origin and destination input, date selection, and displays
the closest flight options returned by the API.

Environment variables:
    TELEGRAM_BOT_TOKEN: Token obtained from BotFather to run the Telegram bot.
    TEQUILA_API_KEY: Kiwi.com (Tequila) API key used to query flight offers.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# Enable logging so we can trace the bot's behaviour when running on a server.
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
LOGGER = logging.getLogger(__name__)

# Conversation states
CHOOSING_LANGUAGE, ORIGIN, DESTINATION, DATE = range(4)


@dataclass
class Flight:
    """Represents a single flight itinerary returned from the API."""

    airline: str
    flight_number: str
    departure_airport: str
    arrival_airport: str
    departure_time: datetime
    arrival_time: datetime
    price: float
    currency: str

    def format_for_user(self, language: str) -> str:
        """Return a human-readable message for the user."""

        # Localised message fragments.
        templates = {
            "ru": "Авиакомпания {airline} {flight_number}\nВылет: {dep_airport} {dep_time}\nПрилет: {arr_airport} {arr_time}\nЦена: {price} {currency}",
            "uz": "Aviakompaniya {airline} {flight_number}\nJo'nash: {dep_airport} {dep_time}\nYetib kelish: {arr_airport} {arr_time}\nNarxi: {price} {currency}",
            "tg": "Ширкати ҳавопаймоии {airline} {flight_number}\nПарвоз: {dep_airport} {dep_time}\nФуруд: {arr_airport} {arr_time}\nНарх: {price} {currency}",
            "kk": "Әуе компаниясы {airline} {flight_number}\nҰшу: {dep_airport} {dep_time}\nҚону: {arr_airport} {arr_time}\nБағасы: {price} {currency}",
            "ky": "Авиакомпания {airline} {flight_number}\nУчуу: {dep_airport} {dep_time}\nКонуу: {arr_airport} {arr_time}\nБаасы: {price} {currency}",
            "en": "Airline {airline} {flight_number}\nDeparture: {dep_airport} {dep_time}\nArrival: {arr_airport} {arr_time}\nPrice: {price} {currency}",
        }
        template = templates.get(language, templates["en"])
        return template.format(
            airline=self.airline,
            flight_number=self.flight_number,
            dep_airport=self.departure_airport,
            arr_airport=self.arrival_airport,
            dep_time=self.departure_time.strftime("%d.%m.%Y %H:%M"),
            arr_time=self.arrival_time.strftime("%d.%m.%Y %H:%M"),
            price=f"{self.price:.2f}",
            currency=self.currency,
        )


class FlightAPIError(Exception):
    """Raised when the flight API returns an error or invalid response."""


class FlightAPIClient:
    """Client wrapper for the Kiwi.com (Tequila) flights API."""

    BASE_URL = "https://api.tequila.kiwi.com/v2/search"

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise FlightAPIError("Missing Kiwi.com API key")
        self.api_key = api_key

    def search_flights(
        self, origin: str, destination: str, date: datetime
    ) -> List[Flight]:
        """Search for flights around the specified date.

        The API is queried with a +/- 3 day window to provide nearby flights.
        """

        date_from = (date - timedelta(days=3)).strftime("%d/%m/%Y")
        date_to = (date + timedelta(days=3)).strftime("%d/%m/%Y")

        params = {
            "fly_from": origin,
            "fly_to": destination,
            "date_from": date_from,
            "date_to": date_to,
            "curr": "USD",
            "limit": 5,
            "sort": "price",
        }

        headers = {"apikey": self.api_key}
        response = requests.get(self.BASE_URL, params=params, headers=headers, timeout=20)

        if response.status_code != 200:
            LOGGER.error("Flight API error: %s", response.text)
            raise FlightAPIError(f"Flight API error: {response.status_code}")

        data = response.json()
        if "data" not in data:
            raise FlightAPIError("Unexpected API response format")

        flights: List[Flight] = []
        for item in data["data"]:
            try:
                flights.append(
                    Flight(
                        airline=item["airlines"][0] if item.get("airlines") else "?",
                        flight_number=item.get("route", [{}])[0].get("flight_no", "?"),
                        departure_airport=item.get("flyFrom", ""),
                        arrival_airport=item.get("flyTo", ""),
                        departure_time=datetime.fromtimestamp(item["dTimeUTC"]),
                        arrival_time=datetime.fromtimestamp(item["aTimeUTC"]),
                        price=float(item.get("price", 0.0)),
                        currency=data.get("currency", "USD"),
                    )
                )
            except (KeyError, TypeError, ValueError) as error:
                LOGGER.warning("Skipping flight due to malformed data: %s", error)
                continue
        return flights


LANGUAGE_PACK: Dict[str, Dict[str, str]] = {
    "ru": {
        "label": "🇷🇺 Русский",
        "choose_language": "Выберите язык",
        "ask_origin": "Введите город или аэропорт отправления (например, MOW или Москва)",
        "ask_destination": "Введите город или аэропорт прибытия (например, TSE или Астана)",
        "ask_date": "Введите дату вылета в формате ДД.ММ.ГГГГ",
        "invalid_date": "Неверный формат даты. Попробуйте снова (ДД.ММ.ГГГГ)",
        "searching": "Ищу ближайшие рейсы...",
        "no_flights": "Рейсы не найдены. Попробуйте другую дату или направление.",
        "api_key_missing": "API ключ не настроен. Обратитесь к администратору.",
        "error": "Произошла ошибка при поиске рейсов. Попробуйте позже.",
        "cancelled": "Поиск отменён. Напишите /start чтобы начать заново.",
    },
    "uz": {
        "label": "🇺🇿 O'zbekcha",
        "choose_language": "Tilni tanlang",
        "ask_origin": "Jo'nash shahri yoki aeroportini kiriting (masalan, TAS yoki Toshkent)",
        "ask_destination": "Borish shahri yoki aeroportini kiriting (masalan, DXB yoki Dubay)",
        "ask_date": "Parvoz sanasini DD.MM.YYYY shaklida kiriting",
        "invalid_date": "Sana formati noto'g'ri. Iltimos, DD.MM.YYYY ko'rinishida kiriting",
        "searching": "Yaqin parvozlar qidirilmoqda...",
        "no_flights": "Parvozlar topilmadi. Boshqa sanani yoki yo'nalishni sinab ko'ring.",
        "api_key_missing": "API kaliti sozlanmagan. Administrator bilan bog'laning.",
        "error": "Parvozlarni qidirishda xatolik yuz berdi. Keyinroq urinib ko'ring.",
        "cancelled": "Qidiruv bekor qilindi. Qayta boshlash uchun /start yozing.",
    },
    "tg": {
        "label": "🇹🇯 Тоҷикӣ",
        "choose_language": "Забонро интихоб кунед",
        "ask_origin": "Шаҳр ё фурудгоҳи парвозро ворид кунед (масалан, DYU ё Душанбе)",
        "ask_destination": "Шаҳр ё фурудгоҳи нишастро ворид кунед (масалан, IST ё Истанбул)",
        "ask_date": "Санаи парвозро бо формати РР.ММ.СССС ворид кунед",
        "invalid_date": "Сана нодуруст аст. Марҳамат карда, РР.ММ.СССС-ро ворид кунед",
        "searching": "Парвозҳои наздик ҷустуҷӯ мешаванд...",
        "no_flights": "Парвоз ёфт нашуд. Сана ё самти дигарро санҷед.",
        "api_key_missing": "Калиди API танзим нашудааст. Лутфан ба администратор муроҷиат кунед.",
        "error": "Ҳангоми ҷустуҷӯи парвозҳо хато шуд. Баъдтар кӯшиш кунед.",
        "cancelled": "Ҷустуҷӯ бекор карда шуд. Барои аз нав оғоз кардан /start нависед.",
    },
    "kk": {
        "label": "🇰🇿 Қазақша",
        "choose_language": "Тілді таңдаңыз",
        "ask_origin": "Ұшу қаласын немесе әуежайын енгізіңіз (мысалы, ALA немесе Алматы)",
        "ask_destination": "Қону қаласын немесе әуежайын енгізіңіз (мысалы, NQZ немесе Астана)",
        "ask_date": "Ұшу күнін КК.АА.ЖЖЖЖ форматында енгізіңіз",
        "invalid_date": "Күн форматы қате. Қайтадан КК.АА.ЖЖЖЖ енгізіңіз",
        "searching": "Жақын рейстер ізделуде...",
        "no_flights": "Рейстер табылмады. Басқа күнді немесе бағытты көріңіз.",
        "api_key_missing": "API кілті бапталмаған. Әкімшіге хабарласыңыз.",
        "error": "Рейстерді іздеу кезінде қате кетті. Кейінірек қайталап көріңіз.",
        "cancelled": "Іздеу тоқтатылды. Қайта бастау үшін /start жазыңыз.",
    },
    "ky": {
        "label": "🇰🇬 Кыргызча",
        "choose_language": "Тилди тандаңыз",
        "ask_origin": "Учуп чыгуучу шаарды же аэропортту жазыңыз (мисалы, FRU же Бишкек)",
        "ask_destination": "Учуп бара турган шаарды же аэропортту жазыңыз (мисалы, OSS же Ош)",
        "ask_date": "Учуу күнүн КК.АА.ЖЖЖЖ форматында жазыңыз",
        "invalid_date": "Күн форматы туура эмес. Кайрадан КК.АА.ЖЖЖЖ жазыңыз",
        "searching": "Жакынкы рейстер издөөдө...",
        "no_flights": "Рейстер табылган жок. Башка күн же багытты тандаңыз.",
        "api_key_missing": "API ачкычы орнотулган эмес. Администраторго кайрылыңыз.",
        "error": "Рейстерди издөөдө ката кетти. Кийинчерээк аракет кылыңыз.",
        "cancelled": "Издөө токтотулду. Кайра баштоо үчүн /start жазыңыз.",
    },
    "en": {
        "label": "🇬🇧 English",
        "choose_language": "Choose your language",
        "ask_origin": "Enter departure city or airport (e.g. NYC or New York)",
        "ask_destination": "Enter arrival city or airport (e.g. LON or London)",
        "ask_date": "Enter departure date in DD.MM.YYYY format",
        "invalid_date": "Invalid date format. Please use DD.MM.YYYY",
        "searching": "Searching for the nearest flights...",
        "no_flights": "No flights found. Try a different date or route.",
        "api_key_missing": "API key is not configured. Please contact the administrator.",
        "error": "An error occurred while searching for flights. Please try again later.",
        "cancelled": "Search cancelled. Type /start to begin again.",
    },
}


def get_text(language: str, key: str) -> str:
    """Return the text for a given language and key with English fallback."""

    language_pack = LANGUAGE_PACK.get(language)
    if language_pack and key in language_pack:
        return language_pack[key]
    return LANGUAGE_PACK["en"].get(key, "")


def build_language_keyboard() -> InlineKeyboardMarkup:
    """Create an inline keyboard for language selection."""

    buttons = [
        [InlineKeyboardButton(pack["label"], callback_data=code)]
        for code, pack in LANGUAGE_PACK.items()
    ]
    return InlineKeyboardMarkup(buttons)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the /start command by asking the user to select a language."""

    keyboard = build_language_keyboard()
    if update.message:
        await update.message.reply_text(
            get_text("en", "choose_language"), reply_markup=keyboard
        )
    else:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            get_text("en", "choose_language"), reply_markup=keyboard
        )
    return CHOOSING_LANGUAGE


async def language_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Callback after the user picks a language."""

    query = update.callback_query
    await query.answer()

    language = query.data
    context.user_data["language"] = language

    await query.edit_message_text(get_text(language, "ask_origin"))
    return ORIGIN


async def handle_origin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the origin provided by the user and ask for the destination."""

    language = context.user_data.get("language", "en")
    context.user_data["origin"] = update.message.text.strip()
    await update.message.reply_text(get_text(language, "ask_destination"))
    return DESTINATION


async def handle_destination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the destination and ask for the travel date."""

    language = context.user_data.get("language", "en")
    context.user_data["destination"] = update.message.text.strip()
    await update.message.reply_text(get_text(language, "ask_date"))
    return DATE


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse a date in DD.MM.YYYY format."""

    try:
        return datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        return None


async def handle_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Validate the date, query the API and display flight options."""

    language = context.user_data.get("language", "en")
    date_text = update.message.text.strip()
    travel_date = parse_date(date_text)

    if travel_date is None:
        await update.message.reply_text(get_text(language, "invalid_date"))
        return DATE

    origin = context.user_data.get("origin")
    destination = context.user_data.get("destination")

    api_key = os.getenv("TEQUILA_API_KEY")
    if not api_key:
        await update.message.reply_text(get_text(language, "api_key_missing"))
        return ConversationHandler.END

    await update.message.reply_text(get_text(language, "searching"))

    try:
        client = FlightAPIClient(api_key)
        flights = client.search_flights(origin, destination, travel_date)
    except FlightAPIError:
        LOGGER.exception("Failed to retrieve flights")
        await update.message.reply_text(get_text(language, "error"))
        return ConversationHandler.END

    if not flights:
        await update.message.reply_text(get_text(language, "no_flights"))
        return ConversationHandler.END

    for flight in flights:
        await update.message.reply_text(flight.format_for_user(language))

    await update.message.reply_text(get_text(language, "cancelled"))
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Allow the user to cancel the conversation."""

    language = context.user_data.get("language", "en")
    if update.message:
        await update.message.reply_text(get_text(language, "cancelled"))
    return ConversationHandler.END


def build_application() -> Application:
    """Create the Telegram application with handlers."""

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is required")

    application = Application.builder().token(token).build()

    conversation = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_LANGUAGE: [CallbackQueryHandler(language_selected)],
            ORIGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_origin)],
            DESTINATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_destination)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="flight_search_conversation",
        persistent=False,
    )

    application.add_handler(conversation)
    return application


def main() -> None:
    """Entrypoint for running the Telegram bot."""

    application = build_application()
    LOGGER.info("Starting Atlas Travel bot")
    application.run_polling()


if __name__ == "__main__":
    main()
