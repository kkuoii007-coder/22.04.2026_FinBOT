import asyncio
import requests

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message

from config import TOKEN


MOEX_SEARCH_URL = "https://iss.moex.com/iss/securities.json"
MAX_RESULTS_PER_GROUP = 15

bot = Bot(token=TOKEN)
dp = Dispatcher()


session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; MOEXIssuerBot/1.0)"})


def fetch_securities(query: str) -> list[dict]:
    params = {
        "q": query,
        "limit": 100,
        "start": 0,
        "iss.only": "securities",
        "securities.columns": "secid,shortname,name,emitent_title,type,group,primary_boardid",
        "lang": "ru",
    }

    try:
        response = session.get(MOEX_SEARCH_URL, params=params, timeout=15)
        response.raise_for_status()
        payload = response.json()

        block = payload.get("securities", {})
        columns = block.get("columns", [])
        data = block.get("data", [])

        if columns and data:
            result = []
            for row in data:
                item = {str(col).lower(): value for col, value in zip(columns, row)}
                result.append(item)
            return result

        if isinstance(data, list) and data and isinstance(data[0], dict):
            return [{str(k).lower(): v for k, v in row.items()} for row in data]

        return []

    except Exception as e:
        print(f"Ошибка при запросе к MOEX API: {e}")
        return []


def filter_securities(securities: list[dict]) -> tuple[list[dict], list[dict]]:
    stocks = []
    bonds = []
    seen_stocks = set()
    seen_bonds = set()

    for item in securities:
        secid = item.get("secid")
        if not secid:
            continue

        group = (item.get("group") or "").strip().lower()
        shortname = item.get("shortname")
        name = item.get("name")
        emitent_title = item.get("emitent_title")
        primary_boardid = item.get("primary_boardid")

        display_name = shortname or name or emitent_title or secid

        record = {
            "code": secid,
            "name": display_name,
            "issuer": emitent_title,
            "board": primary_boardid,
        }

        # Акции
        if group == "stock_shares":
            if secid not in seen_stocks:
                seen_stocks.add(secid)
                stocks.append(record)

        # Облигации
        elif group == "stock_bonds":
            if secid not in seen_bonds:
                seen_bonds.add(secid)
                bonds.append(record)

    return stocks[:MAX_RESULTS_PER_GROUP], bonds[:MAX_RESULTS_PER_GROUP]


def format_response(query: str, stocks: list[dict], bonds: list[dict]) -> str:
    if not stocks and not bonds:
        return (
            "Ничего не найдено.\n"
            "Попробуйте ввести тикер или официальное краткое наименование эмитента/бумаги, "
            "как на сайте Московской биржи.\n"
            "Проверить наименование можно здесь:\n"
            "https://www.moex.com/ru/spot/issues.aspx"
        )

    lines = [f"Найдено по запросу: {query}", ""]

    if stocks:
        lines.append("Акции:")
        for stock in stocks:
            lines.append(f"- {stock['code']} — {stock['name']}")
    else:
        lines.append("Акции не найдены.")

    lines.append("")

    if bonds:
        lines.append("Облигации:")
        for bond in bonds:
            lines.append(f"- {bond['code']} — {bond['name']}")
    else:
        lines.append("Облигации не найдены.")

    return "\n".join(lines)


@dp.message(CommandStart())
async def send_welcome(message: Message):
    welcome_text = (
        "Привет, я бот - агрегатор информации по ценным бумагам конкретных эмитентов.\n\n"
        "Я ищу только акции и облигации.\n\n"
        "Важно: имя эмитента лучше вводить в том виде, в котором оно используется на Московской бирже — "
        "по тикеру, коду бумаги или официальному краткому наименованию.\n\n"
        "Например:\n"
        "Сбербанк → SBER\n\n"
        "Если вы не уверены в названии, уточните его в официальном поиске Московской биржи:\n"
        "https://www.moex.com/ru/spot/issues.aspx"
    )
    await message.answer(welcome_text)


@dp.message(F.text)
async def handle_text_message(message: Message):
    user_query = message.text.strip()

    # Игнорируем команды, кроме /start
    if user_query.startswith("/"):
        return

    if len(user_query) < 3:
        await message.answer(
            "Пожалуйста, введите более точный запрос (не менее 3 символов)."
        )
        return

    securities = await asyncio.to_thread(fetch_securities, user_query)

    print(f"Запрос пользователя: {user_query}")
    print(f"Всего строк от ISS: {len(securities)}")
    if securities:
        print("Первые 3 записи:")
        for row in securities[:3]:
            print(row)

    stocks, bonds = filter_securities(securities)
    response_text = format_response(user_query, stocks, bonds)

    await message.answer(response_text)


async def main():
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
