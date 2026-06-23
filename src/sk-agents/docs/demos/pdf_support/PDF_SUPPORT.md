# PDF Support Implementation

**Status**: ✓ Complete  
**Version**: 1.0.0  
**Date**: February 2026

---

## Overview

This implementation adds support for PDF document processing in AI agents, enabling agents to analyze, extract information from, and answer questions about PDF documents. The feature integrates PDF handling capabilities into the agent framework.

### Key Features
- ✓ **PDF document input** - Accept PDF files as input
- ✓ **Text extraction** - Extract text content from PDFs
- ✓ **Multi-page support** - Process documents with multiple pages
- ✓ **Question answering** - Answer questions about PDF content
- ✓ **Custom chat completion** - Enhanced model selection for PDF tasks

---

## What is PDF Support?

PDF support enables agents to:
- Read and process PDF documents
- Extract text and structural information
- Analyze document content
- Answer questions based on PDF content
- Support various PDF formats and encodings

### Use Cases

- **Document Analysis**: Analyze contracts, reports, and papers
- **Information Extraction**: Extract specific data from forms and documents
- **Q&A Systems**: Answer questions about document content
- **Document Summarization**: Generate summaries of PDF content
- **Content Search**: Find specific information within documents

---

## Configuration

### Basic PDF Agent Setup

```yaml
apiVersion: skagents/v1
kind: Sequential
description: Agent with PDF processing capabilities
service_name: PDFAgent
version: 1.0.0
input_type: BaseInput

spec:
  agents:
    - name: pdf_processor
      role: PDF Analysis Agent
      model: claude-3-5-sonnet-20240620
      system_prompt: |
        You are a helpful assistant that can analyze PDF documents.
        Extract and interpret information from provided PDFs accurately.
      temperature: 0.7
      max_tokens: 4000
  
  tasks:
    - name: analyze_pdf
      task_no: 1
      description: Analyze PDF document
      instructions: |
        Analyze the provided PDF document and answer the user's questions.
        Provide accurate information based on the document content.
      agent: pdf_processor
```

### Configuration Options

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `model` | string | required | LLM model with multimodal support |
| `max_tokens` | integer | varies | Set higher for complex documents (4000+) |
| `temperature` | float | varies | 0.5-0.7 for factual extraction, higher for analysis |

---

## Implementation Architecture

### File Structure

```
src/sk-agents/
├── docs/demos/pdf_support/
│   ├── config.yaml                    # Demo configuration
│   └── PDF_SUPPORT.md                 # This document
└── src/sk_agents/
    └── chat_completion/custom/
        └── example_custom_chat_completion_factory.py  # Custom model factory
```

### Components

1. **Demo Configuration** (`config.yaml`)
   - Example agent setup for PDF processing
   - Task configuration for document analysis
   - Model selection and parameters

2. **Custom Chat Completion Factory** (`example_custom_chat_completion_factory.py`)
   - Extended model support for PDF tasks
   - Custom model selection logic
   - Enhanced multimodal capabilities

---

## Usage

### Starting the PDF Agent

```bash
# Set configuration
export TA_SERVICE_CONFIG=docs/demos/pdf_support/config.yaml

# Run the service
uv run python -m sk_agents.app

# Access API at
# http://localhost:8000/PDFAgent/1.0.0/docs
```

### Making Requests

#### Basic PDF Analysis

```bash
curl -X POST "http://localhost:8000/PDFAgent/1.0.0/api" \
  -H "Content-Type: application/json" \
  -d '{
    "chat_history": [
      {
        "role": "user",
        "content": "What is the main topic of this document?",
        "attachments": [
          {
            "type": "pdf",
            "url": "https://example.com/document.pdf"
          }
        ]
      }
    ]
  }'
```

#### Information Extraction

```json
{
  "chat_history": [
    {
      "role": "user",
      "content": "Extract all dates mentioned in the document",
      "attachments": [
        {
          "type": "pdf",
          "data": "base64_encoded_pdf_content"
        }
      ]
    }
  ]
}
```

---

## API Request Format

### With PDF Attachment

```json
{
  "chat_history": [
    {
      "role": "user",
      "content": "Your question about the PDF",
      "attachments": [
        {
          "type": "pdf",
          "url": "https://example.com/file.pdf"
        }
      ]
    }
  ]
}
```

### Response Format

```json
{
  "task_id": "string",
  "session_id": "string",
  "request_id": "string",
  "output": "Analysis results or extracted information",
  "source": "PDFAgent:1.0.0",
  "token_usage": {
    "total_tokens": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0
  }
}
```

---

## Examples

### Example 1: Document Summary

**Request:**
```json
{
  "chat_history": [
    {
      "role": "user",
      "content": "Summarize this research paper",
      "attachments": [
        {
          "type": "pdf",
          "url": "https://arxiv.org/pdf/2303.08774.pdf"
        }
      ]
    }
  ]
}
```

**Response:**
```json
{
  "output": "This research paper discusses... [summary content]",
  "token_usage": {...}
}
```

