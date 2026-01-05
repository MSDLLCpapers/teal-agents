# Teal Agents Platform

## ⚠️ Deprecation Notice

**A2A (Agent-to-Agent) Functionality Deprecated**: As part of ongoing framework migration evaluation, A2A functionality is being deprecated. The A2A feature set was experimental and never fully fleshed out or stabilized. While existing A2A implementations will continue to function for backward compatibility, new development should avoid using A2A functionality.

## Overview
The Agent Platform aims to provide two major sets of functionality:
1. A core framework for creating and deploying individual agents
2. A set of orchestrators (and supporting services) which allow you to compose
   multiple agents for more complex use cases

## Core Agent Framework
The core framework can be found in the src/sk-agents directory. For more
information, see its [README.md](src/sk-agents/README.md) or [documentation site](https://msdllcpapers.github.io/teal-agents/).

## Orchestrators
Orchestrators provide the patterns in which agents are grouped and interact with
both each other and the applications which leverage them. For more information
on orchestrators, see [README.md](src/orchestrators/README.md).

## Getting Started
Some of the demos and examples in this repository require docker images to be
built locally on your machine. To do this, once cloning this repository locally,
from the root directory
run:
```bash
$ git clone https://github.com/MSDLLCpapers/teal-agents.git
$ cd teal-agents
$ make all
```



01705a2f-5c69-40a7-baae-bb72626d8421