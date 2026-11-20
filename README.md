# parser-ecom

### Развёртывание на сервере

Нужны Docker Engine и Docker Compose. На Linux проверьте `sysctl vm.max_map_count`.
Если значение ниже `1048576`, примените `sudo sysctl -w vm.max_map_count=1048576`
и сохраните это значение в настройках `sysctl` хоста для следующих перезапусков.
Рекомендуемый объём памяти для Docker — от 4 ГБ. [Требования Elasticsearch](https://www.elastic.co/guide/en/elasticsearch/reference/8.19/docker.html#docker-prod-prerequisites).

Создайте `.env` по образцу `.env.example`, если файла ещё нет. Заполните
`GIGACHAT_CLIENT_ID`, `GIGACHAT_CLIENT_SECRET` и `CLOUDRU_API_KEY`.

```sh
docker compose up -d --build --wait
docker compose ps
```

Если Docker Hub недоступен, можно задать в `.env`
`APP_PYTHON_IMAGE=mirror.gcr.io/library/python:3.14-slim`.

Compose запускает Elasticsearch и один веб-процесс с планировщиком. При старте
приложение создаёт индекс и политику ILM. Данные хранятся в постоянном томе
`elasticsearch-data`. Elasticsearch доступен внутри сети Compose.

Лента открывается на `http://127.0.0.1:8000` на самом сервере. Порт задаётся
через `APP_PORT`. Для доступа со своего компьютера можно использовать SSH-туннель:

```sh
ssh -N -L 18000:127.0.0.1:8000 user@server
```

Откройте `http://127.0.0.1:18000` и нажмите «Обновить». Для доступа по домену
настройте обратный прокси с HTTPS и авторизацией, чтобы ограничить доступ к запуску
обновлений. `APP_BIND_IP` задаёт адрес публикации веб-порта на хосте.

```sh
docker compose logs -f app           # журналы
docker compose exec app python bot.py # ручной проход
docker compose down                  # остановка с сохранением тома
```

После изменения ключей выполните `docker compose up -d --wait`, чтобы Compose
применил новые настройки. Планировщик работает внутри `app`.

### Локальный запуск Python

Используйте Python 3.11 или новее. Создайте `.env` по образцу `.env.example`, если
файла ещё нет, и заполните настройки GigaChat и Cloud.ru из разделов ниже.

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

```sh
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --wait elasticsearch
python -m app.elastic
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

По умолчанию клиент подключается к `http://127.0.0.1:9200`. Если нужен другой адрес,
добавьте `ES_URL` в `.env` (см. `.env.example`). Локальный Compose-файл публикует
порт Elasticsearch только на `127.0.0.1`.

### Срок хранения

В ленте показываются статьи за последние 30 дней от публикации. Пайплайн пропускает
более старые записи RSS. В Elasticsearch 8 статьи хранятся в суточных индексах
`news-day-qwen-ГГГГ-ММ-ДД`, которые объединяет алиас `news`. Политика ILM `news-retention`
удаляет дневной индекс через 30 дней после окончания его суток по UTC, при ближайшей
проверке ILM.

При переходе со старого одиночного индекса `news` свежие статьи из него видны вместе
с суточными индексами. Старый индекс без собственной политики получает 30 дней с
момента перехода. Когда имя `news` освободится, следующий запуск подключит под этим
именем алиас ко всем оставшимся суточным индексам.

Ранее сохранённые статьи из `news-day-ГГГГ-ММ-ДД` видны в ленте и учитываются при
проверке URL. Семантический поиск сравнивает только векторы Qwen с 1024 координатами.

### GigaChat

Добавьте в `.env` значения `GIGACHAT_CLIENT_ID` и `GIGACHAT_CLIENT_SECRET` из личного
кабинета и укажите `GIGACHAT_SCOPE` для вашего проекта. По умолчанию используется
`GIGACHAT_API_PERS`. Пример полей есть в `.env.example`.

Docker-образ включает стандартные доверенные сертификаты и официальный корневой
сертификат НУЦ Минцифры для проверки TLS GigaChat. При запуске Python на хосте
укажите путь к такому PEM-файлу в `GIGACHAT_CA_BUNDLE`.
[Инструкция GigaChat по сертификатам](https://developers.sber.ru/docs/ru/gigachat/certificates).

### Cloud.ru Foundation Models

Добавьте API-ключ Foundation Models в `CLOUDRU_API_KEY` в `.env`. Модель
`Qwen/Qwen3-Embedding-0.6B` получает начальный фрагмент статьи для сравнения с
другими публикациями. Выжимку по-прежнему формирует GigaChat.
[Быстрый старт Cloud.ru](https://cloud.ru/docs/foundation-models/ug/topics/quickstart).

Опциональные `CLOUDRU_NETWORK_INTERFACE` и `CLOUDRU_DOH_URL` задают интерфейс
и DNS-over-HTTPS только для запросов Cloud.ru, если VPN мешает доступу к API.
В Compose для выбора интерфейса внутри контейнера используется
`CLOUDRU_CONTAINER_NETWORK_INTERFACE`. Пустое значение использует маршрут Docker.

### Обновление ленты

После запуска Elasticsearch и настройки GigaChat и Cloud.ru выполните `python bot.py` или
`python -m app.pipeline` для одного прохода. Для работы по расписанию без веб-ленты
выполните `python -m app.scheduler`.
Период по умолчанию составляет 60 минут (`REFRESH_INTERVAL_MINUTES`), порог
косинусного сходства — 0.92 (`SEMANTIC_SIMILARITY_THRESHOLD`). Уровень журналирования
задаётся через `LOG_LEVEL`. Локальный lock-файл защищает от одновременных запусков
из одного каталога проекта. Для записи без даты в ленте используется время загрузки.

### Веб-лента

FastAPI использует синхронный пайплайн в рабочем потоке и предоставляет описание
`POST /api/refresh` в `/docs`. Кнопка
«Обновить» ждёт завершения прохода и открывает начало ленты. Планировщик запускается
внутри веб-процесса, поэтому для этого режима достаточно одного процесса Uvicorn.
Кнопка «Скопировать» переносит в буфер выжимку и ссылку на источник. Если браузер
не даёт доступ к буферу, появляется окно с выделенным текстом для ручного копирования.
