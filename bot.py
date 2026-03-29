import logging
import os
import re
import sqlite3
from typing import Optional, Tuple

from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_TOKEN_HERE":
    raise RuntimeError(
        "BOT_TOKEN не задан. Создай файл .env и вставь токен от @BotFather."
    )

DB_PATH = "history.db"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

menu_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
menu_keyboard.add(KeyboardButton("Время -> Темп"), KeyboardButton("Темп -> Время"))
menu_keyboard.add(KeyboardButton("Калории"), KeyboardButton("История"))
menu_keyboard.add(KeyboardButton("Помощь"), KeyboardButton("О боте"))

cancel_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
cancel_keyboard.add(KeyboardButton("Отмена"))


class PaceCalcStates(StatesGroup):
    waiting_time_distance = State()
    waiting_pace_distance = State()
    waiting_calories = State()


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                mode TEXT NOT NULL,
                input_text TEXT NOT NULL,
                result_text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()


def save_history(user_id: int, mode: str, input_text: str, result_text: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO history (user_id, mode, input_text, result_text)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, mode, input_text.strip(), result_text.strip()),
        )
        # Keep only latest 10 records per user.
        conn.execute(
            """
            DELETE FROM history
            WHERE user_id = ?
              AND id NOT IN (
                SELECT id FROM history
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 10
              )
            """,
            (user_id, user_id),
        )
        conn.commit()


def get_history(user_id: int, limit: int = 10) -> list[tuple[str, str, str, str]]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT created_at, mode, input_text, result_text
            FROM history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return rows


def parse_distance(raw: str) -> Optional[float]:
    normalized = re.sub(
        r"(км|km|километр(?:а|ов)?)",
        "",
        raw.strip().lower(),
    ).strip().replace(",", ".")

    try:
        distance = float(normalized)
    except ValueError:
        return None

    if distance <= 0:
        return None

    return distance


def parse_weight(raw: str) -> Optional[float]:
    normalized = re.sub(
        r"(кг|kg|килограмм(?:а|ов)?)",
        "",
        raw.strip().lower(),
    ).strip().replace(",", ".")
    try:
        weight = float(normalized)
    except ValueError:
        return None
    if weight <= 0:
        return None
    return weight


def parse_time_to_seconds(raw: str) -> Optional[int]:
    value = raw.strip().lower()
    if not value:
        return None

    parts = value.split(":")
    if len(parts) == 2:
        try:
            minutes, seconds = map(int, parts)
        except ValueError:
            return None
        if minutes < 0 or not (0 <= seconds < 60):
            return None
        total = minutes * 60 + seconds
        return total if total > 0 else None

    if len(parts) == 3:
        try:
            hours, minutes, seconds = map(int, parts)
        except ValueError:
            return None
        if hours < 0 or not (0 <= minutes < 60) or not (0 <= seconds < 60):
            return None
        total = hours * 3600 + minutes * 60 + seconds
        return total if total > 0 else None

    compact = value.replace(" ", "")
    match = re.fullmatch(
        r"(?:(\d+)(?:ч|час|часа|часов|h|hr|hour|hours))?"
        r"(?:(\d+)(?:м|мин|минута|минуты|минут|min|m))?"
        r"(?:(\d+)(?:с|сек|секунда|секунды|секунд|sec|s))?",
        compact,
    )
    if match:
        hours = int(match.group(1)) if match.group(1) else 0
        minutes = int(match.group(2)) if match.group(2) else 0
        seconds = int(match.group(3)) if match.group(3) else 0
        total = hours * 3600 + minutes * 60 + seconds
        return total if total > 0 else None

    return None


def parse_pace_to_seconds(raw: str) -> Optional[int]:
    return parse_time_to_seconds(raw)


def extract_distance_and_value(raw: str) -> Tuple[Optional[float], Optional[str]]:
    match = re.match(
        r"^\s*(\d+(?:[.,]\d+)?)\s*(?:км|km|километр(?:а|ов)?)?\s+(.+?)\s*$",
        raw.strip().lower(),
    )
    if not match:
        return None, None

    distance = parse_distance(match.group(1))
    value = match.group(2).strip()
    return distance, value


def format_seconds_to_time(total_seconds: int) -> str:
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def format_seconds_to_pace(total_seconds: int) -> str:
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"


def estimate_met(speed_kmh: float) -> float:
    if speed_kmh < 8.0:
        return 8.3
    if speed_kmh < 9.7:
        return 9.8
    if speed_kmh < 10.8:
        return 10.5
    if speed_kmh < 11.3:
        return 11.0
    if speed_kmh < 12.1:
        return 11.8
    if speed_kmh < 12.9:
        return 12.3
    if speed_kmh < 13.8:
        return 12.8
    if speed_kmh < 14.5:
        return 14.5
    if speed_kmh < 16.1:
        return 16.0
    if speed_kmh < 17.7:
        return 19.0
    return 19.8


