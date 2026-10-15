"""Dual LLM Router and inference dispatcher for Marketing OS."""

import json
import time
from typing import Optional
from google import genai
from google.genai import types
import httpx

from core.config import settings
from core.logger import logfire, logger
from core.schemas import LLMEngine, LLMResponse, LLMTaskType


class LLMError(RuntimeError):
    """Exception raised when LLM inference fails across selected engines."""

    pass


def extract_json_payload(content: str) -> Optional[dict]:
    """Extract and parse a JSON object from text content."""
    if not content:
        return None

    raw = content.strip()
    # Handle markdown code blocks
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
        return {"data": parsed}
    except Exception:
        # Extract substring between first '{' and last '}'
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                candidate = json.loads(raw[start : end + 1])
                if isinstance(candidate, dict):
                    return candidate
                return {"data": candidate}
            except Exception:
                pass
    return None


def resolve_ollama_model(preferred_model: Optional[str] = None) -> str:
    """Resolve active Ollama model name, matching available local tags if possible."""
    if preferred_model:
        return preferred_model

    default_model = settings.OLLAMA_MODEL
    try:
        url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
        resp = httpx.get(url, timeout=2.0)
        if resp.status_code == 200:
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            if default_model in models:
                return default_model
            # Match any llama3.1 tag installed locally
            for model_name in models:
                if "llama3.1" in model_name:
                    return model_name
            if models:
                return models[0]
    except Exception:
        pass

    return default_model


def _call_ollama(
    prompt: str,
    system_prompt: str = "",
    task_type: LLMTaskType = LLMTaskType.TRIAGE_SCORING,
    model: Optional[str] = None,
    json_mode: bool = False,
) -> LLMResponse:
    """Execute inference against local Ollama instance with keep_alive: '1m' and Logfire telemetry."""
    model_name = resolve_ollama_model(model)
    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat"

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,  # "1m" mandatory for memory hygiene
    }
    if json_mode:
        payload["format"] = "json"

    task_value = task_type.value if hasattr(task_type, "value") else str(task_type)

    with logfire.span("llm_local", model=model_name, json_mode=json_mode) as span:
        # Before making the call, record the input
        logfire.info("LLM Input", prompt=prompt, system_prompt=system_prompt, task=task_value)
        span.set_attribute("gen_ai.prompt", prompt)
        span.set_attribute("gen_ai.system", system_prompt)

        start_time = time.perf_counter()
        try:
            with httpx.Client(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, Exception) as exc:
            raise LLMError(f"Ollama execution failed at {url}: {exc}") from exc

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        content = data.get("message", {}).get("content", "")
        prompt_tokens = data.get("prompt_eval_count")
        completion_tokens = data.get("eval_count")

        # After receiving the response, record the output
        logfire.info("LLM Output", response_content=content, latency_ms=latency_ms)
        span.set_attribute("gen_ai.completion", content)
        span.set_attribute("latency_ms", latency_ms)
        if prompt_tokens is not None:
            span.set_attribute("prompt_tokens", prompt_tokens)
        if completion_tokens is not None:
            span.set_attribute("completion_tokens", completion_tokens)

        raw_json = None
        if json_mode:
            raw_json = extract_json_payload(content)

        return LLMResponse(
            content=content,
            engine=LLMEngine.LOCAL,
            model_name=model_name,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            raw_json=raw_json,
        )


