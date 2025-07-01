
# Technical Overview

This document provides a technical overview of the Teal Agents framework, a config-first framework for creating and deploying AI-powered agents.

## Project Structure

The project is organized as follows:

- **`customization/`**: This directory contains custom components, such as the `merck_custom_chat_completion_factory.py` file, which is used to integrate with an on-network LLM gateway.
- **`demos/`**: This directory contains a number of example configurations for different types of agents.
- **`src/sk_agents/`**: This directory contains the source code for the Teal Agents framework.
- **`tests/`**: This directory contains the tests for the project.

## Core Concepts

The Teal Agents framework is built around the following core concepts:

- **Agents**: Agents are the basic building blocks of the framework. They are responsible for processing input, interacting with the user, and generating output.
- **Plugins**: Plugins are used to extend the functionality of agents. They can be used to add new tools and capabilities to agents.
- **Types**: Types are used to define custom data structures for input and output.
- **Configuration**: The framework is config-first, which means that the majority of the setup is done in a YAML configuration file.

## Architecture

The Teal Agents framework is based on the following architecture:

- **FastAPI**: The framework uses FastAPI to expose a REST API for invoking agents.
- **Semantic Kernel**: The framework uses Semantic Kernel for its core LLM integration.
- **Custom Chat Completion Factory**: The framework uses a custom chat completion factory to integrate with an on-network LLM gateway.

## Workflow

The following is a high-level overview of the workflow for creating and deploying an agent:

1. **Create a configuration file**: The first step is to create a YAML configuration file for the agent. This file specifies the agent's name, description, input and output types, and the plugins that it uses.
2. **Create custom plugins and types (optional)**: If the agent requires any custom functionality, you can create custom plugins and types.
3. **Deploy the agent**: Once the agent is configured, you can deploy it using Docker.

## Key Files

The following are some of the key files in the project:

- **`src/sk_agents/app.py`**: This is the main entry point of the application.
- **`src/sk_agents/routes.py`**: This file defines the API routes for the application.
- **`src/sk_agents/skagents/v1/agent_builder.py`**: This file is responsible for building agents.
- **`src/sk_agents/skagents/v1/sk_agent.py`**: This file contains the implementation of the `SKAgent` class.
- **`src/sk_agents/plugin_loader.py`**: This file is responsible for loading plugins.
- **`src/sk_agents/type_loader.py`**: This file is responsible for loading custom types.
- **`customization/teal-agents/merck_custom_chat_completion_factory.py`**: This file defines a custom chat completion factory that uses an internal LLM gateway.
- **`demos/01_getting_started/config.yaml`**: This file is an example of an agent configuration file.
