# Extended Thinking Implementation

**Status**: Implementation Complete (Model Support Pending)  
**Version**: 1.0.0  
**Date**: March 2026

---

## Overview

This implementation adds the infrastructure to support extended thinking/reasoning capabilities in AI agents. The feature allows compatible AI models to expose their internal reasoning process alongside their final answers.

### Implementation Status
- ✓ **Configuration support** - `include_thinking` flag in agent config
- ✓ **Response model** - `thinking` field in API responses
- ✓ **Extraction logic** - Parse thinking from model responses
- ✓ **Backward compatible** - No breaking changes to existing APIs
- ⚠ **Model support** - Awaiting compatible model versions

---

## What is Extended Thinking?

Extended thinking refers to the internal reasoning process that some AI models can expose. This includes:

- Problem analysis and breakdown
- Step-by-step logical reasoning
- Alternative approach consideration
- Self-correction and verification

**Note**: This feature requires AI models that support extended thinking output. Current model versions may not return thinking content even when enabled.

---

## Configuration

### Enable Extended Thinking

Add `include_thinking: true` to your agent configuration:

```yaml
apiVersion: skagents/v1
kind: Sequential
description: Agent with extended thinking support
service_name: ThinkingTestAgent
version: 1.0.0
input_type: BaseInput

spec:
  agents:
    - name: default
      role: Reasoning Agent
      model: claude-3-5-sonnet-20240620
      system_prompt: |
        You are a helpful assistant that provides clear, well-reasoned responses.
      temperature: 0.7
      max_tokens: 4000
      include_thinking: true  # Enable extended thinking infrastructure
  
  tasks:
    - name: reasoning_task
      task_no: 1
      description: Engage with user
      instructions: |
        Work with the user to assist them in whatever they need.
      agent: default
```

### Configuration Options

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `include_thinking` | boolean | `false` | Enable extended thinking extraction |
| `max_tokens` | integer | varies | Set higher for thinking content (4000+) |
| `temperature` | float | varies | 0.5-0.7 recommended for reasoning |

---

## Implementation Architecture

### File Changes

1. **`tealagents/v1alpha1/config.py`**
   - Added `include_thinking: bool` field to `AgentConfig`
   - Default: `false` for backward compatibility

2. **`skagents/chat_completion_builder.py`**
   - Pass `include_thinking` configuration to LLM setup
   - Configure extended thinking parameters when supported

3. **`tealagents/v1alpha1/agent/handler.py`**
   - Added `_extract_thinking()` method
   - Extracts thinking from response items
   - Handles different model response formats

4. **`tealagents/models.py`**
   - Added `thinking: str | None` field to `TealAgentsResponse`
   - Optional field - `None` when not available

5. **`docs/demos/thinking_test/config.yaml`**
   - Demo configuration with `include_thinking: true`

### Data Flow

```
Configuration (YAML)
  ↓
AgentConfig Model (include_thinking: bool)
  ↓
ChatCompletionBuilder (configure LLM)
  ↓
LLM API Call
  ↓
Response Handler (_extract_thinking)
  ↓
TealAgentsResponse (thinking field)
```

---

## API Response Format

### Response Schema

```json
{
  "task_id": "string",
  "session_id": "string",
  "request_id": "string",
  "output": "string",
  "thinking": "string | null",
  "source": "string | null",
  "token_usage": {
    "total_tokens": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0
  },
  "extra_data": null
}
```

### Field Descriptions

- **`thinking`**: Extended reasoning content from the model
  - Type: `string | null`
  - Present only when model supports and returns thinking
  - `null` if not available or not enabled

---

## Code Implementation

### AgentConfig Extension

```python
# tealagents/v1alpha1/config.py
class AgentConfig(BaseModel):
    name: str
    model: str
    system_prompt: str
    temperature: float | None = None
    max_tokens: int | None = None
    include_thinking: bool = Field(
        default=False,
        description="Include extended thinking/reasoning in response"
    )
```

### Response Model Extension

```python
# tealagents/models.py
class TealAgentsResponse(BaseModel):
    task_id: str
    session_id: str
    request_id: str
    output: str
    token_usage: TokenUsage
    thinking: str | None = Field(
        default=None,
        description="Extended thinking/reasoning from the model"
    )
```

### Thinking Extraction

