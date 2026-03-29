# Telegram Bot (Python + aiogram)

Бот помогает бегунам считать:
- темп (мин/км) по дистанции и времени
- итоговое время по дистанции и темпу

## 1) Получи токен
1. Открой Telegram и напиши `@BotFather`
2. Выполни `/newbot`
3. Скопируй токен

## 2) Подготовь проект (Windows PowerShell)
```powershell
cd "C:\Users\Ekaterina\Desktop\МЕТА\telegram-bot"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Открой файл `.env` и вставь токен:
```env
BOT_TOKEN=123456:ABC...
```

## 3) Запуск
```powershell
python bot.py
```

## Поддерживаемые форматы ввода
- Дистанция: `5`, `10.5`, `21,1км`, `10 км`
- Время: `24:30`, `01:05:40`, `24м30с`, `1ч5м`
- Темп: `4:55`, `5м20с`

## Примеры
### Время -> Темп
- `5 24:30`
- `5км 24м30с`

### Темп -> Время
- `10 5:20`
- `10 км 5м20с`
