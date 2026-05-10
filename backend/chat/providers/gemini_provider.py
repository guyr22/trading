import json
import os
import time
from typing import Iterator

import google.generativeai as genai

from chat.providers.base import BaseChatProvider
from chat.tool_registry import TOOL_REGISTRY
from core.config import MAX_TOOL_ROUNDS
from core.logging import get_logger

logger = get_logger(__name__)


class GeminiProvider(BaseChatProvider):
    def __init__(self, model_variant: str = "gemini") -> None:
        self._model_name = (
            "gemini-3-flash-preview" if model_variant == "gemini" else "gemini-2.5-flash"
        )

    def _configure(self) -> None:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("Google API key is not configured")
        genai.configure(api_key=api_key)

    def _stream_with_tools_impl(self, messages, system_prompt, executor) -> Iterator[str]:
        try:
            self._configure()
        except ValueError as e:
            yield json.dumps({"error": str(e)}) + "\n"
            return

        model = genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=system_prompt,
            tools=TOOL_REGISTRY.gemini_format,
        )
        history = [
            {"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]}
            for m in messages[:-1]
        ]
        chat = model.start_chat(history=history)
        logger.info("Gemini API call  round=0  msgs=%d", len(messages))
        t0 = time.perf_counter()
        response = chat.send_message(messages[-1]["content"])
        logger.info("Gemini API response  round=0  %.2fs", time.perf_counter() - t0)

        for round_num in range(MAX_TOOL_ROUNDS):
            fn_calls = [
                p.function_call
                for p in response.candidates[0].content.parts
                if hasattr(p, "function_call") and p.function_call.name
            ]
            if fn_calls:
                tool_responses = []
                for fc in fn_calls:
                    yield json.dumps({"tool_call": fc.name}) + "\n"
                    t1 = time.perf_counter()
                    result = executor.execute(fc.name, dict(fc.args))
                    logger.info("Tool done  name=%s  %.2fs", fc.name, time.perf_counter() - t1)
                    tool_responses.append({
                        "function_response": {
                            "name": fc.name,
                            "response": {"result": result},
                        }
                    })
                logger.info("Gemini API call  round=%d", round_num + 1)
                t2 = time.perf_counter()
                response = chat.send_message(tool_responses)
                logger.info("Gemini API response  round=%d  %.2fs", round_num + 1, time.perf_counter() - t2)
            else:
                yield json.dumps({"t": response.text}) + "\n"
                return

        yield json.dumps({"error": "Tool loop exceeded maximum rounds"}) + "\n"

    def _stream_technical_impl(self, messages, system_prompt, images) -> Iterator[str]:
        try:
            self._configure()
        except ValueError as e:
            yield json.dumps({"error": str(e)}) + "\n"
            return

        model = genai.GenerativeModel(model_name=self._model_name, system_instruction=system_prompt)
        history = [
            {"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]}
            for m in messages[:-1]
        ]
        chat_session = model.start_chat(history=history)
        last_text = messages[-1]["content"] if messages else ""
        parts: list = [{"mime_type": mt, "data": raw} for mt, raw, _ in images]
        parts.append(last_text)

        for chunk in chat_session.send_message(parts, stream=True):
            if chunk.text:
                yield json.dumps({"t": chunk.text}) + "\n"
