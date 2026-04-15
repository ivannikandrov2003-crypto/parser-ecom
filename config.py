import os

# ---------- ПОЧТОВЫЕ НАСТРОЙКИ ----------
# Адрес, с которого будут отправляться письма (лучше использовать тот же, для которого получен пароль приложения)
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "Sh1b1e@yandex.ru")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "jbnwmlyxnqainzik")
EMAIL_RECIPIENT = "artnikandrov@gmail.com"   # фиксированный получатель

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