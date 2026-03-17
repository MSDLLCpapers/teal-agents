"""
File Processing Utilities for Agent Input

Provides utility functions for processing file uploads (particularly PDFs)
and integrating them with agent prompts.
"""

import logging

from fastapi import HTTPException, UploadFile, status

from sk_agents.utils.pdf_extractor import PDFExtractionError, PDFExtractor

logger = logging.getLogger(__name__)


class FileProcessor:
    """Utility class for processing file uploads and integrating with agent input"""

    @staticmethod
    async def process_pdf_upload(
        file: UploadFile,
        max_pages: int | None = None,
    ) -> str:
        """
        Process an uploaded PDF file and extract its text content.

        Args:
            file: Uploaded PDF file
            max_pages: Maximum number of pages to extract (None = all pages)

        Returns:
            Extracted text content formatted for LLM processing

        Raises:
            HTTPException: If PDF processing fails
        """
        # Validate file type
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be a PDF (.pdf extension required)",
            )

        # Check if PDF extraction is available
        if not PDFExtractor.is_available():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "PDF extraction not available. "
                    "Please install required package: pip install pypdf"
                ),
            )

        try:
            # Read file content
            file_content = await file.read()

            if len(file_content) == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty"
                )

            # Extract metadata
            metadata = PDFExtractor.extract_metadata(file_content)

            # Extract text
            extracted_text = PDFExtractor.extract_text_from_pdf(
                pdf_file=file_content,
                max_pages=max_pages,
                include_page_numbers=True,
            )

            logger.info(
                f"Successfully processed PDF: {file.filename}, "
                f"{metadata['num_pages']} pages, "
                f"{len(extracted_text)} characters"
            )

            # Format for LLM - just prepend document context
            formatted_text = (
                f"# PDF Document Content\n**Source:** {file.filename}\n\n{extracted_text}"
            )

            return formatted_text

        except PDFExtractionError as e:
            logger.error(f"PDF extraction failed for {file.filename}: {e}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Failed to extract text from PDF: {str(e)}",
            ) from e
        except Exception as e:
            logger.exception(f"Unexpected error processing PDF {file.filename}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Internal server error: {str(e)}",
            ) from e
        finally:
            await file.close()

    @staticmethod
    def combine_pdf_and_prompt(pdf_text: str, user_prompt: str) -> str:
        """
        Combine extracted PDF text with user's prompt.

        Args:
            pdf_text: Extracted PDF content
            user_prompt: User's question/prompt

        Returns:
            Combined text ready for agent processing
        """
        return f"{pdf_text}\n\n## User Question:\n{user_prompt}"
