"""Клиент OpenAI-совместимого API эмбеддингов Cloud.ru."""

import logging
import math

from curl_cffi import CurlOpt, requests
from curl_cffi.requests.exceptions import ConnectionError, RequestException, SSLError, Timeout
from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import CLOUDRU_API_KEY, CLOUDRU_DOH_URL, CLOUDRU_EMBEDDING_MODEL, CLOUDRU_NETWORK_INTERFACE, EMBEDDING_DIMENSIONS

logger = logging.getLogger(__name__)
EMBEDDINGS_URL = "https://foundation-models.api.cloud.ru/v1/embeddings"
EMBEDDING_INPUT_BYTES = 4_000


class CloudRuError(RuntimeError):
    """Ошибка конфигурации, запроса или ответа Cloud.ru."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class _TemporaryCloudRuError(CloudRuError):
    """Временный сбой при запросе эмбеддинга."""


class CloudRuEmbeddingClient:
    """Получает векторы Qwen для семантической дедупликации."""

    def __init__(self) -> None:
        self._api_key = CLOUDRU_API_KEY.strip()
        if not self._api_key:
            raise CloudRuError("Укажите CLOUDRU_API_KEY в .env и перезапустите веб-сервер.")
        curl_options = {CurlOpt.DOH_URL: CLOUDRU_DOH_URL} if CLOUDRU_DOH_URL else None
        self._session = requests.Session(interface=CLOUDRU_NETWORK_INTERFACE or None, curl_options=curl_options)

    def close(self) -> None:
        """Закрывает HTTP-сессию клиента."""
        self._session.close()

    def embed(self, text: str) -> list[float]:
        """Возвращает числовой вектор, пригодный для косинусного поиска."""
        article = text.strip()
        if not article:
            raise ValueError("Для эмбеддинга нужен текст статьи")
        excerpt = article.encode()[:EMBEDDING_INPUT_BYTES].decode("utf-8", errors="ignore")
        response = self._request(excerpt)
        try:
            vector = response.json()["data"][0]["embedding"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise CloudRuError("Cloud.ru вернул ответ без эмбеддинга") from None
        if not isinstance(vector, list) or len(vector) != EMBEDDING_DIMENSIONS:
            raise CloudRuError(f"Ожидался эмбеддинг Cloud.ru из {EMBEDDING_DIMENSIONS} координат")
        if any(type(value) not in (int, float) for value in vector):
            raise CloudRuError("Эмбеддинг Cloud.ru содержит нечисловые координаты")
        try:
            result = [float(value) for value in vector]
        except OverflowError:
            raise CloudRuError("Координаты эмбеддинга Cloud.ru выходят за допустимый диапазон") from None
        if not all(map(math.isfinite, result)) or not any(result):
            raise CloudRuError("Cloud.ru вернул эмбеддинг, непригодный для косинусного сравнения")
        return result

    @retry(
        retry=retry_if_exception_type(_TemporaryCloudRuError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=4),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _request(self, excerpt: str) -> requests.Response:
        try:
            response = self._session.post(
                EMBEDDINGS_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": CLOUDRU_EMBEDDING_MODEL, "input": [excerpt], "encoding_format": "float"},
                timeout=(5, 45),
                allow_redirects=False,
            )
        except SSLError:
            raise CloudRuError("Не удалось проверить TLS Cloud.ru") from None
        except (Timeout, ConnectionError):
            raise _TemporaryCloudRuError("Сетевой сбой при запросе эмбеддинга Cloud.ru") from None
        except RequestException:
            raise CloudRuError("Не удалось отправить запрос эмбеддинга Cloud.ru") from None

        status = response.status_code
        if status in {408, 429} or 500 <= status < 600:
            raise _TemporaryCloudRuError(f"Cloud.ru временно не выдаёт эмбеддинги (HTTP {status})", status)
        if status in {401, 403}:
            raise CloudRuError(f"Cloud.ru отклонил доступ (HTTP {status}). Проверьте CLOUDRU_API_KEY и доступ к модели.", status)
        if status == 402:
            raise CloudRuError("Cloud.ru вернул HTTP 402. Проверьте доступ к эмбеддингам в Foundation Models.", status)
        if not 200 <= status < 300:
            raise CloudRuError(f"Cloud.ru не выдал эмбеддинг для {CLOUDRU_EMBEDDING_MODEL} (HTTP {status})", status)
        return response
