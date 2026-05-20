"""
PDF Text Extraction Utility

This module provides functionality to extract text from PDF files
since Semantic Kernel cannot handle PDF files directly.
"""

import io
import logging
from typing import BinaryIO

try:
    from pypdf import PdfReader

    PYPDF_AVAILABLE = True
except ImportError:
    try:
        from PyPDF2 import PdfReader

        PYPDF_AVAILABLE = True
    except ImportError:
        PYPDF_AVAILABLE = False

logger = logging.getLogger(__name__)


class PDFExtractionError(Exception):
    """Raised when PDF extraction fails."""

    pass


class PDFExtractor:
    """
    Extracts text content from PDF files.

    This class handles PDF text extraction to enable processing
    of PDF documents with LLMs that don't natively support PDF format.
    """

    @staticmethod
    def is_available() -> bool:
        """Check if PDF extraction libraries are available."""
        return PYPDF_AVAILABLE

    @staticmethod
    def extract_text_from_pdf(
        pdf_file: BinaryIO | bytes, max_pages: int | None = None, include_page_numbers: bool = True
    ) -> str:
        """
        Extract text from a PDF file.

        Args:
            pdf_file: PDF file as file object or bytes
            max_pages: Maximum number of pages to extract (None for all)
            include_page_numbers: Include page numbers in extracted text

        Returns:
            Extracted text content

        Raises:
            PDFExtractionError: If extraction fails
            ImportError: If required PDF libraries are not installed
        """
        if not PYPDF_AVAILABLE:
            raise ImportError(
                "PDF extraction requires 'pypdf' or 'PyPDF2'. Install with: pip install pypdf"
            )

        try:
            # Handle bytes input
            if isinstance(pdf_file, bytes):
                pdf_file = io.BytesIO(pdf_file)

            # Create PDF reader
            reader = PdfReader(pdf_file)
            total_pages = len(reader.pages)

            if total_pages == 0:
                raise PDFExtractionError("PDF file contains no pages")

            # Determine pages to process
            pages_to_process = min(max_pages, total_pages) if max_pages else total_pages

            logger.info(f"Extracting text from {pages_to_process} pages (of {total_pages} total)")

            # Extract text from each page
            extracted_text_parts = []

            for page_num in range(pages_to_process):
                try:
                    page = reader.pages[page_num]
                    text = page.extract_text()

                    if text.strip():  # Only include pages with actual text
                        if include_page_numbers:
                            extracted_text_parts.append(f"\n--- Page {page_num + 1} ---\n{text}")
                        else:
                            extracted_text_parts.append(text)
                except Exception as e:
                    logger.warning(f"Failed to extract text from page {page_num + 1}: {e}")
                    continue

            if not extracted_text_parts:
                raise PDFExtractionError("No text could be extracted from PDF")

            extracted_text = "\n\n".join(extracted_text_parts)

            logger.info(f"Successfully extracted {len(extracted_text)} characters from PDF")

            return extracted_text

        except PDFExtractionError:
            raise
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            raise PDFExtractionError(f"Failed to extract text from PDF: {str(e)}") from e

    @staticmethod
    def extract_metadata(pdf_file: BinaryIO | bytes) -> dict:
        """
        Extract metadata from a PDF file.

        Args:
            pdf_file: PDF file as file object or bytes

        Returns:
            Dictionary containing PDF metadata
        """
        if not PYPDF_AVAILABLE:
            raise ImportError(
                "PDF extraction requires 'pypdf' or 'PyPDF2'. Install with: pip install pypdf"
            )

        try:
            if isinstance(pdf_file, bytes):
                pdf_file = io.BytesIO(pdf_file)

            reader = PdfReader(pdf_file)

            metadata = {"num_pages": len(reader.pages), "metadata": {}}

            if reader.metadata:
                # Convert metadata to dict
                for key, value in reader.metadata.items():
                    clean_key = key.replace("/", "").lower()
                    metadata["metadata"][clean_key] = str(value)

            return metadata

        except Exception as e:
            logger.warning(f"Failed to extract PDF metadata: {e}")
            return {"num_pages": 0, "metadata": {}}

    @staticmethod
    def format_extracted_text_for_llm(
        extracted_text: str, filename: str | None = None, user_question: str | None = None
    ) -> str:
        """
        Format extracted PDF text for optimal LLM processing.

        Args:
            extracted_text: Raw extracted text
            filename: Original PDF filename
            user_question: User's question about the PDF

        Returns:
            Formatted text prompt
        """
        parts = []

        parts.append("# PDF Document Content")

        if filename:
            parts.append(f"**Source:** {filename}")

        parts.append("\n## Document Text:\n")
        parts.append(extracted_text)

        if user_question:
            parts.append(f"\n## User Question:\n{user_question}")

        return "\n".join(parts)
