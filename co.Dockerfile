# Use a slim Python 3.13 base image
FROM python:3.13-slim

# Install necessary system packages
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl git \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user and group for security
RUN groupadd -g 1000 skagent && \
    useradd -g 1000 -u 1000 -m skagent && \
    mkdir /app && \
    chown -R skagent:skagent /app

# Switch to the non-root user
USER skagent

# Copy the uv installer and add it to the PATH
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV PATH=$PATH:/home/skagent/.local/bin

# Set the working directory inside the container
WORKDIR /app

# Copy the shared ska_utils library
COPY --chown=skagent:skagent shared/ska_utils /app/shared/ska_utils
# Copy the entire collab-orchestrator directory
COPY --chown=skagent:skagent src/orchestrators/collab-orchestrator/orchestrator /app/src/orchestrators/collab-orchestrator/orchestrator

# Set the working directory to the root of your orchestrator application
WORKDIR /app/src/orchestrators/collab-orchestrator/orchestrator

# Install Python dependencies using uv
RUN uv sync --frozen --no-dev

# Expose the port your application will listen on
EXPOSE 8000

# Make the run script executable
RUN chmod +x co.sh

# Set the entrypoint to your run script
ENTRYPOINT ["./co.sh"]