"""
File Upload Routes for PDF Processing

Provides endpoints for uploading PDF files and extracting text
for processing with LLMs via Semantic Kernel.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from sk_agents.utils.pdf_extractor import PDFExtractionError, PDFExtractor

logger = logging.getLogger(__name__)


class PDFUploadResponse(BaseModel):
    """Response model for PDF upload"""

    filename: str
    num_pages: int
    extracted_text: str
    char_count: int
    metadata: dict


class FileUploadRoutes:
    """Routes for handling file uploads, particularly PDFs"""

    @staticmethod
    def get_file_upload_routes() -> APIRouter:
        """
        Create routes for file upload endpoints.

        Returns:
            APIRouter with file upload endpoints
        """
        router = APIRouter(prefix="/files", tags=["File Upload"])

        @router.post("/upload/pdf", response_model=PDFUploadResponse)
        async def upload_pdf(
            file: Annotated[UploadFile, File(description="PDF file to process")],
            max_pages: Annotated[
                int | None, Form(description="Maximum number of pages to extract (optional)")
            ] = None,
            include_page_numbers: Annotated[
                bool, Form(description="Include page numbers in extracted text")
            ] = True,
        ):
            """
            Upload and extract text from a PDF file.

            This endpoint accepts a PDF file upload, extracts the text content,
            and returns it formatted for LLM processing. Use this when you want
            to process PDF files with agents that don't natively support PDF format.

            **Usage:**
            ```bash
            curl -X POST "http://localhost:8000/files/upload/pdf" \\
                -F "file=@document.pdf" \\
                -F "max_pages=10" \\
                -F "include_page_numbers=true"
            ```

            **Returns:**
            - filename: Original filename
            - num_pages: Total number of pages in PDF
            - extracted_text: Full extracted text content
            - char_count: Number of characters extracted
            - metadata: PDF metadata (title, author, etc.)
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
                    include_page_numbers=include_page_numbers,
                )

                logger.info(
                    f"Successfully processed PDF: {file.filename}, "
                    f"{metadata['num_pages']} pages, "
                    f"{len(extracted_text)} characters"
                )

                return PDFUploadResponse(
                    filename=file.filename,
                    num_pages=metadata["num_pages"],
                    extracted_text=extracted_text,
                    char_count=len(extracted_text),
                    metadata=metadata["metadata"],
                )

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

        @router.post("/upload/pdf/formatted", response_model=dict)
        async def upload_pdf_formatted(
            file: Annotated[UploadFile, File(description="PDF file to process")],
            question: Annotated[str, Form(description="Question about the PDF")],
            max_pages: Annotated[int | None, Form(description="Maximum pages to extract")] = None,
        ):
            """
            Upload PDF and get text formatted for LLM processing with a question.

            This endpoint extracts PDF text and formats it specifically for
            LLM consumption, including the user's question in the prompt.

            **Usage:**
            ```bash
            curl -X POST "http://localhost:8000/files/upload/pdf/formatted" \\
                -F "file=@document.pdf" \\
                -F "question=What is the main topic of this document?" \\
                -F "max_pages=10"
            ```

            **Returns:**
            - formatted_prompt: Text ready to send to LLM
            - metadata: PDF information
            """
            # Validate file type
            if not file.filename or not file.filename.lower().endswith(".pdf"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a PDF"
                )

            if not PDFExtractor.is_available():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="PDF extraction not available. Install pypdf: pip install pypdf",
                )

            try:
                file_content = await file.read()

                # Extract text
                extracted_text = PDFExtractor.extract_text_from_pdf(
                    pdf_file=file_content, max_pages=max_pages, include_page_numbers=True
                )

                # Format for LLM
                formatted_text = PDFExtractor.format_extracted_text_for_llm(
                    extracted_text=extracted_text, filename=file.filename, user_question=question
                )

                # Get metadata
                metadata = PDFExtractor.extract_metadata(file_content)

                return {
                    "formatted_prompt": formatted_text,
                    "filename": file.filename,
                    "num_pages": metadata["num_pages"],
                    "char_count": len(extracted_text),
                    "metadata": metadata["metadata"],
                }

            except PDFExtractionError as e:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Failed to extract text: {str(e)}",
                ) from e
            except Exception as e:
                logger.exception(f"Error processing PDF: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Internal error: {str(e)}",
                ) from e
            finally:
                await file.close()

        return router
