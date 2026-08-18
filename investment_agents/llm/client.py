"""
LiteLLM client wrapper.
- Unified API for Ollama (local) and cloud providers
- Budget-aware: passes metadata for callback tracking
- Retry logic with tenacity
- Structured JSON output parsing
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, AsyncIterator, Dict, Optional, Type

import litellm
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from investment_agents.config.settings import get_settings

logger = structlog.get_logger(__name__)

# Silence LiteLLM's verbose logging unless we're in DEBUG
litellm.suppress_debug_info = True


class LLMCallError(Exception):
    """Raised when an LLM call fails after all retries."""


class LLMClient:
    """
    Production LiteLLM wrapper with:
    - Automatic retry (exponential backoff)
    - Metadata tagging (debate_id, agent_id, round) for budget tracking
    - Structured JSON extraction from responses
    - Streaming token support
    """

    def __init__(self, model: Optional[str] = None):
        self._settings = get_settings()
        self.model = model or self._settings.default_model
        self._configure_litellm()

    def _configure_litellm(self) -> None:
        """Set LiteLLM global config (Ollama base URL, keys)."""
        if self.model.startswith("ollama/"):
            litellm.api_base = self._settings.ollama_base_url

        openai_key = self._settings.get_openai_api_key()
        anthropic_key = self._settings.get_anthropic_api_key()
        if openai_key:
            litellm.openai_key = openai_key
        if anthropic_key:
            litellm.anthropic_key = anthropic_key

    async def complete(
        self,
        messages: list[Dict[str, str]],
        *,
        agent_id: str,
        debate_id: str,
        round_number: int,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        response_format: Optional[str] = None,  # "json" to request JSON mode
    ) -> tuple[str, int]:
        """
        Make an async LLM completion call.

        Returns:
            (response_text, total_tokens_used)
        """
        metadata = {
            "agent_id": agent_id,
            "debate_id": debate_id,
            "round_number": round_number,
        }

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "metadata": metadata,
            "timeout": self._settings.agent_request_timeout,
        }

        # Request JSON output if supported and requested
        if response_format == "json":
            if not self.model.startswith("ollama/"):
                kwargs["response_format"] = {"type": "json_object"}

        last_error: Optional[Exception] = None

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._settings.agent_max_retries),
            wait=wait_exponential(
                multiplier=1, min=self._settings.agent_retry_delay, max=10
            ),
            retry=retry_if_exception_type((Exception,)),
            reraise=False,
        ):
            with attempt:
                try:
                    response = await litellm.acompletion(**kwargs)
                    text = response.choices[0].message.content or ""
                    tokens = response.usage.total_tokens if response.usage else 0
                    logger.debug(
                        "llm_call_success",
                        agent_id=agent_id,
                        debate_id=debate_id,
                        round_number=round_number,
                        tokens=tokens,
                        model=self.model,
                    )
                    return text, tokens
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "llm_call_failed",
                        agent_id=agent_id,
                        error=str(e),
                        attempt=attempt.retry_state.attempt_number,
                    )
                    raise

        raise LLMCallError(
            f"LLM call failed for agent {agent_id} after all retries: {last_error}"
        )

    async def stream_complete(
        self,
        messages: list[Dict[str, str]],
        *,
        agent_id: str,
        debate_id: str,
        round_number: int,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """
        Stream tokens from an LLM call.
        Yields string chunks as they arrive.
        """
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "metadata": {
                "agent_id": agent_id,
                "debate_id": debate_id,
                "round_number": round_number,
            },
            "timeout": self._settings.agent_request_timeout,
        }

        try:
            response = await litellm.acompletion(**kwargs)
            async for chunk in response:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            logger.error("llm_stream_failed", agent_id=agent_id, error=str(e))
            raise LLMCallError(f"Streaming failed for {agent_id}: {e}") from e

    @staticmethod
    def extract_json(text: str) -> Dict[str, Any]:
        """
        Robustly extract a JSON object from LLM response text.
        Handles markdown code fences, extra prose before/after JSON.
        """
        # Try direct parse first
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to extract from markdown code block
        code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if code_block:
            try:
                return json.loads(code_block.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Find first { ... } block
        brace_match = re.search(r"\{[\s\S]*\}", text)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Could not extract JSON from LLM response: {text[:200]}...")

    @staticmethod
    def build_json_instruction(schema_description: str) -> str:
        """Return a standard instruction telling the LLM to output JSON."""
        return (
            f"You MUST respond with ONLY valid JSON matching this schema:\n"
            f"{schema_description}\n\n"
            "Do not include any prose, explanation, or markdown outside the JSON object."
        )
