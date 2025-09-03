import os
from datetime import datetime, timezone
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

# ─── Токены и API ────────────────────────────────────────────────────────
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip().strip('"').strip("'")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден — проверь расположение .env и имя переменной.")

AZURE_API_KEY = os.getenv("OPENAI_API_KEY")       
AZURE_OPENAI_ENDPOINT = os.getenv("OPENAI_API_BASE")
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME")
AZURE_API_VERSION = os.getenv("OPENAI_API_VERSION")


HEADERS = {
    "Content-Type": "application/json",
    "api-key": AZURE_API_KEY,
}

# ─── Пути и файлы ────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "warnings.db")
STOPWORDS_PATH = os.getenv("STOPWORDS_PATH", "stopwords.txt")
RULES_PATH = os.getenv("RULES_PATH", "rules.txt")

# ─── Админы и супер-админы ───────────────────────────────────────────────
# списки как МУТАБЕЛЬНЫЕ объекты, чтобы их можно было менять из хендлеров
ADMIN_USERNAMES = ["@scrmmzdk", "@Maga22804"]
SUPER_ADMINS = ["@Maga22804", "@scrmmzdk"]

# ─── Общие флаги (как ссылки на контейнеры, чтобы менять по месту) ──────
PAUSED = [False]      # /pause, /resume
AI_ENABLED = [True]   # /onai, /offai
IMMUNE_USERS = [set()]  # /god, /godoff

BOT_START_TIME = datetime.now(timezone.utc)

# Куда писать аварийные уведомления; можно оставить None
LOG_CHAT_ID = int(os.getenv("LOG_CHAT_ID", "0")) or None