@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message) -> None:
    text = (
        "Привет! Я калькулятор для бегунов.\n\n"
        "Что умею:\n"
        "1) Время + дистанция -> темп (мин/км)\n"
        "2) Темп + дистанция -> итоговое время\n"
        "3) Прогноз калорий на пробежке\n"
        "4) История последних 10 расчетов\n\n"
        "Выбери режим кнопкой ниже."
    )
    await message.answer(text, reply_markup=menu_keyboard)


@dp.message_handler(commands=["help"])
@dp.message_handler(lambda m: m.text == "Помощь")
async def cmd_help(message: types.Message) -> None:
    await message.answer(
        "Форматы ввода:\n"
        "- Время: MM:SS, HH:MM:SS или с единицами (24м30с, 1ч5м)\n"
        "- Темп: MM:SS или с единицами (4:55, 4м55с)\n"
        "- Дистанция: км, можно дробную (5, 10.5, 21,1км)\n"
        "- Вес: кг (70, 68кг)\n\n"
        "Режим 'Время -> Темп': отправь строку `дистанция время`\n"
        "Примеры: `5 24:30`, `5км 24м30с`\n\n"
        "Режим 'Темп -> Время': отправь строку `дистанция темп`\n"
        "Примеры: `10 5:20`, `10 км 5м20с`\n\n"
        "Режим 'Калории':\n"
        "- `дистанция вес` (быстрая оценка)\n"
        "- `дистанция время вес` (точнее, с учетом скорости)\n"
        "Примеры: `10 70`, `10 52:30 70`, `21,1км 1:45:00 68кг`\n\n"
        "Кнопка 'История' показывает 10 последних расчетов.\n"
        "Чтобы выйти из режима, нажми 'Отмена'.",
        reply_markup=menu_keyboard,
    )


@dp.message_handler(lambda m: m.text == "О боте")
async def about_bot(message: types.Message) -> None:
    await message.answer("Бот считает темп, время, калории и хранит историю расчетов.")


@dp.message_handler(commands=["history"])
@dp.message_handler(lambda m: m.text == "История")
async def show_history(message: types.Message) -> None:
    rows = get_history(message.from_user.id, limit=10)
    if not rows:
        await message.answer("История пока пуста. Сделай первый расчет.", reply_markup=menu_keyboard)
        return

    lines = ["Последние расчеты:"]
    for idx, (created_at, mode, input_text, result_text) in enumerate(rows, start=1):
        ts = created_at.replace("T", " ")
        lines.append(f"{idx}. [{ts}] {mode}")
        lines.append(f"   Ввод: {input_text}")
        lines.append(f"   Результат: {result_text}")

    await message.answer("\n".join(lines), reply_markup=menu_keyboard)


@dp.message_handler(lambda m: m.text == "Отмена", state="*")
async def cancel_state(message: types.Message, state: FSMContext) -> None:
    if await state.get_state() is not None:
        await state.finish()
        await message.answer("Ок, режим сброшен.", reply_markup=menu_keyboard)
    else:
        await message.answer("Сейчас нет активного режима.", reply_markup=menu_keyboard)


@dp.message_handler(lambda m: m.text == "Время -> Темп")
async def start_time_to_pace(message: types.Message) -> None:
    await PaceCalcStates.waiting_time_distance.set()
    await message.answer(
        "Отправь: `дистанция время`\nПримеры: `5 24:30`, `5км 24м30с`",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard,
    )


@dp.message_handler(lambda m: m.text == "Темп -> Время")
async def start_pace_to_time(message: types.Message) -> None:
    await PaceCalcStates.waiting_pace_distance.set()
    await message.answer(
        "Отправь: `дистанция темп`\nПримеры: `10 5:20`, `10 км 5м20с`",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard,
    )


@dp.message_handler(lambda m: m.text == "Калории")
async def start_calories(message: types.Message) -> None:
    await PaceCalcStates.waiting_calories.set()
    await message.answer(
        "Отправь:\n"
        "`дистанция вес` или `дистанция время вес`\n"
        "Примеры: `10 70`, `10 52:30 70`, `21,1км 1:45:00 68кг`",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard,
    )


