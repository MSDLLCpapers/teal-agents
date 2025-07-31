# Teal Agents Platform
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
