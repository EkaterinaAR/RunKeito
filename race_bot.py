import logging
import os
import re
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.race")
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN_RACE") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_TOKEN_HERE":
    raise RuntimeError("BOT_TOKEN не задан. Создай файл .env и вставь токен от @BotFather.")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


@dataclass(frozen=True)
class Race:
    name: str
    country: str
    city: str
    race_date: date
    distance_type: str  # marathon | half


RACES: List[Race] = [
    Race("Paris Marathon", "Франция", "Париж", date(2026, 4, 12), "marathon"),
    Race("Madrid Rock'n'Roll Marathon", "Испания", "Мадрид", date(2026, 4, 26), "marathon"),
    Race("Prague Half Marathon", "Чехия", "Прага", date(2026, 4, 4), "half"),
    Race("Berlin Half Marathon", "Германия", "Берлин", date(2026, 4, 5), "half"),
    Race("Copenhagen Marathon", "Дания", "Копенгаген", date(2026, 5, 10), "marathon"),
    Race("Riga Marathon", "Латвия", "Рига", date(2026, 5, 17), "marathon"),
    Race("Riga Half Marathon", "Латвия", "Рига", date(2026, 5, 17), "half"),
    Race("Stockholm Marathon", "Швеция", "Стокгольм", date(2026, 6, 6), "marathon"),
    Race("Gold Coast Marathon", "Австралия", "Голд-Кост", date(2026, 7, 5), "marathon"),
    Race("Tallinn Marathon", "Эстония", "Таллин", date(2026, 9, 13), "marathon"),
    Race("Tallinn Half Marathon", "Эстония", "Таллин", date(2026, 9, 13), "half"),
    Race("Berlin Marathon", "Германия", "Берлин", date(2026, 9, 27), "marathon"),
    Race("Lisbon Half Marathon", "Португалия", "Лиссабон", date(2026, 10, 11), "half"),
    Race("Chicago Marathon", "США", "Чикаго", date(2026, 10, 11), "marathon"),
    Race("Valencia Half Marathon", "Испания", "Валенсия", date(2026, 10, 25), "half"),
    Race("Athens Marathon", "Греция", "Афины", date(2026, 11, 8), "marathon"),
    Race("Valencia Marathon", "Испания", "Валенсия", date(2026, 12, 6), "marathon"),
    Race("Dubai Marathon", "ОАЭ", "Дубай", date(2027, 1, 24), "marathon"),
    Race("Rome Marathon", "Италия", "Рим", date(2027, 3, 21), "marathon"),
    Race("Rome Half Marathon", "Италия", "Рим", date(2027, 3, 21), "half"),
]

MONTHS_RU = {
    "январь": 1,
    "января": 1,
    "февраль": 2,
    "февраля": 2,
    "март": 3,
    "марта": 3,
    "апрель": 4,
    "апреля": 4,
    "май": 5,
    "мая": 5,
    "июнь": 6,
    "июня": 6,
    "июль": 7,
    "июля": 7,
    "август": 8,
    "августа": 8,
    "сентябрь": 9,
    "сентября": 9,
    "октябрь": 10,
    "октября": 10,
    "ноябрь": 11,
    "ноября": 11,
    "декабрь": 12,
    "декабря": 12,
}

menu_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
menu_keyboard.add(KeyboardButton("Найти забеги"), KeyboardButton("Помощь"))

cancel_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
cancel_keyboard.add(KeyboardButton("Отмена"))

distance_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
distance_keyboard.add(KeyboardButton("Марафон"), KeyboardButton("Полумарафон"))
distance_keyboard.add(KeyboardButton("Любая"), KeyboardButton("Пропустить"))
distance_keyboard.add(KeyboardButton("Отмена"))

country_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
country_keyboard.add(KeyboardButton("Пропустить"), KeyboardButton("Отмена"))

month_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
month_keyboard.add(KeyboardButton("Пропустить"), KeyboardButton("Отмена"))


class RaceSearchStates(StatesGroup):
    waiting_distance = State()
    waiting_country = State()
    waiting_month_year = State()


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def parse_month_year(raw: str) -> Optional[Tuple[int, int]]:
    text = normalize_text(raw).replace(",", " ")

    dotted = re.fullmatch(r"(0?[1-9]|1[0-2])[./-](\d{4})", text)
    if dotted:
        return int(dotted.group(1)), int(dotted.group(2))

    iso = re.fullmatch(r"(\d{4})[./-](0?[1-9]|1[0-2])", text)
    if iso:
        return int(iso.group(2)), int(iso.group(1))

    words = text.split()
    if len(words) == 2:
        if words[0].isdigit() and words[1].isdigit():
            month = int(words[0])
            year = int(words[1])
            if 1 <= month <= 12 and 1900 <= year <= 2100:
                return month, year

        month_word = MONTHS_RU.get(words[0])
        if month_word and words[1].isdigit():
            year = int(words[1])
            if 1900 <= year <= 2100:
                return month_word, year

    return None


def country_matches(user_country: str, race_country: str) -> bool:
    user_norm = normalize_text(user_country)
    race_norm = normalize_text(race_country)
    return user_norm == race_norm or user_norm in race_norm or race_norm in user_norm


def find_races(
    distance_filter: Optional[str],
    country_filter: Optional[str],
    month_year_filter: Optional[Tuple[int, int]],
) -> List[Race]:
    today = date.today()
    results = [race for race in RACES if race.race_date >= today]

    if distance_filter and distance_filter != "any":
        results = [race for race in results if race.distance_type == distance_filter]

    if country_filter:
        results = [race for race in results if country_matches(country_filter, race.country)]

    if month_year_filter:
        month, year = month_year_filter
        results = [
            race
            for race in results
            if race.race_date.month == month and race.race_date.year == year
        ]

    results.sort(key=lambda race: race.race_date)
    return results


