# A Full Example
In this example directory, there is a complete working implementation of the
Assistant Orchestrator, Assistant Orchestrator Services, Agent Selector,
Fallback Agent, three regular agents, a test client, and all supporting
services.

The purpose of the example is to both provide a playground where you can test
out the Agent Platform and to enable development of both the Orchestrator and
Services components by providing a local testing setup.

The complete setup looks something like this:
![Example Architecture](/assets/example-arch.png)

## Prerequisites

### Docker and Docker Compose
You'll need Docker and Docker Compose. Note, if running the ENTIRE thing, you
can probably get this to work with Podman as well. Unfortunately, Podman has
some limitations about accessing the host network from a container, and
therefore to perform development of the system, you'll need to use something
like Rancher Desktop.

### Building the Base Images
Prior to running the example, you'll need to build three base docker images
locally. To do so, from the root of the repository, simply run:
```bash
$ git clone https://github.com/MSDLLCpapers/teal-agents.git
$ cd teal-agents
$ make all
```

### Configuring the Environment

- You can skip this step and go to "Running the Example" step

Before starting the example, you'll first need to create environment files for
each of them. To do so, copy the following files in the `example` directory to
one of the same name, but without the `.example` extension.
* general.env.example
* ao-hybrid.env.example
* math.env.example
* recipient.env.example
* services.env.example
* test-agent.env.example
* weather.env.example

to generate the env files:

On windows/linux you can run:

```bash
$ cd src/orchestrators/assistant-orchestrator/example
$ make build-environments-bash
$ ...
```

On MacOS:

```bash
$ cd src/orchestrators/assistant-orchestrator/example
$ make build-environments-macos

```

## Running the Example

Make sure you are in the example directory if not run the included cd command first from the root. then rn the make command:

Windows/Linux:

```bash
$ cd src/orchestrators/assistant-orchestrator/example
$ make build-full-example-system-bash
```

MacOS:

```bash
$ cd src/orchestrators/assistant-orchestrator/example
$ make build-full-example-system-macos
```

This will build and start approximately 17 containers on your machine. For
details, see the [Compose File](./compose.yaml).

To access your test environment, once started, open your browser to
http://localhost:8000/client, and begin chatting away.

Once you are done, to shut everything down, you can simply run

```bash
$ make all-down
```

## Update API Keys

if you need to update you api keys you can use the command:

Windows/Linux

```bash
$ make prompt-api-keys-bash
```

MacOS:

```bash
$ make prompt-api-keys-bash
```

## Deploy Changes

when developing new code and need to deploy changes like for client you can run:

```bash
$ make deploy-updated-code
```


## Including Your Own Agent
To include your own agent in the example, you can include agent configuration
files in the `test-agent` directory. Note that your agent must be named
`TestAgent` and be version `0.1` for it to be picked up by the orchestrator.
To start the example with your agent, you'll need to run:
```bash
$ make test-agent-up
```

Once you are done, to shut everything down, you can simply run
```bash
$ make test-agent-down
```

### Debugging Your Test Agent
Additionally, you can debug your test agent while running the example
application. In this case, you'll need to start the `sk-agents` application on
your local machine with the appropriate configuration and environment setup.

Note: You must start your agent on host `0.0.0.0` and port `8106` for it to be
accessible to the orchestrator. Additionally, you must start your agent before
starting all other components of the example.

For example, from within the `sk-agents` project, you could create the following
`config.yaml` file in the `agents` subfolder:
```yaml
apiVersion: skagents/v1
kind: Sequential
description: >
  An agent great at writing poetry
service_name: TestAgent
version: 0.1
input_type: BaseInput
spec:
  agents:
    - name: default
      role: Default Agent
      model: gpt-4o-2024-05-13
      system_prompt: >
        You are a helpful assistant.
  tasks:
    - name: action_task
      task_no: 1
      description: Write a poem
      instructions: >
        Write a short poem given the user's request
      agent: default
```

You would then need to set up your environment as follows:
```text
TA_API_KEY=<Your API Key>
TA_SERVICE_CONFIG=agents/config.yaml
```

Then start your agent locally:
```shell
src/sk-agents$ uv run -- fastapi dev --host=0.0.0.0 --port=8106
```

You can then start the remaining components of the example:
```shell
src/orchestrators/assistant-orchestrator/example$ make debug-test-agent-up
```

## Other Make Targets
In addition to `all-up` and `all-down`, there are a number of other `make`
targets to achieve various tasks, including:
* `debug-ao-[up/down]` - Enable [debugging of Orchestrator](../orchestrator/README.md)
* `debug-services-[up/down]` - Enable [debugging of Services](../services/README.md)
* `test-agent-[up/down]` - Enable testing of an additional agent you define by
  adding configuration to the `test-agent` directory.
* `debug-test-agent-[up/down]` - Enable debugging of an agent you're running
  on your machine, locally (Note: You must start your agent on host `0.0.0.0`
  and port `8106`)

## Other Helpful Links
When running, there are a number of other handy links to observe the system,
including:
* [Kong API Gateway](http://localhost:8002/) - To view configured agent services
  and routes (This is the Agent Catalog)
* [DynamoDB Admin](http://localhost:8400/) - For viewing persistent storage of
  tickets and chat history
* [Aspire Dashboard]() - To view traces and logs from the Orchestrator,
  Services, and Agents. Note you'll actually have to extract the correct URL
  from your Docker logs for the `aspire` container as the dashboard requires a
  valid token. Run `docker logs <container id>` and then search for the line
  `Login to the dashboard at <url>` to retrieve the URL