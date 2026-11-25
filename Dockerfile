ARG APP_PYTHON_IMAGE=python:3.14-slim
FROM ${APP_PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GIGACHAT_CA_BUNDLE=/opt/parser-ecom/gigachat-ca.pem \
    PIPELINE_LOCK_PATH=/tmp/parser-ecom-refresh.lock

WORKDIR /opt/parser-ecom

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY docker/russian-trusted-root-ca.crt ./
RUN (cat "$(python -m certifi)" && printf '\n' && cat russian-trusted-root-ca.crt) > "$GIGACHAT_CA_BUNDLE"

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY app/ ./app/
COPY bot.py config.py parser.py ./

USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
