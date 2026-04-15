from curl_cffi import requests
from bs4 import BeautifulSoup
from config import KEYWORDS
import time
import warnings
from bs4 import XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

def get_updates(sources):
    news_list = []

    for name, url in sources.items():
        try:
            print(f"Парсим {name}...")
            for attempt in range(5):
                response = requests.get(url, impersonate="chrome110", timeout=30)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, "xml")
                    break
                if response.status_code == 429:
                    time.sleep(2**attempt)
                    continue
                print(f"Сайт {name} ответил кодом {response.status_code}")
                break

            if response.status_code != 200:
                print(f"Сайт {name} ответил кодом {response.status_code}")
                continue

            soup = BeautifulSoup(response.content, "xml")
            items = soup.find_all("item")
            if not items:
                items = soup.find_all("entry")

            for item in items:
                title = item.find("title").text.strip() if item.find("title") else ""
                link_tag = item.find("link")
                if link_tag and link_tag.text.strip():
                    link = link_tag.text.strip()
                elif link_tag and link_tag.get("href"):
                    link = link_tag.get("href")
                else:
                    link = item.find("guid").text.strip() if item.find("guid") else ""

                if not title or not link:
                    continue

                if any(word in title.lower() for word in KEYWORDS):
                    news_list.append({"source": name, "title": title, "link": link})

            time.sleep(2)

        except Exception as e:
            print(f"Ошибка при парсинге {name}: {e}")

    return news_list