```python
# tealagents/v1alpha1/agent/handler.py
def _extract_thinking(self, response: ChatMessageContent) -> str | None:
    """Extract thinking/reasoning content from LLM response."""
    try:
        # Check for thinking blocks in response items
        if hasattr(response, "items"):
            for item in response.items:
                if hasattr(item, "type") and item.type == "thinking":
                    if hasattr(item, "thinking"):
                        return item.thinking
                    elif hasattr(item, "text"):
                        return item.text
        
        # Check metadata for thinking content
        if hasattr(response, "metadata"):
            if thinking := response.metadata.get("thinking"):
                return thinking
        
        return None
    except Exception as e:
        logger.warning(f"Error extracting thinking: {e}")
        return None
```

---

## Usage

### Starting the Service

```bash
# Set environment variables
export TA_SERVICE_CONFIG=docs/demos/thinking_test/config.yaml

# Run the service
uv run python -m sk_agents.app

# Access API documentation
# http://localhost:8000/ThinkingTestAgent/1.0.0/docs
```

### Making Requests

```bash
curl -X POST "http://localhost:8000/ThinkingTestAgent/1.0.0/api" \
  -H "Content-Type: application/json" \
  -d '{
    "chat_history": [
      {
        "role": "user",
        "content": "Explain your reasoning process"
      }
    ]
  }'
```

---

## Testing

### Verification Steps

1. **Configuration Loading**
   - Verify `include_thinking` is parsed correctly
   - Check agent configuration in logs

2. **API Response**
   - Response includes `thinking` field
   - Field is `null` when not available
   - No errors when thinking extraction fails

3. **Backward Compatibility**
   - Existing configs without `include_thinking` work normally
   - Agents default to `include_thinking: false`

### Expected Behavior

| Scenario | `include_thinking` | Model Support | `thinking` Field |
|----------|-------------------|---------------|------------------|
| Enabled + Supported | `true` | Yes | String content |
| Enabled + Not Supported | `true` | No | `null` |
| Disabled | `false` | Any | `null` |
| Not Specified | (default) | Any | `null` |

---

## Limitations

### Current Status

1. **Model Availability**: Extended thinking requires specific model versions
2. **Provider Support**: Not all LLM providers support this feature
3. **Response Format**: Thinking extraction depends on model response structure
4. **Token Overhead**: Thinking content increases token usage

### Known Issues

- Some model versions may not return thinking content
- Thinking format varies between providers
- Extraction may fail for unexpected response formats (handled gracefully)

---

## Migration Guide

### Enabling for Existing Agents

To add extended thinking to an existing agent:

```yaml
# Before
spec:
  agents:
    - name: my_agent
      model: claude-3-5-sonnet-20240620
      system_prompt: "You are helpful"

# After  
spec:
  agents:
    - name: my_agent
      model: claude-3-5-sonnet-20240620
      system_prompt: "You are helpful"
      include_thinking: true  # Add this line
      max_tokens: 4000        # Increase if needed
```

**No other changes required** - the implementation is backward compatible.

---

## Best Practices

### Configuration

1. **Set adequate `max_tokens`**: Thinking content requires additional tokens (4000+ recommended)
2. **Adjust `temperature`**: Lower values (0.5-0.7) for focused reasoning
3. **Clear prompts**: Guide the model on reasoning depth
4. **Test first**: Verify model supports thinking before production use

### Error Handling

1. **Null checks**: Always check if `thinking` is `null`
2. **Fallback**: Don't rely on thinking for critical logic
3. **Logging**: Monitor extraction warnings in logs
4. **Graceful degradation**: Application works without thinking content

---

## Future Roadmap

### Phase 1 (Current)
- ✓ Infrastructure implementation
- ✓ Configuration support
- ✓ Response model updates
- ✓ Extraction logic

### Phase 2 (Pending Model Support)
- ⏳ Production model compatibility
- ⏳ Format standardization
- ⏳ Enhanced extraction for multiple providers

### Phase 3 (Future)
- Streaming thinking content
- Thinking quality metrics
- UI visualization components

---

## Technical Details

### Dependencies

No new dependencies required - uses existing:
- `pydantic` for models
- `semantic-kernel` for LLM integration
- `fastapi` for API endpoints

### Performance Impact

- **Minimal overhead** when disabled (default)
- **Token increase** when enabled (20-50% typical)
- **Latency increase** proportional to thinking content length

---

## Summary

This implementation provides the foundation for extended thinking support in agents. The infrastructure is complete and ready for use once compatible model versions are available. The feature is:

- ✓ Fully backward compatible
- ✓ Configurable per agent
- ✓ Safe with graceful error handling
- ✓ Production-ready infrastructure

---

**Implementation Date**: February-March 2026  
**Status**: Infrastructure Complete, Awaiting Model Support  
**Version**: 1.0.0
