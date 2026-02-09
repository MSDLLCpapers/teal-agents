FROM python:3.12-slim

RUN apt-get update \
    && apt-get install --no-install-recommends -y curl git \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000 skagent && \
    useradd -g 1000 -u 1000 -m skagent && \
    mkdir /app && \
    chown -R skagent:skagent /app

USER skagent

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV PATH=$PATH:/home/skagent/.local/bin

WORKDIR /app

COPY --chown=skagent:skagent shared/ska_utils /app/shared/ska_utils
COPY --chown=skagent:skagent src/orchestrators/assistant-orchestrator-hybrid/orchestrator /app/src/orchestrators/assistant-orchestrator-hybrid/orchestrator

WORKDIR /app/src/orchestrators/assistant-orchestrator-hybrid/orchestrator

RUN uv sync --frozen --no-dev


# Make entrypoint executable
RUN chmod +x ao-celery.sh

# Set entrypoint
ENTRYPOINT ["./ao-celery.sh"]
