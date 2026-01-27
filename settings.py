from dotenv import load_dotenv
import os

# Загружаем переменные окружения из файла .env в корне проекта
load_dotenv()

# Токен Telegram-бота
BOT_TOKEN: str | None = os.getenv("BOT_TOKEN")

# Часовой пояс по умолчанию (Владивосток, GMT+10)
DEFAULT_TIMEZONE: str = "Asia/Vladivostok"

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не найден. Убедись, что в файле .env задана переменная BOT_TOKEN=..."
    )