# Merck API Integration Setup Guide

This guide walks you through setting up and testing the FileAssistant agent with Merck's custom GPT API integration.

## Prerequisites

- Python 3.12+
- Access to Merck's internal GPT API
- Valid X-Merck-APIKey

## Step-by-Step Setup

### 1. Configure Environment Variables

**Create and edit the `.env` file** in the `ray_tests/simple_agent_1` directory:

```bash
# From the test directory
cd ray_tests/simple_agent_1

# Copy the example file
cp .env.example .env

# Edit with your credentials
# Replace MERCK_API_KEY with your actual key
nano .env  # or use your preferred editor
```

Update these values in `.env`:
```bash
MERCK_API_KEY=your-actual-x-merck-apikey
MERCK_API_ROOT=https://iapi-test.merck.com/gpt/v2
```

### 2. Install Dependencies

From the `src/sk-agents` directory (only needed once):

```bash
cd ../../src/sk-agents
uv sync

# Or using pip
pip install -e .
```

### 3. Test the Integration

Run the integration test from the test directory:

```bash
cd ../../ray_tests/simple_agent_1
python test_merck_integration.py
```

**Expected Output:**
```
======================================================================
  Merck API Integration Tests
======================================================================

✓ Found .env file at: /path/to/teal-agents/src/sk-agents/.env

======================================================================
  Test 1: Direct MerckChatCompletion Client
======================================================================

[1/3] Initializing MerckChatCompletion client...
✓ Client initialized

[2/3] Creating test chat history...
✓ Chat history created

[3/3] Making API call...
✓ API call successful!

----------------------------------------------------------------------
Response from Merck API:
----------------------------------------------------------------------
Hello from Merck API!
----------------------------------------------------------------------

✓ Test 1 PASSED: Direct client works correctly!

... (similar for Test 2)

======================================================================
  ✓ All tests PASSED! Integration is working correctly.
======================================================================
```

### 4. Start the Agent

**New!** You can now run the agent directly from the test directory:

```bash
# From ray_tests/simple_agent_1
python run_agent.py
```

Or make it executable:

```bash
chmod +x run_agent.py
./run_agent.py
```

The agent will start on `http://localhost:8000`

**Note:** The standalone runner automatically:
- Loads the local `.env` file
- Sets up Python paths correctly
- Changes to the test directory
- Starts the FastAPI server

### 5. Test the Agent API

#### Option A: Using Swagger UI

Open your browser to:
```
http://localhost:8000/FileAssistant/0.1/docs
```

Try the `/invoke` endpoint with this request body:
```json
{
  "input": "What files are in the data directory?"
}
```

#### Option B: Using curl

```bash
curl -X POST "http://localhost:8000/FileAssistant/0.1/invoke" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "List all the files and tell me what they contain"
  }'
```

#### Option C: Using Python requests

```python
import requests

response = requests.post(
    "http://localhost:8000/FileAssistant/0.1/invoke",
    json={"input": "What files are available?"}
)

print(response.json())
```

## Architecture Overview

The integration follows this flow:

```
User Request
    ↓
FastAPI Endpoint (app.py)
    ↓
Teal Agents Handler
    ↓
KernelBuilder
    ↓
ChatCompletionBuilder
    ↓
MerckChatCompletionFactory (your custom factory)
    ↓
MerckChatCompletion (your custom client)
    ↓
Merck API (https://iapi-test.merck.com/gpt/v2)
```

## Key Files Created

1. **`merck_chat_completion.py`** - Custom Semantic Kernel chat completion client
   - Implements async HTTP calls to Merck API
   - Handles message formatting and response parsing
   - Compatible with Semantic Kernel interfaces

2. **`merck_chat_completion_factory.py`** - Factory for creating clients
   - Registers supported models
   - Provides configuration requirements
   - Creates MerckChatCompletion instances

3. **`config.yaml`** - Updated to use `gpt-5-2025-08-07`

4. **`.env`** - Environment configuration with Merck API settings

5. **`test_merck_integration.py`** - Integration test script

## Troubleshooting

### Issue: "MERCK_API_KEY not configured"

**Solution:** Make sure you've updated the `.env` file with your actual API key:
```bash
MERCK_API_KEY=your-actual-key-here
```

### Issue: "HTTP 401 Unauthorized"

**Solution:** Your API key may be invalid or expired. Verify:
1. The key is correct
2. The key has not been revoked
3. You have access to the Merck API endpoint

### Issue: "HTTP 404 Not Found"

**Solution:** Check that the API endpoint URL is correct:
```bash
MERCK_API_ROOT=https://iapi-test.merck.com/gpt/v2
```

### Issue: "Model not supported"

**Solution:** The model name must be one of:
- `gpt-5-2025-08-07`
- `gpt-4o`
- `gpt-4o-mini`

Update `config.yaml` if needed.

### Issue: Import errors when running tests

**Solution:** Make sure you're running from the project root and dependencies are installed:
```bash
cd /path/to/teal-agents
cd src/sk-agents
uv sync
cd ../../ray_tests/simple_agent_1
python test_merck_integration.py
```

## Next Steps

Once the integration is working:

1. **Customize the agent** - Modify `config.yaml` to change behavior
2. **Add more plugins** - Create additional tool plugins
3. **Test with real data** - Add files to the `data/` directory
4. **Scale up** - Deploy with proper authentication and monitoring

## Support

For issues specific to:
- **Teal Agents platform**: See main README.md
- **Merck API**: Contact your API administrator
- **Custom integration**: Review the code comments in the integration files

## Additional Resources

- [Teal Agents Documentation](../../../README.md)
- [Semantic Kernel Documentation](https://learn.microsoft.com/en-us/semantic-kernel/)
- [Plugin Development Guide](../../../docs/demos/03_plugins/README.md)