### Example 2: Data Extraction

**Request:**
```json
{
  "chat_history": [
    {
      "role": "user",
      "content": "Extract all company names and addresses from this invoice",
      "attachments": [
        {
          "type": "pdf",
          "data": "base64_pdf_data"
        }
      ]
    }
  ]
}
```

**Response:**
```json
{
  "output": "Company Names:\n1. Acme Corp - 123 Main St...",
  "token_usage": {...}
}
```

### Example 3: Q&A on Document

**Request:**
```json
{
  "chat_history": [
    {
      "role": "user",
      "content": "When was this contract signed and what are the key terms?",
      "attachments": [
        {
          "type": "pdf",
          "url": "https://example.com/contract.pdf"
        }
      ]
    }
  ]
}
```

---

## Custom Chat Completion Factory

### Purpose

The custom chat completion factory extends the default model selection to provide:
- Enhanced model support for PDF and multimodal tasks
- Custom model routing based on task requirements
- Optimized model selection for document processing

### Configuration

To use the custom factory, set environment variables:

```bash
export TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE=sk_agents.chat_completion.custom.example_custom_chat_completion_factory
export TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME=ExampleCustomChatCompletionFactory
```

### Supported Models

The custom factory includes support for various models optimized for:
- Text extraction
- Document understanding
- Multimodal analysis
- Question answering

---

## Best Practices

### Document Preparation

1. **File Size**: Keep PDFs under reasonable size limits (< 10MB recommended)
2. **Format**: Use text-based PDFs when possible (not scanned images)
3. **Quality**: Ensure clear, readable documents for best results
4. **Pages**: Consider splitting very long documents

### Prompting

1. **Be Specific**: Ask clear, specific questions about the document
2. **Context**: Provide context about what you're looking for
3. **Structure**: Request structured output (lists, tables) when appropriate
4. **Validation**: Ask follow-up questions to verify extracted information

### Performance

1. **Token Limits**: Monitor token usage for large documents
2. **Chunking**: Break large documents into sections if needed
3. **Caching**: Reuse document analysis across multiple questions
4. **Model Selection**: Use appropriate models for the task complexity

---

## Limitations

### Current Constraints

1. **File Size**: Large PDFs may exceed token limits
2. **Image Content**: Scanned PDFs require OCR capabilities
3. **Complex Layouts**: Tables and charts may be challenging
4. **Languages**: Performance varies by document language
5. **Security**: Sensitive documents require appropriate handling

### Known Issues

- Multi-column layouts may be parsed incorrectly
- Some special characters may not render properly
- Very large documents may need chunking
- Scanned PDFs require models with OCR support

---

## Testing

### Test Cases

#### Test 1: Simple Text Extraction
```json
{
  "chat_history": [
    {
      "role": "user",
      "content": "What is the title of this document?",
      "attachments": [{"type": "pdf", "url": "simple.pdf"}]
    }
  ]
}
```

#### Test 2: Multi-Page Analysis
```json
{
  "chat_history": [
    {
      "role": "user",
      "content": "Summarize each section of this report",
      "attachments": [{"type": "pdf", "url": "report.pdf"}]
    }
  ]
}
```

#### Test 3: Data Extraction
```json
{
  "chat_history": [
    {
      "role": "user",
      "content": "Create a table of all dates and events mentioned",
      "attachments": [{"type": "pdf", "url": "timeline.pdf"}]
    }
  ]
}
```

---

## Troubleshooting

### PDF Not Processing

**Possible causes:**
- Invalid PDF format
- File size too large
- Unsupported encoding
- Network issues (if URL-based)

**Solutions:**
- Verify PDF is valid and readable
- Check file size limits
- Try different encoding
- Ensure URL is accessible

### Incomplete Extraction

**Possible causes:**
- Token limit exceeded
- Complex document structure
- Poor document quality

**Solutions:**
- Increase max_tokens
- Simplify the request
- Pre-process the document
- Split into smaller chunks

### Incorrect Information

**Possible causes:**
- Model hallucination
- Ambiguous questions
- Poor document quality

**Solutions:**
- Ask more specific questions
- Request citations or page numbers
- Verify critical information
- Use lower temperature for factual tasks

---

## Migration Guide

### Adding PDF Support to Existing Agent

To add PDF capabilities to an existing agent:

1. **Update Model**: Choose a model with multimodal support
2. **Adjust max_tokens**: Increase for document processing
3. **Update System Prompt**: Include PDF handling instructions
4. **Test Thoroughly**: Verify PDF processing works as expected

**Example:**
```yaml
# Before
spec:
  agents:
    - name: assistant
      model: gpt-4o-mini
      max_tokens: 1000

# After
spec:
  agents:
    - name: assistant
      model: claude-3-5-sonnet-20240620  # Multimodal support
      max_tokens: 4000                    # Increased for PDFs
      system_prompt: |
        You can analyze PDF documents and answer questions about them.
```

---

## Performance Considerations

### Token Usage

