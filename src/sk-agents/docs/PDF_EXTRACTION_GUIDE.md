# PDF Text Extraction for Teal Agents - Complete Guide

**Version:** 1.0.0
**Last Updated:** March 2026

## Table of Contents

1. [Quick Start](#quick-start)
2. [Problem Statement](#problem-statement)
3. [Solution Overview](#solution-overview)
4. [Installation](#installation)
5. [API Endpoints](#api-endpoints)
6. [Usage Examples](#usage-examples)
7. [Python API Reference](#python-api-reference)
8. [Implementation Details](#implementation-details)
9. [Configuration](#configuration)
10. [Error Handling](#error-handling)
11. [Best Practices](#best-practices)
12. [Limitations](#limitations)
13. [Testing](#testing)
14. [Troubleshooting](#troubleshooting)
15. [Future Enhancements](#future-enhancements)

---

## Quick Start

Get started with PDF text extraction in 3 minutes.

### Installation

```bash
# Install the PDF processing library
pip install pypdf
```

### Start Your Agent

```bash
# Set your config
export TA_SERVICE_CONFIG=path/to/your/config.yaml

# Start the service
python -m sk_agents.app
```

### Upload a PDF

```bash
curl -X POST "http://localhost:8000/YourAgent/1.0/files/upload/pdf" \
  -F "file=@document.pdf"
```

### Upload PDF with Question

```bash
curl -X POST "http://localhost:8000/YourAgent/1.0/files/upload/pdf/formatted" \
  -F "file=@document.pdf" \
  -F "question=What is this document about?"
```

### Use with Agent API

```python
import requests

# Extract PDF text
with open("document.pdf", "rb") as f:
    response = requests.post(
        "http://localhost:8000/YourAgent/1.0/files/upload/pdf/formatted",
        files={"file": f},
        data={"question": "Summarize this document"}
    )

formatted_prompt = response.json()["formatted_prompt"]

# Send to agent
agent_response = requests.post(
    "http://localhost:8000/YourAgent/1.0/tealagents/v1alpha1",
    json={
        "user_id": "user123",
        "items": [{"content_type": "text", "content": formatted_prompt}]
    }
)

print(agent_response.json()["output"])
```

---

## Problem Statement

Semantic Kernel cannot directly handle PDF files, but users need to process PDF documents with AI agents. The solution is to extract text from PDFs before sending to the LLM.

---

## Solution Overview

This module provides PDF text extraction functionality that:

1. **Accepts PDF file uploads** via REST API endpoints
2. **Extracts text content** using the `pypdf` library
3. **Formats extracted text** for optimal LLM processing
4. **Returns structured data** including metadata and extracted content

### Key Features

✅ **File Upload Support** - Accept PDF files via multipart/form-data
✅ **Text Extraction** - Extract all text content from PDFs
✅ **Page Limiting** - Process only first N pages for large documents
✅ **Metadata Extraction** - Get PDF metadata (title, author, pages)
✅ **LLM Formatting** - Format text optimally for LLM processing
✅ **Error Handling** - Comprehensive error messages and status codes
✅ **Logging** - Detailed logging of extraction process

---

## Installation

### Using pip

```bash
pip install pypdf
```

### Using pyproject.toml

Add to your `pyproject.toml`:

```toml
[project]
dependencies = [
    "pypdf>=4.0.0",
    # ... other dependencies
]
```

### Fallback Library

If `pypdf` is not available, the system will attempt to use `PyPDF2`:

```bash
pip install PyPDF2
```

---

## API Endpoints

All endpoints are prefixed with `/{ServiceName}/{Version}/files`

### POST `/upload/pdf`

Extract text from a PDF file.

**Parameters:**
- `file` (form-data, required): PDF file to upload
- `max_pages` (form-data, optional): Maximum number of pages to extract
- `include_page_numbers` (form-data, optional): Include page numbers in output (default: true)

**Request Example:**

```bash
curl -X POST "http://localhost:8000/{ServiceName}/{Version}/files/upload/pdf" \
  -F "file=@document.pdf" \
  -F "max_pages=10" \
  -F "include_page_numbers=true"
```

**Response:** `PDFUploadResponse`

```json
{
  "filename": "document.pdf",
  "num_pages": 5,
  "extracted_text": "--- Page 1 ---\nDocument content...",
  "char_count": 15420,
  "metadata": {
    "title": "Document Title",
    "author": "Author Name"
  }
}
```

### POST `/upload/pdf/formatted`

Upload PDF and get formatted text with question for LLM processing.

**Parameters:**
- `file` (form-data, required): PDF file to upload
- `question` (form-data, required): User's question about the PDF
- `max_pages` (form-data, optional): Maximum pages to extract

**Request Example:**

```bash
curl -X POST "http://localhost:8000/{ServiceName}/{Version}/files/upload/pdf/formatted" \
  -F "file=@document.pdf" \
  -F "question=What is the main topic of this document?" \
  -F "max_pages=10"
```

**Response:**

```json
{
  "formatted_prompt": "# PDF Document Content\n**Source:** document.pdf\n\n## Document Text:\n...\n\n## User Question:\nWhat is the main topic?",
  "filename": "document.pdf",
  "num_pages": 5,
  "char_count": 15420,
  "metadata": {
    "title": "Document Title",
    "author": "Author Name"
  }
}
```

---

## Usage Examples

### 1. Simple PDF Upload

Upload a PDF and get extracted text:

```bash
curl -X POST "http://localhost:8000/PDFAgent/1.0/files/upload/pdf" \
  -F "file=@document.pdf" \
  -F "max_pages=10"
```

**Response:**
```json
{
  "filename": "document.pdf",
  "num_pages": 5,
  "extracted_text": "Page 1 content...",
  "char_count": 15420,
  "metadata": {
    "title": "Document Title"
  }
}
```

### 2. PDF with Question (Formatted for LLM)

Upload a PDF with a question and get formatted text ready for the LLM:

```bash
curl -X POST "http://localhost:8000/PDFAgent/1.0/files/upload/pdf/formatted" \
  -F "file=@document.pdf" \
  -F "question=What is the main topic?"
```

**Response:**
```json
{
  "formatted_prompt": "# PDF Document Content\n**Source:** document.pdf\n\n## Document Text:\n...\n\n## User Question:\nWhat is the main topic?",
  "num_pages": 5,
  "char_count": 15420
}
```

### 3. Full Integration with Agent

Complete workflow example:

```python
import requests

# Step 1: Upload PDF and extract text
with open("document.pdf", "rb") as f:
    upload_response = requests.post(
        "http://localhost:8000/PDFAgent/1.0/files/upload/pdf/formatted",
        files={"file": f},
        data={"question": "Summarize this document"}
    )

formatted_text = upload_response.json()["formatted_prompt"]

# Step 2: Send to agent
agent_response = requests.post(
    "http://localhost:8000/PDFAgent/1.0/tealagents/v1alpha1",
    json={
        "user_id": "user123",
        "items": [
            {
                "content_type": "text",
                "content": formatted_text
            }
        ]
    }
)

print(agent_response.json()["output"])
```

### 4. Error Handling Example

Production-ready code with error handling:

```python
import requests
from typing import Optional

def process_pdf_with_agent(
    pdf_path: str,
    question: str,
    agent_url: str,
    max_pages: Optional[int] = None
) -> str:
    """
    Process a PDF file with an agent.

    Args:
        pdf_path: Path to PDF file
        question: Question about the PDF
        agent_url: Base URL of the agent service
        max_pages: Optional limit on pages to process

    Returns:
        Agent's response text
    """
    try:
        # Step 1: Upload and extract PDF
        with open(pdf_path, "rb") as f:
            upload_data = {"question": question}
            if max_pages:
                upload_data["max_pages"] = max_pages

            upload_response = requests.post(
                f"{agent_url}/files/upload/pdf/formatted",
                files={"file": f},
                data=upload_data
            )
            upload_response.raise_for_status()

        formatted_prompt = upload_response.json()["formatted_prompt"]

        # Step 2: Send to agent
        agent_response = requests.post(
            f"{agent_url}/tealagents/v1alpha1",
            json={
                "user_id": "user123",
                "items": [
                    {
                        "content_type": "text",
                        "content": formatted_prompt
                    }
                ]
            }
        )
        agent_response.raise_for_status()

        return agent_response.json()["output"]

    except requests.exceptions.RequestException as e:
        print(f"API error: {e}")
        raise
    except KeyError as e:
        print(f"Unexpected response format: {e}")
        raise
    except Exception as e:
        print(f"Error processing PDF: {e}")
        raise

# Usage
if __name__ == "__main__":
    result = process_pdf_with_agent(
        pdf_path="document.pdf",
        question="What is the main topic?",
        agent_url="http://localhost:8000/PDFAgent/1.0",
        max_pages=10
    )
    print(result)
```

---

## Python API Reference

### PDFExtractor Class

Import the extractor:

```python
from sk_agents.utils.pdf_extractor import PDFExtractor, PDFExtractionError
```

#### Method: `extract_text_from_pdf()`

Extract text from a PDF file or bytes.

```python
text = PDFExtractor.extract_text_from_pdf(
    pdf_file,                    # File object or bytes
    max_pages=None,             # Optional: limit pages
    include_page_numbers=True   # Optional: add page markers
)
```

**Parameters:**
- `pdf_file` (BinaryIO | bytes): PDF file object or bytes
- `max_pages` (int, optional): Maximum pages to extract
- `include_page_numbers` (bool): Add page number markers (default: True)

**Returns:** `str` - Extracted text content

**Raises:** `PDFExtractionError` on failure

**Example:**

```python
with open("document.pdf", "rb") as f:
    text = PDFExtractor.extract_text_from_pdf(
        pdf_file=f,
        max_pages=10,
        include_page_numbers=True
    )
    print(text)
```

#### Method: `extract_metadata()`

Extract metadata from a PDF file.

```python
metadata = PDFExtractor.extract_metadata(pdf_file)
```

**Parameters:**
- `pdf_file` (BinaryIO | bytes): PDF file object or bytes

**Returns:** `dict` with keys:
- `num_pages` (int): Number of pages
- `title` (str | None): Document title
- `author` (str | None): Document author
- `subject` (str | None): Document subject
- `creator` (str | None): Creator application

**Example:**

```python
with open("document.pdf", "rb") as f:
    metadata = PDFExtractor.extract_metadata(f)
    print(f"Pages: {metadata['num_pages']}")
    print(f"Title: {metadata['title']}")
    print(f"Author: {metadata['author']}")
```

#### Method: `format_extracted_text_for_llm()`

Format extracted text with document structure and user question.

```python
formatted = PDFExtractor.format_extracted_text_for_llm(
    extracted_text,
    filename,
    user_question
)
```

**Parameters:**
- `extracted_text` (str): The extracted text content
- `filename` (str): Name of the PDF file
- `user_question` (str): User's question about the document

**Returns:** `str` - Formatted prompt ready for LLM

**Example:**

```python
formatted = PDFExtractor.format_extracted_text_for_llm(
    extracted_text="Document content here...",
    filename="document.pdf",
    user_question="What is the main topic?"
)
print(formatted)
```

**Output:**
```
# PDF Document Content
**Source:** document.pdf

## Document Text:
Document content here...

## User Question:
What is the main topic?
```

#### Method: `is_available()`

Check if PDF processing libraries are installed.

```python
available = PDFExtractor.is_available()
```

**Returns:** `bool` - True if pypdf or PyPDF2 is installed

**Example:**

```python
if PDFExtractor.is_available():
    print("PDF processing is available")
else:
    print("Please install: pip install pypdf")
```

---

## Implementation Details

### Files Created

#### 1. Core Extraction Module
**File:** `src/sk_agents/utils/pdf_extractor.py`

Main PDF processing class with methods:
- `extract_text_from_pdf()` - Extract text from PDF files
- `extract_metadata()` - Get PDF metadata (pages, title, author)
- `format_extracted_text_for_llm()` - Format text for LLM consumption
- `is_available()` - Check if required libraries are installed

**Features:**
- Supports file objects or bytes input
- Configurable page limits
- Optional page number inclusion
- Comprehensive error handling
- Works with both `pypdf` and `PyPDF2`

#### 2. REST API Routes
**File:** `src/sk_agents/file_upload_routes.py`

Two main endpoints:

**POST `/files/upload/pdf`**
- Upload PDF and get extracted text
- Parameters: file, max_pages, include_page_numbers
- Returns: PDFUploadResponse with text, metadata, statistics

**POST `/files/upload/pdf/formatted`**
- Upload PDF with a question
- Returns text pre-formatted for LLM with user's question included
- Ready to send directly to agent

#### 3. App Integration
**File:** `src/sk_agents/appv3.py` (modified)

Added file upload routes to AppV3:
```python
# Include file upload routes for PDF processing
app.include_router(
    FileUploadRoutes.get_file_upload_routes(),
    prefix=f"/{name}/{version}",
)
```

#### 4. Module Initialization
**File:** `src/sk_agents/utils/__init__.py`

Exports the PDF utilities:
```python
from sk_agents.utils.pdf_extractor import PDFExtractor, PDFExtractionError

__all__ = [
    "PDFExtractor",
    "PDFExtractionError",
]
```

#### 5. Test Script
**File:** `tests/test_pdf_extraction.py`

Command-line test utility:
```bash
python test_pdf_extraction.py document.pdf http://localhost:8000/PDFAgent/1.0
```

Tests both extraction endpoints and provides detailed output.

---

## Configuration

No special configuration required. The PDF processing routes are automatically included when using AppV3 (tealagents/v1alpha1).

The system will automatically detect and use:
1. `pypdf` (preferred)
2. `PyPDF2` (fallback)

---

## Error Handling

The module handles various error scenarios with appropriate HTTP status codes:

| Error Type | Status Code | Description |
|------------|-------------|-------------|
| Invalid file type | 400 Bad Request | File is not a PDF |
| Empty file | 400 Bad Request | Uploaded file is empty |
| Extraction failure | 422 Unprocessable Entity | Could not extract text from PDF |
| Missing library | 500 Internal Server Error | pypdf/PyPDF2 not installed |
| Internal errors | 500 Internal Server Error | Unexpected error during processing |

### Example Error Responses

**Invalid file type:**
```json
{
  "detail": "File must be a PDF (application/pdf)"
}
```

**Missing library:**
```json
{
  "detail": "PDF extraction requires 'pypdf' or 'PyPDF2'. Install with: pip install pypdf"
}
```

**Extraction failure:**
```json
{
  "detail": "Failed to extract text from PDF: [error details]"
}
```

---

## Best Practices

### 1. Chunk Large Documents

For PDFs with many pages, process in chunks:

```python
# Process first 10 pages
response = requests.post(
    f"{agent_url}/files/upload/pdf",
    files={"file": pdf_file},
    data={"max_pages": 10}
)
```

### 2. Set max_pages

Limit extraction to relevant pages to reduce processing time and token usage:

```bash
curl -X POST "http://localhost:8000/PDFAgent/1.0/files/upload/pdf" \
  -F "file=@document.pdf" \
  -F "max_pages=5"
```

### 3. Validate Results

Check extracted text quality before sending to LLM:

```python
response = requests.post(url, files={"file": f}, data={"question": q})
data = response.json()

# Verify extraction succeeded
if data["char_count"] == 0:
    print("Warning: No text extracted from PDF")
```

### 4. Handle Errors

Implement retry logic for network issues:

```python
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

session = requests.Session()
retry = Retry(total=3, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)

response = session.post(url, files=files, data=data)
```

### 5. Cache Extractions

Store extracted text to avoid re-processing:

```python
import hashlib
import json

def get_pdf_cache_key(pdf_path: str) -> str:
    """Generate cache key from PDF file hash."""
    with open(pdf_path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def extract_with_cache(pdf_path: str, cache_dir: str):
    """Extract PDF with caching."""
    cache_key = get_pdf_cache_key(pdf_path)
    cache_file = f"{cache_dir}/{cache_key}.json"

    # Check cache
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)

    # Extract and cache
    with open(pdf_path, "rb") as f:
        response = requests.post(url, files={"file": f})
        data = response.json()

    with open(cache_file, "w") as f:
        json.dump(data, f)

    return data
```

---

## Limitations

### 1. Text-based PDFs Only

The extractor works with text-based PDFs. Scanned PDFs (images) require OCR processing.

**Workaround:** Use OCR preprocessing tools like Tesseract before extraction.

### 2. Token Limits

Very large documents may exceed LLM token limits.

**Workaround:**
- Use `max_pages` parameter to limit extraction
- Split document into chunks
- Summarize progressively

### 3. Complex Layouts

Tables and multi-column layouts may not extract perfectly.

**Impact:** Text order may not match visual layout.

### 4. File Size

Recommended to keep PDFs under 10MB for optimal performance.

**Recommendation:** For larger files, extract specific pages or sections.

---

## Testing

### Quick Test

Test the PDF extraction with a sample PDF:

```bash
# Download a test PDF
curl -o test.pdf https://arxiv.org/pdf/2303.08774.pdf

# Extract text
curl -X POST "http://localhost:8000/PDFAgent/1.0/files/upload/pdf" \
  -F "file=@test.pdf" \
  -F "max_pages=5"

# Extract with question
curl -X POST "http://localhost:8000/PDFAgent/1.0/files/upload/pdf/formatted" \
  -F "file=@test.pdf" \
  -F "question=What is this paper about?" \
  -F "max_pages=5"
```

### Using Test Script

Run the included test script:

```bash
python tests/test_pdf_extraction.py document.pdf http://localhost:8000/PDFAgent/1.0
```

**Features:**
- Tests both extraction endpoints
- Displays detailed output
- Shows metadata and statistics
- Verifies API responses

---

## Troubleshooting

### Library Not Found

**Error:**
```
ImportError: PDF extraction requires 'pypdf' or 'PyPDF2'
```

**Solution:**
```bash
pip install pypdf
```

### Empty Extraction

If no text is extracted:

1. **Check if PDF is text-based** (not scanned image)
   ```bash
   # Open PDF in a reader to verify it has selectable text
   ```

2. **Verify file size and corruption**
   ```bash
   # Check file size
   ls -lh document.pdf

   # Try opening in PDF reader
   ```

3. **Test with a known-good PDF**
   ```bash
   curl -o test.pdf https://arxiv.org/pdf/2303.08774.pdf
   # Test extraction with this file
   ```

### Encoding Issues

If text has garbled characters:

1. **PDF may use non-standard encoding**
   - Try different PDF viewer to verify original content
   - Check PDF properties for encoding information

2. **May require preprocessing**
   - Use PDF repair tools
   - Re-save PDF with standard encoding

### API Errors

**Connection refused:**
```
requests.exceptions.ConnectionError: Connection refused
```

**Solution:** Verify agent service is running:
```bash
# Check if service is running
curl http://localhost:8000/health

# Start service if needed
python -m sk_agents.app
```

**422 Unprocessable Entity:**
```json
{"detail": "Failed to extract text from PDF"}
```

**Solution:**
- Verify PDF is not corrupted
- Check PDF is text-based (not scanned)
- Try with `max_pages` parameter to limit extraction

---

## Future Enhancements

Planned improvements for future versions:

- **OCR Support** - Process scanned PDFs with Tesseract or similar
- **Table Extraction** - Preserve table structure in extracted text
- **Image Extraction** - Extract and process images from PDFs
- **Streaming Extraction** - Process large files without loading entirely into memory
- **Batch Processing** - Upload and process multiple PDFs simultaneously
- **PDF Preprocessing** - Automatic cleanup and optimization
- **Advanced Formatting** - Better handling of complex layouts
- **Metadata Enhancement** - Extract additional document metadata
- **Caching Layer** - Built-in caching to avoid re-processing
- **Progress Tracking** - Real-time progress for large extractions

---

## Summary

This PDF text extraction module enables Teal Agents to process PDF documents by:

1. ✅ Accepting PDF uploads via REST API
2. ✅ Extracting text content with `pypdf`
3. ✅ Formatting text for optimal LLM processing
4. ✅ Providing comprehensive error handling
5. ✅ Supporting metadata extraction
6. ✅ Offering flexible page limiting

**Get Started:**
```bash
pip install pypdf
python -m sk_agents.app
```

**Quick Test:**
```bash
curl -X POST "http://localhost:8000/YourAgent/1.0/files/upload/pdf" \
  -F "file=@document.pdf"
```

For questions or issues, refer to the [Troubleshooting](#troubleshooting) section.

---

**Documentation Version:** 1.0.0
**Last Updated:** March 16, 2026
