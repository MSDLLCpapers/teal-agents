FROM python:3.12-slim

RUN apt-get update \
    && apt-get install --no-install-recommends -y curl git \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000 skagent && \
    useradd -g 1000 -u 1000 -m skagent && \
    mkdir /app && \
    chown -R skagent:skagent /app

USER skagent

WORKDIR /app

COPY --chown=skagent:skagent src/orchestrators/assistant-orchestrator-hybrid/orchestrator/content_update /app/content_update


# ENV PYTHONUNBUFFERED=1 \
#     PYTHONDONTWRITEBYTECODE=1

# Install only Celery + Redis client
RUN pip install --no-cache-dir celery redis chromadb langchain-openai langchain-community

EXPOSE 8000
