# Collab Orchestrator - Local Development Guide

## Introduction

The Collab Orchestrator is a service designed to coordinate and manage various AI agents and tools, facilitating complex collaborative tasks. This guide provides instructions for setting up and running the Collab Orchestrator and its associated services locally using Docker Compose.

## Prerequisites

Before you begin, ensure you have the following installed on your system:

  * **[Rancher Desktop](https://rancherdesktop.io/)**: Includes Docker Engine and Docker Compose.
  * **Make**: (Commonly pre-installed on Linux and macOS. For Windows, consider using Git Bash or MinGW which includes `make`).
  * **OpenAI API Key**: This is required for the orchestrator's GPT integration.

## Setup and Running the Orchestrator

Follow these steps to get the Collab Orchestrator and its dependencies running:

1.  **Build Docker Images**
    Navigate to the root directory of your project (the top-level folder containing `src/`) and execute the `make all` command. This will build the Docker images for all services defined in the project.

    ```bash
    cd /path/to/your/project/root # Replace with your actual project root
    make all
    ```

2.  **Access the Docker Compose Directory**
    Change your current working directory to where the main `compose.yaml` for the orchestrator examples is located:

    ```bash
    cd src/orchestrators/collab-orchestrator/orchestrator/example
    ```

3.  **Configure Environment Variables**
    Set up the necessary environment variables, including your OpenAI API key, which will be used by the orchestrator. Choose the command appropriate for your operating system:

      * **For macOS:**
        ```bash
        make build-environments-macos
        ```
      * **For Linux / WSL (Bash):**
        ```bash
        make build-environments-bash
        ```

    Follow the prompts in your terminal to enter your GPT API key.

4.  **Start Services**
    Initiate all services defined in the `compose.yaml` file.

    ```bash
    make all-up
    ```

    **Note on Startup:** Due to potential startup race conditions between services, the `co` (Collab Orchestrator) service might occasionally fail to connect to its dependencies on the first attempt. If you observe errors related to connection refused for `co` during initial startup, you can restart just the orchestrator service:

    ```bash
    docker compose restart co
    ```

## Accessing the Orchestrator and Client

Once the services are running, you can interact with the Collab Orchestrator:

1.  **Client User Interface (Optional)**
    Open the HTML client in your web browser at:

    ```
    http://localhost:8000/client
    ```

2.  **API Documentation (Swagger UI)**
    Access the OpenAPI (Swagger) documentation for the Collab Orchestrator's API endpoints in your browser:

    ```
    http://localhost:8100/CollaborationOrchestrator/0.1/docs
    ```