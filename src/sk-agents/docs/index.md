# Teal Agents Framework
## Chat Completion Factories
### Background
If you hadn't noticed, Teal Agents Framework is built on top of the open source
Semantic Kernel library. Semantic Kernel leverages the concept of the Kernel to
which certain capabilities are added, which can then be used to interact with
LLMs for things like agents.

One of the core components you add to a Kernel is the ChatCompletionClient. This
object provides connection details to the specific LLM you want to enable for a
given Kernel (and in this context, an Agent). ChatCompletionClient's come in
many flavors with the ability to connect to things like standard OpenAI APIs,
Azure OpenAI and Anthropic APIs, Anthropic APIs, Ollama APIs, etc. Due to the
early nature of this product, there is limited, in-built support for the
different model hosting options (indeed only standard OpenAI at the time of
writing).

### ChatCompletion Factories
In the `ska_types` module, there is defined a ChatCompletionFactory abstract
class. Within the `chat_completion` package, there is a default implementation
of this class called `DefaultChatCompletionFactory`. Standard, widely supported
ChatCompletions should be included here, and we welcome contributions to build
out the available standard models.

### Custom Factories
There is also the ability for users to add a supplementary ChatCompletionFactory
of their own writing. To do so, you'll need to create a module with a class that
extends the ChatCompletionFactory abstract class and implement three methods:

* `get_configs` - Static method you should implement if your chat completions
   require additional configuration (via environment variables).
* `get_chat_completion_for_model_name` - Method that returns an instance of
  `ChatCompletionClientBase` for connecting to a model with a given name. When
  implemented, the model name can then be used for an agent's `model` property
  in the agent config YAML.
* `get_model_type_for_name` - Method that returns the appropriate `ModelType`
   for a given model name. This is currently only used to determine the correct
   way to calculate the token usage for a model response and if someone can
   think of a better way to do it, I'd like this method to go away.

Once you've created your custom factory, enable it by setting the two following
environment variables:

* TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE - The relative path to the python
  file containing your factory class
* TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME - The class name of your custom
  factory class

Once enabled, you have the ability to use any model your factory can handle with
a given agent by specifying the model name in the `model` field of the agent's
YAML configuration.

Included is an example of a custom chat completion factory (non-working unless you have Azure OpenAI endpoints):
::: sk_agents.chat_completion.custom.example_custom_chat_completion_factory.ExampleCustomChatCompletionFactory

### Notes
1. A custom factory takes precedence over the default factory, so if your
   factory provides a chat completion with a model name matching one in the
   default factory, yours will be selected.
2. While not exactly on-topic, there is an additional configuration property
   `TA_STRUCTURED_OUTPUT_TRANSFORMER_MODEL` which specifies which model should
   be used to convert agent results in to structured output whenever an
   `output_type` is defined. This defaults to `openai-gpt-4o` but if you've
   implemented a custom factory, you can override this property to be one of
   your models.