@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message) -> None:
    await message.answer(
        "Привет! Я помогу найти ближайшие забеги.\n\n"
        "Параметры поиска:\n"
        "1) дистанция: марафон / полумарафон / любая\n"
        "2) страна\n"
        "3) месяц и год\n\n"
        "Важно: нужно задать минимум 2 параметра из 3.",
        reply_markup=menu_keyboard,
    )


@dp.message_handler(commands=["help"])
@dp.message_handler(lambda m: m.text == "Помощь")
async def cmd_help(message: types.Message) -> None:
    await message.answer(
        "Как пользоваться:\n"
        "1) Нажми 'Найти забеги'\n"
        "2) Выбери дистанцию\n"
        "3) Введи страну (или 'Пропустить')\n"
        "4) Введи месяц и год (или 'Пропустить')\n\n"
        "Форматы месяца и года:\n"
        "- 04.2026\n"
        "- 2026-04\n"
        "- апрель 2026\n\n"
        "Минимум 2 параметра должны быть заданы.",
        reply_markup=menu_keyboard,
    )


@dp.message_handler(lambda m: m.text == "Найти забеги")
async def start_search(message: types.Message, state: FSMContext) -> None:
    await state.finish()
    await RaceSearchStates.waiting_distance.set()
    await message.answer(
        "Шаг 1/3. Выбери дистанцию:",
        reply_markup=distance_keyboard,
    )


@dp.message_handler(lambda m: m.text == "Отмена", state="*")
async def cancel_state(message: types.Message, state: FSMContext) -> None:
    if await state.get_state() is not None:
        await state.finish()
        await message.answer("Поиск отменен.", reply_markup=menu_keyboard)
    else:
        await message.answer("Сейчас нет активного поиска.", reply_markup=menu_keyboard)


@dp.message_handler(state=RaceSearchStates.waiting_distance, content_types=types.ContentType.TEXT)
async def handle_distance(message: types.Message, state: FSMContext) -> None:
    mapping = {
        "марафон": "marathon",
        "полумарафон": "half",
        "любая": "any",
        "пропустить": None,
    }
    value = normalize_text(message.text)

    if value not in mapping:
        await message.answer(
            "Выбери один из вариантов: Марафон / Полумарафон / Любая / Пропустить.",
            reply_markup=distance_keyboard,
        )
        return

    await state.update_data(distance_filter=mapping[value])
    await RaceSearchStates.waiting_country.set()
    await message.answer(
        "Шаг 2/3. Введи страну (например: Испания, Германия, США) или нажми 'Пропустить'.",
        reply_markup=country_keyboard,
    )


@dp.message_handler(state=RaceSearchStates.waiting_country, content_types=types.ContentType.TEXT)
async def handle_country(message: types.Message, state: FSMContext) -> None:
    value = normalize_text(message.text)
    country_filter = None if value == "пропустить" else message.text.strip()

    if country_filter is not None and len(country_filter) < 2:
        await message.answer(
            "Слишком короткое название страны. Введи страну полностью или нажми 'Пропустить'.",
            reply_markup=country_keyboard,
        )
        return

    await state.update_data(country_filter=country_filter)
    await RaceSearchStates.waiting_month_year.set()
    await message.answer(
        "Шаг 3/3. Введи месяц и год (например: 04.2026 или апрель 2026) или нажми 'Пропустить'.",
        reply_markup=month_keyboard,
    )


@dp.message_handler(state=RaceSearchStates.waiting_month_year, content_types=types.ContentType.TEXT)
async def handle_month_year(message: types.Message, state: FSMContext) -> None:
    value = normalize_text(message.text)
    month_year_filter = None

    if value != "пропустить":
        month_year_filter = parse_month_year(value)
        if month_year_filter is None:
            await message.answer(
                "Не смогла распознать месяц/год. Примеры: 04.2026, 2026-04, апрель 2026.",
                reply_markup=month_keyboard,
            )
            return

    await state.update_data(month_year_filter=month_year_filter)
    data = await state.get_data()

    selected_filters = sum(
        [
            data.get("distance_filter") is not None,
            data.get("country_filter") is not None,
            data.get("month_year_filter") is not None,
        ]
    )

    if selected_filters < 2:
        await state.finish()
        await message.answer(
            "Нужно указать минимум 2 параметра из 3. Запусти поиск заново кнопкой 'Найти забеги'.",
            reply_markup=menu_keyboard,
        )
        return

    races = find_races(
        distance_filter=data.get("distance_filter"),
        country_filter=data.get("country_filter"),
        month_year_filter=data.get("month_year_filter"),
    )

    await state.finish()

    if not races:
        await message.answer(
            "По таким параметрам ничего не найдено в текущем каталоге забегов.",
            reply_markup=menu_keyboard,
        )
        return

    lines = ["Ближайшие забеги:"]
    for race in races[:10]:
        lines.append(
            f"{race.name} / {race.country} / {race.city} / {race.race_date.strftime('%d.%m.%Y')}"
        )

    await message.answer("\n".join(lines), reply_markup=menu_keyboard)


@dp.message_handler(content_types=types.ContentType.TEXT)
async def fallback_text(message: types.Message) -> None:
    await message.answer("Нажми 'Найти забеги' для запуска поиска.", reply_markup=menu_keyboard)


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