- **Base document**: Varies by size and format
- **Per question**: Additional tokens for analysis
- **Optimization**: Cache document embeddings when possible

### Latency

- **Document loading**: Network latency for URLs
- **Processing time**: Increases with document size
- **Model inference**: Varies by model and complexity

### Cost

- **Input tokens**: Document size significantly impacts cost
- **Output tokens**: Answer length affects cost
- **Optimization**: Use smaller models for simple tasks

---

## Future Enhancements

Potential improvements:

1. **OCR Support**: Better handling of scanned PDFs
2. **Table Extraction**: Enhanced table parsing
3. **Image Analysis**: Process images within PDFs
4. **Multi-file**: Process multiple PDFs simultaneously
5. **Caching**: Store processed document embeddings
6. **Streaming**: Stream analysis results for large documents

---

## Technical Details

### Dependencies

- Multimodal LLM support (Claude, GPT-4o, etc.)
- PDF processing libraries (handled by model)
- Base64 encoding for inline PDFs
- URL handling for external PDFs

### Security Considerations

1. **Data Privacy**: PDFs may contain sensitive information
2. **Input Validation**: Verify PDF sources
3. **Access Control**: Restrict document access appropriately
4. **Logging**: Be cautious with document content in logs

---

## Testing Results

### Model Compatibility Testing

Testing was performed on **March 12, 2026** using an internal API gateway with various models to evaluate PDF processing capabilities.

#### Test Configuration

**Test Case**: PDF URL Processing
- **PDF Source**: https://arxiv.org/pdf/2303.08774.pdf
- **Task**: Summarize research paper content
- **Input Type**: BaseMultiModalInput with PDF URL attachment

#### Results Summary

| Model | Version | Status | Notes |
|-------|---------|--------|-------|
| Claude 3.7 Sonnet | claude-3-7-sonnet-20250219-v1 | ✅ **SUCCESS** | Successfully read and processed PDF from URL |
| GPT-4o | gpt-4o-2024-08-06 | ❌ **FAILED** | Unable to process PDF from URL |

#### Detailed Findings

**✅ Claude Models - WORKING**

Configuration:
```yaml
spec:
  agents:
    - name: pdf_analyzer
      role: PDF Document Analyzer
      model: claude-3-7-sonnet-20250219-v1
      system_prompt: |
        You are an expert document analyzer specialized in processing PDF files.
```

**Results**:
- Successfully fetched PDF from arXiv URL
- Extracted text content accurately
- Provided coherent document summaries
- Handled multimodal input correctly

---

**❌ GPT-4o Models - FAILED**

Configuration:
```yaml
spec:
  agents:
    - name: pdf_analyzer
      role: PDF Document Analyzer
      model: gpt-4o-2024-08-06
      system_prompt: |
        You are an expert document analyzer specialized in processing PDF files.
```

**Results**:
- Failed to process PDF from URL
- Endpoint returned 404 errors
- Azure OpenAI SDK incompatibility with API gateway structure

---

### Recommendations

**For PDF Processing Tasks**:
1. ✅ **Use Claude Models** (claude-3-7-sonnet-20250219-v1 or similar)
   - Proven compatibility with API gateway
   - Excellent multimodal and PDF processing capabilities
   - Reliable URL-based PDF fetching

2. ❌ **Avoid GPT Models** for PDF URLs at this time
   - Endpoint compatibility issues with current gateway configuration
   - May work with base64-encoded PDFs (not tested)

**Configuration Best Practices**:
```yaml
# RECOMMENDED: Claude for PDF processing
model: claude-3-7-sonnet-20250219-v1
input_type: BaseMultiModalInput
max_tokens: 4000
temperature: 0.3
include_thinking: true
```

**Custom Factory Setup**:
```bash
# Required environment variables
export TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE=src/sk_agents/chat_completion/custom/example_custom_chat_completion_factory.py
export TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME=ExampleCustomChatCompletionFactory
```

### Testing Checklist

When testing PDF support:
- ✅ Use Claude models for URL-based PDFs
- ✅ Set `input_type: BaseMultiModalInput` in config
- ✅ Configure custom chat completion factory
- ✅ Test with public PDFs (e.g., arXiv) before internal documents
- ✅ Verify API key has proper permissions
- ✅ Monitor token usage for large documents
- ⚠️ Consider base64 encoding for sensitive documents instead of URLs

---

## Summary

PDF support enables agents to:
- ✓ Process and analyze PDF documents
- ✓ Extract information accurately
- ✓ Answer questions about document content
- ✓ Support various PDF formats and structures

The implementation provides a flexible foundation for document processing tasks while maintaining compatibility with the existing agent framework.

**⚠️ Important**: Based on testing with internal API gateways, **Claude models are recommended** for PDF processing tasks. GPT models may have endpoint compatibility issues with URL-based PDF attachments depending on the API gateway configuration.

---

**Implementation Date**: February 2026  
**Testing Date**: March 12, 2026  
**Status**: Production Ready (Claude models)  
**Version**: 1.0.0
