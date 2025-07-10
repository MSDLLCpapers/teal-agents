# Overview of Teal Agents - Agent component

This project is one component of a larger, Agent Platform, known as Teal Agents.
Its purpose is to enable the simplified creation of AI Agents using a low-code
approach consisting of a YAML configuration file and optional Python Plug-in
definitions (tools).

The application is built using FastAPI as the primary hosting framework and
Semantic Kernel for LLM integration. The source code can be found in the
`src/sk_agents` subdirectory of this workspace.

Currently, there are two versions of the YAML configuration API:
  * skagents/v1 - The original version which, while still supported, is
    deprecated (although we currently lack a stable successor).
  * skagents/v2alpha1 - An prototype version which was never stabilized but
    which does provide a base from which we'll build during this refactoring
    initiative. An example of the `v2alpha1` configuration can be found in the
    `demos/ZZ_wikipedia_demo` directory.

The main entrypoint of the application is the `app.py` file which performs some
basic setup and then, depending on the API version specified in the
configuration file, branches to either AppV1 or AppV2 (found in `appv1.py` and
`appv2.py`, respectively). For the purposes of this refactoring, we will use
only `appv2.py` as a reference.

`appv2.py` sets up the pulls in the applicable routes and handlers from the
`routes.py` file which specifies the following endpoints:
* POST /<AgentName>/<AgentVersion> - Direct REST invocation
* POST /<AgentName>/<AgentVersion>/sse - SSE streaming invocation

NOTE: There is an additional `streaming` endpoint which handles websocket
connections, but this should be considered deprecated and will not need to
considered for future development.

The route handlers parse the provided configuration file and then, based on the
defined API version, call the appropriate handlers provided in the `__init__.py`
files in the like-named directories (e.g. `skagents/v1` first invokes the handler
in the `__init__.py` file in the `skagents` subdirectory which then invokes the
handler in the `__init__.py` file in the `skagents/v1` subdirectory).  Because
`v2alpha1` was able to leverage the exising `v1` logic for the `Chat` `kind`,
no additional subdirectory was introduced, but that will change for this
refactor.  The `__init__.py` file in `skagents/v1` directory then parses the
`kind` from the configuration file and instantiates the appropriate handler (an
implementation of the `BaseHandler` class) and then passes the request on to
that handler for processing.

NOTES:
* There's a lot that goes in to instantiating the appropriate handler class
  including leveraging kernel and agent builders which define the intersection of
  this application with Semantic Kernel.
* Teal Agents is an Open Source project and, as such, it is
  implemented to generally support the publicly available LLM endpoints (e.g.
  OpenAI).  However, since we're running it inside of our corporate network and we
  have a custom LLM gateway, it can be extended with custom implementations of the
  `ChatCompletionFactory` class available in `src/sk_agents/ska_types` directory.
  For us, this has been done and the custom implementation can be found in the
  `customization/teal-agents/merck_custom_chat_completion_factory.py` file.
* This application is designed in a very extendable manner and its
  runtime behavior is heavily dependent on both the provided configuration file as
  well as a number of environment variables. Every attempt should be made to
  continue developing this in the same, open and extendable manner.
* This application strives to maintain backwards compatibility with currently
  available API versions (e.g. `skagents/v1`) and, as such, whenever performing
  any refactoring, you should ensure that the new functionality is isolated and
  does not change anything about existing functionality.
* The Agent component of Teal Agents is one piece of a much larger overall
  platform.  That said, it is also a standalone component.  Since it exposes
  agents as APIs, it can run by itself and can be invoked directly, but it's also
  common for it to be invoked by "Orchestrators" which are different components
  which provide multi-agent orchestration capabilities. It's important to keep
  this in mind when designing any new feature.