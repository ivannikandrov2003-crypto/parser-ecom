import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------- ELASTICSEARCH ----------
ES_URL = os.getenv("ES_URL", "http://127.0.0.1:9200")
ES_INDEX = "news"
NEWS_RETENTION_DAYS = 30
SEMANTIC_SIMILARITY_THRESHOLD = float(os.getenv("SEMANTIC_SIMILARITY_THRESHOLD", "0.92"))

# ---------- ПАЙПЛАЙН ----------
REFRESH_INTERVAL_MINUTES = int(os.getenv("REFRESH_INTERVAL_MINUTES", "60"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
PIPELINE_LOCK_PATH = Path(os.getenv("PIPELINE_LOCK_PATH") or Path(__file__).resolve().with_name(".pipeline.lock"))

# ---------- GIGACHAT ----------
GIGACHAT_CLIENT_ID = os.getenv("GIGACHAT_CLIENT_ID", "")
GIGACHAT_CLIENT_SECRET = os.getenv("GIGACHAT_CLIENT_SECRET", "")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_CA_BUNDLE = os.getenv("GIGACHAT_CA_BUNDLE", "")
GIGACHAT_CHAT_MODEL = os.getenv("GIGACHAT_CHAT_MODEL", "GigaChat-2")

# ---------- CLOUD.RU FOUNDATION MODELS ----------
CLOUDRU_API_KEY = os.getenv("CLOUDRU_API_KEY", "")
CLOUDRU_NETWORK_INTERFACE = os.getenv("CLOUDRU_NETWORK_INTERFACE", "")
CLOUDRU_DOH_URL = os.getenv("CLOUDRU_DOH_URL", "")
CLOUDRU_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
EMBEDDING_DIMENSIONS = 1024

# ---------- ИСТОЧНИКИ RSS ----------
SOURCES = {
    "Sostav": "https://www.sostav.ru/rss",
    # "Adindex": "https://adindex.ru/news/news.rss",
    # "РБК": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
    # "Ведомости": "https://www.vedomosti.ru/rss/1news",
    "Коммерсант": "https://www.kommersant.ru/RSS/corp.xml",
    "Forbes": "https://www.forbes.ru/newrss.xml",
    "Shoppers": "https://shoppers.media/rss.xml",
    "ТАСС": "https://tass.ru/rss/v2.xml",
    "РИА Новости": "https://ria.ru/export/rss2/archive/index.xml",
    "Известия": "https://iz.ru/xml/rss/all.xml",
}

# ---------- КЛЮЧЕВЫЕ СЛОВА ДЛЯ ФИЛЬТРАЦИИ ----------
KEYWORDS = [
    "ритейл",
    "retail",
    "е-ком",
    "e-com",
    "маркетплейс",
    "wildberries",
    "ozon",
    "яндекс маркет",
    "мегамаркет",
    "реклам",
    "интернет-торговл",
    "логистик",
    "склад",
    "лента",
    "магнит",
    "пятерочка",
    "перекресток",
    "вкусвилл",
    "м.видео",
    "эльдорадо",
    "ecommerce",
    "fmcg",
    "fashion",
    "darkstore",
    "даркстор",
    "пвз",
    "курьер",
    "x5",
    "х5",
    "о'кей",
    "озон",
    "wb",
    "rwb",
    "яндекс лавка",
    "самокат",
    "купер",
]
