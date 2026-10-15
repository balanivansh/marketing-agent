"""Integration and unit tests for the Dual LLM Router."""

import unittest
from unittest.mock import patch
import httpx

from core.config import settings
from core.router import LLMError, call_llm
from core.schemas import LLMEngine, LLMResponse, LLMTaskType


class TestRouter(unittest.TestCase):
    """Test suite for Dual LLM Router and fallback mechanisms."""

    def test_local_ollama(self):
        """Test local Ollama inference with TRIAGE_SCORING in JSON mode."""
        prompt = (
            "Score the relevance of this tech headline: 'Apple announces M5 chip' "
            "for an AI developer. Return JSON {'relevance': float, 'reason': str}."
        )
        response: LLMResponse = call_llm(
            prompt=prompt,
            task_type=LLMTaskType.TRIAGE_SCORING,
            json_mode=True,
            force_engine=LLMEngine.LOCAL,
            allow_fallback=False,
        )

        self.assertEqual(response.engine, LLMEngine.LOCAL)
        self.assertTrue(len(response.content.strip()) > 0)
        self.assertGreater(response.latency_ms, 0)
        self.assertIsNotNone(response.raw_json)
        self.assertIsInstance(response.raw_json, dict)
        self.assertTrue(
            "relevance" in response.raw_json or "data" in response.raw_json or len(response.raw_json) > 0
        )

    def test_gemini_flash(self):
        """Test Gemini Flash cloud inference with IDEATION task."""
        prompt = (
            "Give 2 short hook ideas for a fitness reel about progressive overload. "
            "Keep under 10 words each."
        )
        response: LLMResponse = call_llm(
            prompt=prompt,
            task_type=LLMTaskType.IDEATION,
            force_engine=LLMEngine.CLOUD,
            allow_fallback=False,
        )

        self.assertEqual(response.engine, LLMEngine.CLOUD)
        self.assertIsInstance(response.content, str)
        self.assertTrue(len(response.content.strip()) > 0)
        self.assertGreater(response.latency_ms, 0)
        if response.prompt_tokens is not None:
            self.assertGreater(response.prompt_tokens, 0)

    def test_engine_fallback(self):
        """Verify error handling and fallback behavior when an engine fails or is forced."""
        # 1. Verify forced engine routing
        # Forcing CLOUD on TRIAGE_SCORING (which defaults to LOCAL)
        forced_cloud_resp = call_llm(
            prompt="Reply with the single word: OK",
            task_type=LLMTaskType.TRIAGE_SCORING,
            force_engine=LLMEngine.CLOUD,
            allow_fallback=False,
        )
        self.assertEqual(forced_cloud_resp.engine, LLMEngine.CLOUD)
        self.assertIn("OK", forced_cloud_resp.content.upper())

        # 2. Verify graceful fallback: when LOCAL fails, router falls back to CLOUD
        with patch("core.router._call_ollama", side_effect=LLMError("Simulated Ollama daemon offline")):
            fallback_resp = call_llm(
                prompt="Reply with the single word: PONG",
                task_type=LLMTaskType.TRIAGE_SCORING,
                allow_fallback=True,
            )
            # Must fall back gracefully to CLOUD
            self.assertEqual(fallback_resp.engine, LLMEngine.CLOUD)
            self.assertTrue(len(fallback_resp.content.strip()) > 0)

        # 3. Verify clean error raising when an engine is forced without fallback and fails
        with patch("core.router._call_ollama", side_effect=LLMError("Connection refused")):
            with self.assertRaises(LLMError) as ctx:
                call_llm(
                    prompt="Test prompt",
                    force_engine=LLMEngine.LOCAL,
                    allow_fallback=False,
                )
            self.assertIn("Connection refused", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
