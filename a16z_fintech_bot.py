import html
import logging
import os
import re
import textwrap
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from aiogram import Bot, Dispatcher, executor, types
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env.a16z")
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN_A16Z") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_TOKEN_HERE":
    raise RuntimeError("BOT_TOKEN не задан. Добавь BOT_TOKEN_A16Z в .env.a16z.")

FINTECH_CATEGORY_URL = "https://a16z.com/category/fintech/"
MAX_ITEMS = 5
REQUEST_TIMEOUT = 15
CACHE_TTL_MINUTES = 30

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)


@dataclass
class FeedItem:
    title: str
    link: str
    summary: str
    published_at: Optional[datetime]


def strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def short_summary(title: str, description: str, limit: int = 180) -> str:
    base = strip_html(description)
    if not base:
        return "Краткое описание недоступно, смотри первоисточник."

    sentence_end = re.search(r"[.!?]\s", base)
    if sentence_end:
        candidate = base[: sentence_end.end()].strip()
    else:
        candidate = base

    if len(candidate) > limit:
        candidate = textwrap.shorten(candidate, width=limit, placeholder="...")

    if candidate.lower() == strip_html(title).lower():
        return "Материал о трендах и практиках в Fintech от команды a16z."
    return candidate


def normalize_title(value: str) -> str:
    return re.sub(r"\s*\|\s*Andreessen Horowitz\s*$", "", value or "").strip()


def fetch_url(url: str, accept: str = "text/html") -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; A16ZFintechBot/1.0)",
            "Accept": accept,
        },
    )
    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return response.read().decode("utf-8", "replace")


def collect_candidates(html_page: str) -> List[Dict[str, str]]:
    candidates: List[Dict[str, str]] = []
    seen = set()

    pattern = re.compile(
        r'<a\s+href="(https://a16z.com/[^"]+)"[^>]*class="block group/card"[^>]*>'
        r".*?<span[^>]*>(.*?)</span>",
        flags=re.IGNORECASE | re.DOTALL,
    )

    for href, raw_title in pattern.findall(html_page):
        title = strip_html(raw_title)
        if len(title) < 8:
            continue
        key = (href, title)
        if key in seen:
            continue
        seen.add(key)
        candidates.append({"href": href, "title": title})

    if candidates:
        return candidates

    fallback_pattern = re.compile(
        r'<a\s+href="(https://a16z.com/[^"]+)"[^>]*>(.*?)</a>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    for href, raw_text in fallback_pattern.findall(html_page):
        title = strip_html(raw_text)
        if (
            len(title) < 8
            or "/category/" in href
            or "/author/" in href
            or "/tag/" in href
            or "/about/" in href
            or "/wp-content/" in href
        ):
            continue
        if "fintech" not in (href + " " + title).lower():
            continue
        key = (href, title)
        if key in seen:
            continue
        seen.add(key)
        candidates.append({"href": href, "title": title})

    return candidates


def parse_meta(field: str, html_page: str, property_key: str = "name") -> str:
    patterns = [
        rf'<meta\s+[^>]*{property_key}="{re.escape(field)}"[^>]*content="([^"]+)"',
        rf'<meta\s+[^>]*content="([^"]+)"[^>]*{property_key}="{re.escape(field)}"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_page, flags=re.IGNORECASE)
        if match:
            return strip_html(match.group(1))
    return ""


def parse_article(item: Dict[str, str]) -> Optional[FeedItem]:
    page = fetch_url(item["href"])

    og_title = parse_meta("og:title", page, property_key="property")
    og_description = parse_meta("og:description", page, property_key="property")
    published_raw = parse_meta("article:published_time", page, property_key="property")

    published_at = None
    if published_raw:
        try:
            normalized = published_raw.replace("Z", "+00:00")
            published_at = datetime.fromisoformat(normalized)
        except ValueError:
            published_at = None

    title = normalize_title(og_title or item["title"])
    summary = short_summary(title=title, description=og_description)
    return FeedItem(
        title=title,
        link=item["href"],
        summary=summary,
        published_at=published_at,
    )


_news_cache: Dict[str, object] = {"fetched_at": None, "items": []}


def get_fintech_news(limit: int = MAX_ITEMS) -> List[FeedItem]:
    now = datetime.now(timezone.utc)
    fetched_at = _news_cache.get("fetched_at")
    if isinstance(fetched_at, datetime) and now - fetched_at < timedelta(
        minutes=CACHE_TTL_MINUTES
    ):
        cached = _news_cache.get("items") or []
        return list(cached)[:limit]

    category_page = fetch_url(FINTECH_CATEGORY_URL)
    candidates = collect_candidates(category_page)

    items: List[FeedItem] = []
    for candidate in candidates:
        if len(items) >= limit:
            break
        try:
            parsed = parse_article(candidate)
        except (URLError, TimeoutError):
            continue
        if parsed:
            items.append(parsed)

    items.sort(
        key=lambda x: x.published_at.timestamp() if x.published_at else 0.0,
        reverse=True,
    )
    _news_cache["fetched_at"] = now
    _news_cache["items"] = list(items)

    return items[:limit]


def format_item(index: int, news: FeedItem) -> str:
    date_str = ""
    if news.published_at:
        date_str = news.published_at.strftime("%Y-%m-%d")

    date_line = f"\nДата: {date_str}" if date_str else ""
    return (
        f"{index}. {news.title}{date_line}\n"
        f"Саммари: {news.summary}\n"
        f"Источник: {news.link}"
    )


@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message) -> None:
    intro = (
        "Привет! Это a16z Fintech bot.\n"
        "Собираю свежие публикации с тегом Fintech и даю короткое саммари.\n"
    )
    await message.answer(intro)

    try:
        news = get_fintech_news()
    except (URLError, TimeoutError, ValueError) as exc:
        logging.exception("Failed to fetch feed: %s", exc)
        await message.answer(
            "Не получилось получить данные с a16z прямо сейчас. Попробуй еще раз чуть позже."
        )
        return

    if not news:
        await message.answer("Пока не нашла публикации по тегу Fintech.")
        return

    blocks = [format_item(i, item) for i, item in enumerate(news, start=1)]
    await message.answer("\n\n".join(blocks), disable_web_page_preview=True)


@dp.message_handler(commands=["help"])
async def cmd_help(message: types.Message) -> None:
    await message.answer("Команда: /start - показать короткие саммари по a16z Fintech.")


def main() -> None:
    executor.start_polling(dp, skip_updates=True)


if __name__ == "__main__":
    main()
