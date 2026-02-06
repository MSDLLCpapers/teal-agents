FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install only Celery + Redis client
RUN pip install --no-cache-dir celery redis chromadb langchain-openai langchain-community