def _call_gemini(
    prompt: str,
    system_prompt: str = "",
    task_type: LLMTaskType = LLMTaskType.DRAFTING,
    model: Optional[str] = None,
    json_mode: bool = False,
) -> LLMResponse:
    """Execute inference against Gemini Flash via google-genai SDK and Logfire telemetry."""
    if not settings.GEMINI_API_KEY:
        raise LLMError("GEMINI_API_KEY is not configured in settings or environment.")

    model_name = model or settings.GEMINI_MODEL
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    config_kwargs = {}
    if system_prompt:
        config_kwargs["system_instruction"] = system_prompt
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"

    config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

    task_value = task_type.value if hasattr(task_type, "value") else str(task_type)

    with logfire.span("llm_gemini", model=model_name, json_mode=json_mode) as span:
        # Before making the call, record the input
        logfire.info("LLM Input", prompt=prompt, system_prompt=system_prompt, task=task_value)
        span.set_attribute("gen_ai.prompt", prompt)
        span.set_attribute("gen_ai.system", system_prompt)

        start_time = time.perf_counter()
        try:
            resp = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
        except Exception as exc:
            raise LLMError(f"Gemini execution failed for model {model_name}: {exc}") from exc

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        content = resp.text or ""

        prompt_tokens = None
        completion_tokens = None
        if resp.usage_metadata:
            prompt_tokens = getattr(resp.usage_metadata, "prompt_token_count", None)
            completion_tokens = getattr(resp.usage_metadata, "candidates_token_count", None)

        # After receiving the response, record the output
        logfire.info("LLM Output", response_content=content, latency_ms=latency_ms)
        span.set_attribute("gen_ai.completion", content)
        span.set_attribute("latency_ms", latency_ms)
        if prompt_tokens is not None:
            span.set_attribute("prompt_tokens", prompt_tokens)
        if completion_tokens is not None:
            span.set_attribute("completion_tokens", completion_tokens)

        raw_json = None
        if json_mode:
            raw_json = extract_json_payload(content)

        return LLMResponse(
            content=content,
            engine=LLMEngine.CLOUD,
            model_name=model_name,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            raw_json=raw_json,
        )


def call_llm(
    prompt: str,
    system_prompt: str = "",
    task_type: LLMTaskType = LLMTaskType.DRAFTING,
    json_mode: bool = False,
    force_engine: Optional[LLMEngine] = None,
    allow_fallback: bool = True,
) -> LLMResponse:
    """Route LLM inference based on task type with fallback and Logfire telemetry."""
    # Determine primary engine
    if force_engine is not None:
        primary_engine = force_engine
    elif task_type == LLMTaskType.TRIAGE_SCORING:
        primary_engine = LLMEngine.LOCAL
    else:
        primary_engine = LLMEngine.CLOUD

    with logfire.span("llm_call", engine=primary_engine.value, task=task_type.value) as span:
        span.set_attribute("json_mode", json_mode)
        span.set_attribute("forced_engine", primary_engine.value if force_engine else "none")
        span.set_attribute("gen_ai.prompt", prompt)
        span.set_attribute("gen_ai.system", system_prompt)

        try:
            if primary_engine == LLMEngine.LOCAL:
                response = _call_ollama(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    task_type=task_type,
                    json_mode=json_mode,
                )
            else:
                response = _call_gemini(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    task_type=task_type,
                    json_mode=json_mode,
                )

            span.set_attribute("model", response.model_name)
            span.set_attribute("latency_ms", response.latency_ms)
            span.set_attribute("gen_ai.completion", response.content)
            if response.prompt_tokens is not None:
                span.set_attribute("prompt_tokens", response.prompt_tokens)
            if response.completion_tokens is not None:
                span.set_attribute("completion_tokens", response.completion_tokens)
            return response

        except Exception as primary_exc:
            if not allow_fallback:
                logger.error(
                    f"LLM call failed on engine {primary_engine.value} (fallback disabled): {primary_exc}"
                )
                raise

            fallback_engine = (
                LLMEngine.CLOUD if primary_engine == LLMEngine.LOCAL else LLMEngine.LOCAL
            )
            logger.warning(
                f"Primary engine {primary_engine.value} failed: {primary_exc}. "
                f"Initiating graceful fallback to {fallback_engine.value}."
            )
            span.set_attribute("fallback_occurred", True)
            span.set_attribute("fallback_from", primary_engine.value)
            span.set_attribute("fallback_to", fallback_engine.value)

            try:
                if fallback_engine == LLMEngine.LOCAL:
                    response = _call_ollama(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        task_type=task_type,
                        json_mode=json_mode,
                    )
                else:
                    response = _call_gemini(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        task_type=task_type,
                        json_mode=json_mode,
                    )

                span.set_attribute("model", response.model_name)
                span.set_attribute("latency_ms", response.latency_ms)
                span.set_attribute("gen_ai.completion", response.content)
                if response.prompt_tokens is not None:
                    span.set_attribute("prompt_tokens", response.prompt_tokens)
                if response.completion_tokens is not None:
                    span.set_attribute("completion_tokens", response.completion_tokens)
                return response

            except Exception as fallback_exc:
                logger.error(
                    f"Fallback engine {fallback_engine.value} also failed: {fallback_exc}"
                )
                raise LLMError(
                    f"Primary engine {primary_engine.value} failed ({primary_exc}) "
                    f"and fallback {fallback_engine.value} failed ({fallback_exc})"
                ) from fallback_exc
