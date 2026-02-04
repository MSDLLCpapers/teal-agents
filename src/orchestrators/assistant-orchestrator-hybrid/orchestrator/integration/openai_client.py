"""
Azure OpenAI client wrapper.

This module provides a wrapper around Azure OpenAI client initialization
and common operations for chat completions.
"""

import json
import logging
from typing import Optional, Any

from openai import AzureOpenAI
from ska_utils import AppConfig
from configs import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_CHAT_MODEL,
)

logger = logging.getLogger(__name__)


class AzureOpenAIClient:
    """
    Wrapper for Azure OpenAI client.
    
    Provides centralized Azure OpenAI client management with support for:
    - Chat completions
    - JSON response parsing
    - Model configuration via configs
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_version: Optional[str] = None,
        default_model: Optional[str] = None
    ):
        """
        Initialize Azure OpenAI client.
        
        Args:
            api_key: Azure OpenAI API key (defaults to config)
            endpoint: Azure OpenAI endpoint (defaults to config)
            api_version: API version (defaults to config)
            default_model: Default model/deployment name (defaults to config)
        """
        app_config = AppConfig()
        self.api_key = api_key or app_config.get(AZURE_OPENAI_API_KEY.env_name)
        self.endpoint = endpoint or app_config.get(AZURE_OPENAI_ENDPOINT.env_name)
        self.api_version = api_version or app_config.get(AZURE_OPENAI_API_VERSION.env_name)
        self.default_model = default_model or app_config.get(AZURE_OPENAI_CHAT_MODEL.env_name)
        
        if not self.api_key or not self.endpoint:
            raise ValueError("Azure OpenAI API key and endpoint are required")
        
        self._client: Optional[AzureOpenAI] = None
    
    def _ensure_initialized(self) -> None:
        """Ensure client is initialized."""
        if self._client is None:
            self._initialize()
    
    def _initialize(self) -> None:
        """Initialize Azure OpenAI client."""
        self._client = AzureOpenAI(
            api_key=self.api_key,
            api_version=self.api_version,
            azure_endpoint=self.endpoint
        )
        logger.info(f"Azure OpenAI client initialized")
        logger.info(f"Endpoint: {self.endpoint}")
        logger.info(f"Default model: {self.default_model}")
    
    @property
    def client(self) -> AzureOpenAI:
        """Get the Azure OpenAI client instance."""
        self._ensure_initialized()
        return self._client
    
    def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 200
    ) -> str:
        """
        Make a chat completion request.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model/deployment name (defaults to configured default)
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            
        Returns:
            Response content string
        """
        self._ensure_initialized()
        
        response = self._client.chat.completions.create(
            model=model or self.default_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        return response.choices[0].message.content.strip()
    
    def chat_completion_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 400
    ) -> dict[str, Any]:
        """
        Make a chat completion request expecting JSON response.
        
        Args:
            system_prompt: System message
            user_prompt: User message
            model: Model/deployment name
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            
        Returns:
            Parsed JSON response as dictionary
        """
        result_text = self.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        # Extract JSON from response (handle potential markdown wrapping)
        result_text = self._extract_json(result_text)
        
        return json.loads(result_text)
    
    @staticmethod
    def _extract_json(text: str) -> str:
        """
        Extract JSON from text that may be wrapped in markdown code blocks.
        
        Args:
            text: Raw response text
            
        Returns:
            Clean JSON string
        """
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return text


def create_azure_openai_client() -> AzureOpenAIClient:
    """
    Factory function to create Azure OpenAI client with default configuration.
    
    Returns:
        Configured AzureOpenAIClient instance
    """
    return AzureOpenAIClient()
