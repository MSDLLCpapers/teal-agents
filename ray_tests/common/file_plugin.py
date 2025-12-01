"""
File Plugin for reading and searching local files.

This plugin provides tools for listing, reading, and searching files
in the local data directory.
"""

import os
from pathlib import Path
from typing import List

from pydantic import BaseModel
from semantic_kernel.functions.kernel_function_decorator import kernel_function

from sk_agents.ska_types import BasePlugin


class FileInfo(BaseModel):
    """Information about a file."""
    name: str
    path: str
    size: int
    extension: str


class FileListResult(BaseModel):
    """Result of listing files."""
    files: List[FileInfo]
    total_count: int


class FileContent(BaseModel):
    """Content of a file."""
    filename: str
    content: str
    size: int


class FilePlugin(BasePlugin):
    """Plugin for file operations."""

    def __init__(self, authorization: str | None = None, extra_data_collector=None):
        super().__init__(authorization, extra_data_collector)
        # Get the data directory relative to this plugin file
        self.data_dir = Path(__file__).parent / "data"

    @kernel_function(
        description="List all files in the data directory"
    )
    def list_files(self) -> FileListResult:
        """
        List all files in the data directory.

        Returns:
            FileListResult with information about all files
        """
        files = []

        if not self.data_dir.exists():
            return FileListResult(files=[], total_count=0)

        for file_path in self.data_dir.iterdir():
            if file_path.is_file():
                files.append(FileInfo(
                    name=file_path.name,
                    path=str(file_path.relative_to(self.data_dir.parent)),
                    size=file_path.stat().st_size,
                    extension=file_path.suffix
                ))

        return FileListResult(
            files=sorted(files, key=lambda x: x.name),
            total_count=len(files)
        )

    @kernel_function(
        description="Read the contents of a specific file by filename"
    )
    def read_file(self, filename: str) -> FileContent:
        """
        Read the contents of a file.

        Args:
            filename: Name of the file to read (e.g., 'sample.txt')

        Returns:
            FileContent with the file contents

        Raises:
            ValueError: If file doesn't exist or cannot be read
        """
        file_path = self.data_dir / filename

        if not file_path.exists():
            raise ValueError(f"File '{filename}' not found in data directory")

        if not file_path.is_file():
            raise ValueError(f"'{filename}' is not a file")

        try:
            content = file_path.read_text(encoding='utf-8')
            return FileContent(
                filename=filename,
                content=content,
                size=len(content)
            )
        except UnicodeDecodeError:
            raise ValueError(f"File '{filename}' is not a text file or has encoding issues")
        except Exception as e:
            raise ValueError(f"Error reading file '{filename}': {str(e)}")

    @kernel_function(
        description="Search for files by name pattern (supports wildcards like *.txt)"
    )
    def search_files(self, pattern: str) -> FileListResult:
        """
        Search for files matching a pattern.

        Args:
            pattern: Search pattern (e.g., '*.txt', 'note*', 'config.json')

        Returns:
            FileListResult with matching files
        """
        if not self.data_dir.exists():
            return FileListResult(files=[], total_count=0)

        files = []
        for file_path in self.data_dir.glob(pattern):
            if file_path.is_file():
                files.append(FileInfo(
                    name=file_path.name,
                    path=str(file_path.relative_to(self.data_dir.parent)),
                    size=file_path.stat().st_size,
                    extension=file_path.suffix
                ))

        return FileListResult(
            files=sorted(files, key=lambda x: x.name),
            total_count=len(files)
        )
