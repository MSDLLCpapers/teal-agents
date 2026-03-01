# Teal Agent Platform - Assistant Orchestrator Hybird
## User Context

Generative AI can be more robust and engaging when it knows more about the user
with which it is interacting. As such, the Assistant Orchestrator provides for
the ability to store user-specific context information in either a `transient`
(session-specific) or `persistent` manner. This context is then retrieved during
user interactions and made available to agents which can leverage it to provide
these more personalized experiences.

### Enabling User Context for an Agent

To enable user context for an agent, your agent's `input_type` field must
include an attribute named `user_context` which is a simple dictionary of
key/value string pairs corresponding to user context. To simplify this, for
agent builders, the core framework contains the standard type
`BaseInputWithUserContext`.

Example agent configuration:
```yaml
apiVersion: skagents/v1
kind: Sequential
description: >
  A weather chat agent
service_name: WeatherBot
version: 0.1
input_type: BaseInputWithUserContext
...
```

Once available, the user context can be referenced from within agent
instructions. For example, to reference the context with the key `User Location`
directly, you could include:

```yaml
      instructions: >
        Work with the user to assist them in whatever they need.
        
        The following user context was provided:
          User Location: {{user_context["User Location"]}}
```

If you wanted to include all available user context, you could loop through the
context dictionary:

```yaml
      instructions: >
        Work with the user to assist them in whatever they need.

        The following user context was provided:
          {% for key, value in user_context.items() %}
            {{key}}: {{value}}
          {% endfor %}
```

### Persistent User Context
Persistent user context is stored and retrieved via the Assistant Orchestrator
Service. It provides the standard CRUD endpoints for managing user context:

* Create - `POST /services/v1/{orchestrator name}/users/{user ID}/context`
* Read - `GET /services/v1/{orchestrator name}/users/{user ID}/context`
* Update - `PUT /services/v1/{orchestrator name}/users/{user ID}/context/{key}`
* Delete - `DELETE /services/v1/{orchestrator name}/users/{user ID}/context/{key}`

All persistent context for a particular orchestrator/user is loaded at session
start.

### Transient User Context
Transient user context is not retained beyond the user's current session.
Transient context can be set from within agent plug-ins by including a
"Context Directive" in the `extra_data` returned by an agent. The following
directives are available for managing transient context:

* set-context - To add or update a transient context key/value pair
* add-context - To add a new transient context key/value pair
* update-context - To update an existing transient context key/value pair
* delete-context - To remove a transient context key/value pair

Use the `extra_data_collector` from within an agent plug-in to include a context
directive. For example, if you built a Weather Agent which could retrieve
location-specific weather information for a user, you might want to set a "User
Location" context item so that future interactions within the same session do
not require the user to specify their location (assuming that if they asked once
additional, similar requests would be for the same location). To achieve this,
your weather plugin could leverage the `set-context` directive to store the
user's location.

```python
self.extra_data_collector.add_extra_data("set-context", f"User Location:{location.value}")
```

In this example, the `set-context` is the extra data key, with a value of "User
Location:{location.value}" indicating that the `User Location` key in context
should be set to the varible `location.value` value.

Other context directives follow a similar pattern where you would pass the
directive as the key, and the key/value as a string separated by a colon. For
context deletion, you would only specify the key to delete.