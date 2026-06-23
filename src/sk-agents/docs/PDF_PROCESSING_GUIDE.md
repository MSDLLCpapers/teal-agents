# PDF Processing for Teal Agents

**Version:** 2.0.0
**Last Updated:** March 2026

## Table of Contents

1. [Quick Start](#quick-start)
2. [Overview](#overview)
3. [Installation](#installation)
4. [Usage Examples](#usage-examples)
5. [Python API Reference](#python-api-reference)
6. [Error Handling](#error-handling)
7. [Best Practices](#best-practices)
8. [Limitations](#limitations)
9. [Troubleshooting](#troubleshooting)

---

## Quick Start

Send a PDF to your agent in a single request:

```bash
curl -X POST "http://localhost:8000/YourAgent/1.0/tealagents/v1alpha1/with-file" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F 'message_json={"items":[{"content_type":"text","content":"What is this document about?"}]}' \
  -F "file=@document.pdf" \
  -F "max_pages=10"
```

The PDF content is automatically extracted and combined with your question, then sent to the agent for processing.

---

## Overview

### Problem Statement

Many LLMs don't natively support PDF file uploads. Previously, users had to:
1. Upload PDFs to a separate endpoint
2. Copy the extracted text from the response
3. Paste it into a new request with their question
4. Send to the agent

This was cumbersome and error-prone.

### Solution

Teal Agents now provides **integrated PDF processing**:
- ✅ Upload PDF and prompt in a single request
- ✅ Automatic text extraction using `pypdf`
- ✅ Seamless combination of PDF content + user question
- ✅ Direct agent processing - no manual steps required

### Key Features

- **Single-Step Processing**: Upload file and ask question in one request
- **Automatic Text Extraction**: Uses `pypdf` library for reliable extraction
- **Page Limiting**: Process only the first N pages for large documents
- **Secure File Handling**: Files are processed in memory, not stored
- **Error Handling**: Comprehensive error messages and validation

---

## Installation

### Prerequisites

```bash
pip install pypdf
```

### Verify Installation

```python
from sk_agents.utils.pdf_extractor import PDFExtractor

if PDFExtractor.is_available():
    print("PDF processing is available")
```

---

## Usage Examples

### 1. Basic PDF Question

Ask a question about a PDF document:

```bash
curl -X POST "http://localhost:8000/YourAgent/1.0/tealagents/v1alpha1/with-file" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F 'message_json={"items":[{"content_type":"text","content":"Summarize this document"}]}' \
  -F "file=@report.pdf"
```

**Response:**
```json
{
  "session_id": "abc123",
  "task_id": "task456",
  "request_id": "req789",
  "status": "completed",
  "content": {
    "output": "This document discusses...",
    "token_usage": {...}
  }
}
```

### 2. Limit Pages Processed

Process only the first 5 pages of a large PDF:

```bash
curl -X POST "http://localhost:8000/YourAgent/1.0/tealagents/v1alpha1/with-file" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F 'message_json={"items":[{"content_type":"text","content":"What are the key findings?"}]}' \
  -F "file=@research_paper.pdf" \
  -F "max_pages=5"
```

### 3. Python Example

```python
import requests
import json

# Prepare the request
url = "http://localhost:8000/YourAgent/1.0/tealagents/v1alpha1/with-file"
headers = {"Authorization": "Bearer YOUR_TOKEN"}

# Message with your question
message_json = {
    "items": [{
        "content_type": "text",
        "content": "What is the main conclusion of this paper?"
    }]
}

# Open PDF and send request
with open("document.pdf", "rb") as pdf_file:
    response = requests.post(
        url,
        headers=headers,
        data={"message_json": json.dumps(message_json), "max_pages": 10},
        files={"file": pdf_file}
    )

# Get agent's response
result = response.json()
print(result["content"]["output"])
```

### 4. With Session Context

Continue a conversation with PDF context:

```python
import json
import requests

url = "http://localhost:8000/YourAgent/1.0/tealagents/v1alpha1/with-file"
headers = {"Authorization": "Bearer YOUR_TOKEN"}

# Include session_id to maintain context
message_json = {
    "session_id": "existing_session_123",
    "items": [{
        "content_type": "text",
        "content": "Based on this new document, how does it compare to our previous discussion?"
    }]
}

with open("new_report.pdf", "rb") as pdf_file:
    response = requests.post(
        url,
        headers=headers,
        data={"message_json": json.dumps(message_json)},
        files={"file": pdf_file}
    )

print(response.json()["content"]["output"])
```

### 5. Error Handling Example

```python
import json
import requests

def process_pdf_with_agent(pdf_path, question, agent_url, auth_token, max_pages=None):
    """
    Process a PDF file with an agent.

    Args:
        pdf_path: Path to PDF file
        question: Question about the PDF
        agent_url: Base URL of the agent service
        auth_token: Authorization token
        max_pages: Optional limit on pages to process

    Returns:
        Agent's response text
    """
    try:
        message_json = {
            "items": [{
                "content_type": "text",
                "content": question
            }]
        }

        with open(pdf_path, "rb") as f:
            data = {"message_json": json.dumps(message_json)}
            if max_pages:
                data["max_pages"] = max_pages

            response = requests.post(
                f"{agent_url}/tealagents/v1alpha1/with-file",
                headers={"Authorization": f"Bearer {auth_token}"},
                data=data,
                files={"file": f}
            )

            response.raise_for_status()
            result = response.json()
            return result["content"]["output"]

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400:
            print(f"Bad request: {e.response.json()['detail']}")
        elif e.response.status_code == 422:
            print(f"PDF processing failed: {e.response.json()['detail']}")
        elif e.response.status_code == 500:
            print(f"Server error: {e.response.json()['detail']}")
        raise
    except FileNotFoundError:
        print(f"PDF file not found: {pdf_path}")
        raise
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise

# Usage
answer = process_pdf_with_agent(
    pdf_path="document.pdf",
    question="What is the main topic?",
    agent_url="http://localhost:8000/YourAgent/1.0",
    auth_token="your_token_here",
    max_pages=10
)
print(answer)
```

---

## Python API Reference

### FileProcessor.process_pdf_upload()

Process an uploaded PDF file and extract text content.

```python
from sk_agents.file_upload_routes import FileProcessor

async def process_pdf(file: UploadFile, max_pages: int | None = None) -> str:
    pdf_text = await FileProcessor.process_pdf_upload(file, max_pages)
    return pdf_text
```

**Parameters:**
- `file` (UploadFile): The uploaded PDF file object
- `max_pages` (int, optional): Maximum number of pages to extract

**Returns:**
- `str`: Extracted text formatted for LLM processing

**Raises:**
- `HTTPException(400)`: Invalid file type or empty file
- `HTTPException(422)`: PDF extraction failed
- `HTTPException(500)`: pypdf library not installed

### FileProcessor.combine_pdf_and_prompt()

Combine extracted PDF text with user's prompt.

```python
from sk_agents.file_upload_routes import FileProcessor

combined = FileProcessor.combine_pdf_and_prompt(
    pdf_text="PDF content here...",
    user_prompt="What is this about?"
)
```

**Parameters:**
- `pdf_text` (str): Extracted PDF content
- `user_prompt` (str): User's question

**Returns:**
- `str`: Combined text ready for agent processing

### PDFExtractor.is_available()

Check if PDF extraction libraries are available.

```python
from sk_agents.utils.pdf_extractor import PDFExtractor

if PDFExtractor.is_available():
    print("PDF processing ready")
```

---

## Error Handling

### Common Errors

#### 1. Invalid File Type

**Error:**
```json
{
  "detail": "File must be a PDF (.pdf extension required)"
}
```

**Solution:** Ensure you're uploading a file with `.pdf` extension.

#### 2. PDF Library Not Installed

**Error:**
```json
{
  "detail": "PDF extraction not available. Please install required package: pip install pypdf"
}
```

**Solution:**
```bash
pip install pypdf
```

#### 3. Invalid JSON in message_json

**Error:**
```json
{
  "detail": "Invalid JSON in message_json: Expecting value: line 1 column 1 (char 0)"
}
```

**Solution:** Ensure `message_json` is a valid JSON string:
```bash
-F 'message_json={"items":[{"content_type":"text","content":"Your question"}]}'
```

#### 4. Missing Text Item

**Error:**
```json
{
  "detail": "Message must contain at least one text item with your question"
}
```

**Solution:** Include at least one text item in your message:
```json
{
  "items": [
    {"content_type": "text", "content": "Your question here"}
  ]
}
```

#### 5. Corrupted PDF

**Error:**
```json
{
  "detail": "Failed to extract text from PDF: PDF file is corrupted or encrypted"
}
```

**Solution:** Verify the PDF is not corrupted or password-protected. Try opening it in a PDF reader.

---

## Best Practices

### 1. Limit Pages for Large Documents

Process only relevant pages to reduce token usage:

```bash
curl -X POST "$AGENT_URL/tealagents/v1alpha1/with-file" \
  -H "Authorization: Bearer $TOKEN" \
  -F 'message_json={...}' \
  -F "file=@large_document.pdf" \
  -F "max_pages=10"
```

### 2. Be Specific in Your Questions

Instead of:
```
"Tell me about this document"
```

Use:
```
"What are the three main conclusions in the executive summary?"
```

### 3. Handle Errors Gracefully

```python
try:
    response = requests.post(url, ...)
    response.raise_for_status()
except requests.exceptions.HTTPError as e:
    # Handle specific error codes
    if e.response.status_code == 422:
        print("PDF could not be processed")
    # ... handle other errors
```

### 4. Validate PDF Before Uploading

```python
import os

def validate_pdf(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF not found: {file_path}")

    if not file_path.lower().endswith('.pdf'):
        raise ValueError("File must have .pdf extension")

    if os.path.getsize(file_path) == 0:
        raise ValueError("PDF file is empty")

    return True
```

### 5. Use Session IDs for Context

Maintain conversation context across requests:

```python
# First request
response1 = send_with_pdf(pdf1, "Summarize this", session_id=None)
session_id = response1["session_id"]

# Follow-up request
response2 = send_with_pdf(pdf2, "How does this compare?", session_id=session_id)
```

---

## Limitations

### Current Limitations

1. **Text-Only Extraction**: Only text is extracted. Images, charts, and tables are not processed.

2. **PDF Format Support**: Requires standard PDF format. May not work with:
   - Scanned documents (image-based PDFs without OCR)
   - Password-protected PDFs
   - Heavily formatted or complex layouts

3. **No URL Support**: PDFs must be uploaded as files. URL-based PDF fetching is not supported for security reasons.

4. **File Size**: Very large PDFs may timeout or exceed token limits. Use `max_pages` parameter to limit extraction.

5. **Single File**: Only one PDF can be processed per request.

### Workarounds

**For scanned PDFs:**
Use OCR tools (like Tesseract) before uploading:
```bash
ocr-tool input.pdf output.pdf
```

**For large files:**
Split into smaller PDFs or use `max_pages`:
```bash
pdftk input.pdf cat 1-10 output part1.pdf
```

**For multiple PDFs:**
Send separate requests and reference previous session:
```python
for pdf in pdf_files:
    response = send_with_pdf(pdf, question, session_id=session_id)
    session_id = response["session_id"]
```

---

## Troubleshooting

### Issue: "PDF extraction not available"

**Cause:** `pypdf` library not installed

**Solution:**
```bash
pip install pypdf
```

Verify:
```python
from sk_agents.utils.pdf_extractor import PDFExtractor
print(PDFExtractor.is_available())  # Should print True
```

---

### Issue: No text extracted (char_count = 0)

**Possible causes:**
1. PDF is image-based (scanned document)
2. PDF uses non-standard encoding
3. PDF is empty or corrupted

**Solutions:**
- Use OCR if it's a scanned document
- Try a different PDF viewer to verify content
- Check if PDF opens correctly in standard readers

---

### Issue: Agent response is truncated

**Cause:** PDF content + question exceeds token limit

**Solution:**
- Reduce `max_pages` parameter
- Ask more specific questions
- Process PDF in chunks

---

### Issue: "message_json must contain at least one text item"

**Cause:** Message format is incorrect

**Solution:**
Ensure proper JSON structure:
```json
{
  "items": [
    {"content_type": "text", "content": "Your question"}
  ]
}
```

---

## Summary

The integrated PDF processing feature enables seamless document analysis with Teal Agents:

✅ **Single-step process**: Upload file + ask question in one request
✅ **Automatic extraction**: No manual copy-paste required
✅ **Secure**: Files processed in memory, not stored
✅ **Flexible**: Control page limits and maintain session context

**Get Started:**
```bash
curl -X POST "$AGENT_URL/tealagents/v1alpha1/with-file" \
  -H "Authorization: Bearer $TOKEN" \
  -F 'message_json={"items":[{"content_type":"text","content":"Your question"}]}' \
  -F "file=@document.pdf"
```

---

**Documentation Version:** 2.0.0
**Last Updated:** March 18, 2026
**Note:** URL-based PDF fetching has been removed for security reasons. Only file uploads are supported.
