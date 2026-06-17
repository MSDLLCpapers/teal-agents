# Teal Agent Platform - Assistant Orchestrator Hybrid

## Overview
This page focuses on running and debugging the Assistant Orchestrator Hybrid locally.
To read more about the philosophy, architecture, and configuration of the
orchestrator see this [README.md](../README.md).

## Prerequisites
* **Docker w/Docker Compose** - Note: Due to limitations with Podman's ability to
  access the host network in rootless mode, you will be unable to use it to
  debug the orchestrator. I recommend using Rancher Desktop, but other docker
  distributions with the ability to reference `host.docker.internal` to access
  the host network should work as well
* **[uv](https://docs.astral.sh/uv/)** - An extremely fast Python package and
  project manager

## Running the Orchestrator

### Building local container images
Prior to running the orchestrator locally, you'll need to first build the base
images. To do so, after cloning, from the repository root, run `make all`.
```bash
$ git clone https://github.com/MSDLLCpapers/teal-agents.git
$ cd teal-agents
$ make all
```

### Starting supporting services
To start up the supporting services, you'll first need to create environment
files for each of them. To do so, copy the following files in the `example`
directory to one of the same name, but without the `.example` extension.
* general.env.example
* ao-hybrid.env.example
* math.env.example
* recipient.env.example
* services.env.example
* weather.env.example

Copy each of the files, for example:
```bash
$ cd src/orchestrators/assistant-orchestrator-hybrid/example
$ cp general.env.example general.env
$ ...
```

Then change the `TA_API_KEY` value to your LLM API key for the following
files: `general.env`, `math.env`, `process.env`, `recipient.env`, and
`weather.env`.

Note: To simplify this copying, we've provided a `make` target which will copy
all of the files and add your API key. Simply run `make
build-environments-(bash | macos)` from the `example` directory and all files
will be copied for you and your API key will be updated.

Now, start all of the supporting services, except for the orchestrator itself,
by running `make debug-ao-up`.
```bash
$ make debug-ao-up
```

Note: It may take a couple of minutes for everything to start because one of the
agents has a dependency on some data that must be loaded prior to starting. If
the startup fails, it was likely due to a temporary network issue while this
data was being loaded, so just try re-running the command.

### Installing dependencies
Install all dependencies for the orchestrator by running `uv sync` from the
`orchestrator` directory.
```bash
$ cd src/orchestrators/assistant-orchestrator-hybrid/orchestrator
$ uv sync
```

### Setting up the environment
Copy the example environment file.
```bash
$ cp .env.example .env
```

### Copying the configuration file
Currently, you do not need to perform this step, but just note that in the
`orchestrator/conf` directory, there is an example configuration file. In the
future, it might be removed and you might need to copy the one from the
`example` directory.

### Running the orchestrator
Finally, you can start the orchestrator locally using `fastapi` with `uv run` or
by starting the virtual environment manually and directly invoking `fastapi`.
When starting it, you must ensure that it binds to all network interfaces so
that it can be accessed by the Kong running in a container. Additionally, 
you'll need to have it listen on port 8100.
```bash
$ uv run -- fastapi dev --host=0.0.0.0 --port=8100 jose.py
```
or
```bash
$ source .venv/bin/activate
$ fastapi dev --host=0.0.0.0 --port=8100 jose.py
```
![Output](/assets/ao-output.png)

### Testing it out
You should now be able to access the demo client app at
http://localhost:8000/client and begin chatting with all requests routed through
your locally running orchestrator.

You can test it out by asking about the temperature in Rahway:
"What's the temperature in Rahway?"

![Screenshot](/assets/example-question.png)