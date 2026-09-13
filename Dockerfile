# syntax=docker/dockerfile:1
# Development is the default target for Compose; production is available with
# `docker build --target production .`.
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    libgomp1 \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-hin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN groupadd --system adam && useradd --system --gid adam --create-home adam

COPY pyproject.toml ./
COPY README.md ./
COPY adam ./adam
RUN pip install --upgrade pip setuptools wheel && pip install ".[voice]"

RUN mkdir -p /app/.adam_storage && chown -R adam:adam /app

FROM base AS development
COPY tests ./tests
RUN pip install ".[dev,voice]"
USER adam
EXPOSE 8000
CMD ["uvicorn", "adam.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM base AS production
COPY tests ./tests
USER adam
EXPOSE 8000
CMD ["adam", "serve", "--host", "0.0.0.0", "--port", "8000"]
