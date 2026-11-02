FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# curl para o healthcheck do compose.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY . .
RUN pip install --upgrade pip \
    && pip install -e ".[dev]"

CMD ["uvicorn", "compras.main:app", "--host", "0.0.0.0", "--port", "8000"]
