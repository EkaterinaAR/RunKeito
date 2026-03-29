# Telegram Bots (Python + aiogram)

В проекте два бота:
- `bot.py` - старый бот-калькулятор (темп/время/калории)
- `race_bot.py` - бот для поиска забегов

## Подготовка
```powershell
cd "C:\Users\Ekaterina\Desktop\МЕТА\telegram-bot"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Токены
Можно использовать отдельные `.env` для каждого бота:
- `.env.calculator` c `BOT_TOKEN_CALCULATOR=...`
- `.env.race` c `BOT_TOKEN_RACE=...`

Также поддерживается общий fallback в `.env`:
- `BOT_TOKEN=...`

## Запуск
Калькулятор:
```powershell
python bot.py
```

Поиск забегов:
```powershell
python race_bot.py
```

## Railway
Для деплоя настроен `Procfile`:
- `worker: python race_bot.py`

## Поиск забегов
Параметры:
- дистанция: `марафон` / `полумарафон` / `любая`
- страна
- месяц и год

Важно: минимум 2 параметра из 3.
Формат ответа: `название / страна / город / дата`.