@dp.message_handler(state=PaceCalcStates.waiting_time_distance, content_types=types.ContentType.TEXT)
async def calculate_pace(message: types.Message, state: FSMContext) -> None:
    distance, time_raw = extract_distance_and_value(message.text)
    total_seconds = parse_time_to_seconds(time_raw or "")

    if distance is None:
        await message.answer(
            "Не смог прочитать дистанцию. Пример: `5`, `10.5`, `21,1км`",
            parse_mode="Markdown",
        )
        return
    if total_seconds is None:
        await message.answer(
            "Не смог прочитать время. Пример: `24:30`, `01:24:30`, `24м30с`",
            parse_mode="Markdown",
        )
        return

    pace_seconds = round(total_seconds / distance)
    pace_text = format_seconds_to_pace(pace_seconds)

    result_text = f"Темп: {pace_text} мин/км"
    save_history(message.from_user.id, "Время -> Темп", message.text, result_text)

    await state.finish()
    await message.answer(
        f"Дистанция: {distance:g} км\n"
        f"Время: {format_seconds_to_time(total_seconds)}\n"
        f"{result_text}",
        reply_markup=menu_keyboard,
    )


@dp.message_handler(state=PaceCalcStates.waiting_pace_distance, content_types=types.ContentType.TEXT)
async def calculate_time(message: types.Message, state: FSMContext) -> None:
    distance, pace_raw = extract_distance_and_value(message.text)
    pace_seconds = parse_pace_to_seconds(pace_raw or "")

    if distance is None:
        await message.answer(
            "Не смог прочитать дистанцию. Пример: `5`, `10.5`, `21,1км`",
            parse_mode="Markdown",
        )
        return
    if pace_seconds is None:
        await message.answer(
            "Не смог прочитать темп. Пример: `4:55` или `4м55с`",
            parse_mode="Markdown",
        )
        return

    total_seconds = round(distance * pace_seconds)

    result_text = f"Итоговое время: {format_seconds_to_time(total_seconds)}"
    save_history(message.from_user.id, "Темп -> Время", message.text, result_text)

    await state.finish()
    await message.answer(
        f"Дистанция: {distance:g} км\n"
        f"Темп: {format_seconds_to_pace(pace_seconds)} мин/км\n"
        f"{result_text}",
        reply_markup=menu_keyboard,
    )


@dp.message_handler(state=PaceCalcStates.waiting_calories, content_types=types.ContentType.TEXT)
async def calculate_calories(message: types.Message, state: FSMContext) -> None:
    parts = message.text.strip().split()
    if len(parts) not in (2, 3):
        await message.answer(
            "Нужен формат: `дистанция вес` или `дистанция время вес`.\n"
            "Примеры: `10 70`, `10 52:30 70`",
            parse_mode="Markdown",
        )
        return

    distance = parse_distance(parts[0])
    if distance is None:
        await message.answer(
            "Не смог прочитать дистанцию. Пример: `10`, `21,1км`",
            parse_mode="Markdown",
        )
        return

    if len(parts) == 2:
        weight = parse_weight(parts[1])
        if weight is None:
            await message.answer(
                "Не смог прочитать вес. Пример: `70` или `68кг`",
                parse_mode="Markdown",
            )
            return
        kcal = round(distance * weight * 1.036)
        method = "быстрая оценка"
        details = ""
    else:
        total_seconds = parse_time_to_seconds(parts[1])
        weight = parse_weight(parts[2])
        if total_seconds is None:
            await message.answer(
                "Не смог прочитать время. Пример: `52:30` или `1:05:40`",
                parse_mode="Markdown",
            )
            return
        if weight is None:
            await message.answer(
                "Не смог прочитать вес. Пример: `70` или `68кг`",
                parse_mode="Markdown",
            )
            return
        hours = total_seconds / 3600
        speed_kmh = distance / hours
        met = estimate_met(speed_kmh)
        kcal = round(met * weight * hours)
        method = "оценка с учетом скорости (MET)"
        details = (
            f"\nВремя: {format_seconds_to_time(total_seconds)}"
            f"\nСредняя скорость: {speed_kmh:.2f} км/ч"
        )

    result_text = f"Расход: ~{kcal} ккал"
    save_history(message.from_user.id, "Калории", message.text, result_text)

    await state.finish()
    await message.answer(
        f"Дистанция: {distance:g} км\n"
        f"Вес: {weight:g} кг"
        f"{details}\n"
        f"{result_text}\n"
        f"Метод: {method}",
        reply_markup=menu_keyboard,
    )


@dp.message_handler(content_types=types.ContentType.TEXT)
async def fallback_text(message: types.Message) -> None:
    await message.answer(
        "Выбери режим: 'Время -> Темп', 'Темп -> Время', 'Калории' или 'История'.\n"
        "Если нужно, нажми 'Помощь'.",
        reply_markup=menu_keyboard,
    )


if __name__ == "__main__":
    init_db()
    executor.start_polling(dp, skip_updates=True)
