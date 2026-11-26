import os
from re import fullmatch

from dotenv import load_dotenv

load_dotenv()

# ---------- ELASTICSEARCH ----------
ES_URL = os.getenv("ES_URL", "http://127.0.0.1:9200")
NEWS_RETENTION_DAYS = 30

# ---------- ПАЙПЛАЙН ----------
REFRESH_INTERVAL_MINUTES = int(os.getenv("REFRESH_INTERVAL_MINUTES", "30"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# ---------- TELEGRAM ----------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
TELEGRAM_CONFIGURED = bool(TELEGRAM_CHANNEL_ID and (
    TELEGRAM_BOT_TOKEN or os.getenv("TELEGRAM_TOKEN_CONFIGURED") == "true"
))
TELEGRAM_CHANNEL_NAME = os.getenv("TELEGRAM_CHANNEL_NAME", "").strip() or "Новости e-commerce"
TELEGRAM_CHANNEL_USERNAME = os.getenv("TELEGRAM_CHANNEL_USERNAME", "").strip().removeprefix("@")
if not TELEGRAM_CHANNEL_USERNAME and TELEGRAM_CHANNEL_ID.startswith("@"):
    TELEGRAM_CHANNEL_USERNAME = TELEGRAM_CHANNEL_ID[1:]
TELEGRAM_CHANNEL_URL = (
    f"https://t.me/{TELEGRAM_CHANNEL_USERNAME}"
    if fullmatch(r"[a-zA-Z0-9_]{1,32}", TELEGRAM_CHANNEL_USERNAME) else None
)

# ---------- GIGACHAT ----------
GIGACHAT_CLIENT_ID = os.getenv("GIGACHAT_CLIENT_ID", "")
GIGACHAT_CLIENT_SECRET = os.getenv("GIGACHAT_CLIENT_SECRET", "")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_CA_BUNDLE = os.getenv("GIGACHAT_CA_BUNDLE", "")
GIGACHAT_CHAT_MODEL = "GigaChat-2"  # Lite, обычная генерация текста.

# ---------- ИСТОЧНИКИ RSS ----------
SOURCES = {
    "Sostav": "https://www.sostav.ru/rss",
    "AdIndex": "https://adindex.ru/news/news.rss",
    # "РБК": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
    "Ведомости": "https://www.vedomosti.ru/rss/rubric/business/retail",
    "Коммерсант": "https://www.kommersant.ru/RSS/corp.xml",
    # "Forbes": "https://www.forbes.ru/newrss.xml",
    # "Shoppers": "https://shoppers.media/rss.xml",
    "ТАСС": "https://tass.ru/rss/v2.xml",
    "РИА Новости": "https://ria.ru/export/rss2/archive/index.xml",
    "Известия": "https://iz.ru/xml/rss/news.xml",
    "Retail.ru": "https://www.retail.ru/rss/news/",
}

RSS_EXCERPT_SOURCES = {"ТАСС", "Известия"}
RSS_STANDARD_HTTP_SOURCES = {"Известия"}

# ---------- ТЕМАТИКА E-COMMERCE ----------
ECOM_TOPIC_KEYWORDS = [
    # Каналы и модели онлайн-торговли
    "e-commerce",
    "ecommerce",
    "ecom",
    "е-ком",
    "электронная коммерция",
    "электронная торговля",
    "интернет-торговля",
    "онлайн-ритейл",
    "онлайн-торговля",
    "онлайн-продажи",
    "онлайн-заказы",
    "онлайн-покупки",
    "интернет-магазин",
    "интернет-магазины",
    "маркетплейс",
    "маркетплейсы",
    "маркетплейсах",
    "торговая онлайн-площадка",
    "социальная коммерция",
    "social commerce",
    "live commerce",
    "quick commerce",
    "q-commerce",
    "e-grocery",
    "онлайн-супермаркет",
    "c2c",
    "d2c",
    "b2b-маркетплейс",
    "дропшиппинг",
    # Площадки и продавцы
    "wildberries",
    "вайлдберриз",
    "вайлдберрис",
    "рвб",
    "ozon",
    "озон",
    "яндекс маркет",
    "мегамаркет",
    "сбермегамаркет",
    "авито",
    "aliexpress",
    "алиэкспресс",
    "lamoda",
    "ламода",
    "купишуз",
    "детский мир онлайн",
    "яндекс лавка",
    "яндекс лавки",
    "яндекс еда",
    "самокат",
    "купер",
    "shopify",
    "amazon",
    "temu",
    "shein",
    "ebay",
    "etsy",
    "селлер",
    "селлеры",
    "селлеров",
    "кабинет продавца",
    "карточка товара",
    "карточки товаров",
    "комиссия маркетплейса",
    "витрина товаров",
    "подписка продавца",
    "ритейл-медиа",
    "ретейл-медиа",
    "retail media",
    "продвижение товаров",
    # Доставка, платежи и сопровождение онлайн-заказов
    "фулфилмент",
    "фулфиллмент",
    "fulfillment",
    "fbo",
    "fbs",
    "dbs",
    "пвз",
    "пункт выдачи заказов",
    "пункты выдачи заказов",
    "постамат",
    "постаматы",
    "даркстор",
    "dark store",
    "darkstore",
    "последняя миля",
    "экспресс-доставка",
    "доставка онлайн-заказов",
    "доставка день в день",
    "возврат онлайн-заказа",
    "интернет-эквайринг",
    "онлайн-эквайринг",
    "оплата частями",
    "bnpl",
    "касса интернет-магазина",
    "трансграничная электронная торговля",
]

# Заголовки в старом пайплайне также проверяются по прежним широким признакам.
KEYWORDS = [
    *ECOM_TOPIC_KEYWORDS,
    "ритейл",
    "retail",
    "e-com",
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
    "fmcg",
    "fashion",
    "курьер",
    "x5",
    "х5",
    "о'кей",
    "wb",
    "rwb",
]

# ---------- НОВЫЙ КОНВЕЙЕР ----------
NEWS_SEARCH_INDEX = os.getenv("NEWS_SEARCH_INDEX", "ecom-keywords-v1")
NEWS_DUPLICATE_SCORE = float(os.getenv("NEWS_DUPLICATE_SCORE", "0.5"))
NEWS_DUPLICATE_MIN_MATCHES = int(os.getenv("NEWS_DUPLICATE_MIN_MATCHES", "2"))
NEWS_MAX_KEYWORDS = int(os.getenv("NEWS_MAX_KEYWORDS", "8"))
AI_POLL_SECONDS = int(os.getenv("AI_POLL_SECONDS", "5"))
NEWS_CLEANUP_INTERVAL_MINUTES = int(os.getenv("NEWS_CLEANUP_INTERVAL_MINUTES", "60"))
