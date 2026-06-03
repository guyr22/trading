import json
import os
import re
import time
from typing import Iterator

import google.generativeai as genai
from google.api_core import exceptions as gax

from chat.providers.base import BaseChatProvider
from chat.tool_registry import TOOL_REGISTRY
from core.config import MAX_TOOL_ROUNDS
from core.logging import get_logger

logger = get_logger(__name__)


def _quota_message(err: Exception) -> str:
    """Turn a raw Gemini 429 into a short, actionable message for the user."""
    retry = re.search(r"retry in ([\d.]+)s", str(err), re.IGNORECASE)
    wait = f" Try again in about {round(float(retry.group(1)))}s." if retry else ""
    return (
        "This model's request limit was reached (free-tier quota)." + wait +
        " You can switch models from the chat toolbar, or raise the limit by enabling billing."
    )


class GeminiProvider(BaseChatProvider):
    def __init__(self, model_variant: str = "gemini") -> None:
        self._model_name = {
            "gemini": "gemini-3-flash-preview",
            "gemini25": "gemini-2.5-flash",
            "gemini35": "gemini-3.5-flash",
        }.get(model_variant, "gemini-3-flash-preview")

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

        def _send(payload, round_num):
            logger.info("Gemini API call  round=%d", round_num)
            t = time.perf_counter()
            resp = chat.send_message(payload)
            logger.info("Gemini API response  round=%d  %.2fs", round_num, time.perf_counter() - t)
            return resp

        try:
            response = _send(messages[-1]["content"], 0)
        except gax.ResourceExhausted as e:
            logger.warning("Gemini quota exhausted: %s", e)
            yield json.dumps({"error": _quota_message(e)}) + "\n"
            return

        for round_num in range(MAX_TOOL_ROUNDS):
            fn_calls = [
                p.function_call
                for p in response.candidates[0].content.parts
                if hasattr(p, "function_call") and p.function_call.name
            ]
            if not fn_calls:
                yield json.dumps({"t": response.text}) + "\n"
                return

            tool_responses = []
            for fc in fn_calls:
                yield json.dumps({"tool_call": fc.name}) + "\n"
                t1 = time.perf_counter()
                result = executor.execute(fc.name, dict(fc.args))
                logger.info("Tool done  name=%s  %.2fs", fc.name, time.perf_counter() - t1)
                tool_responses.append({
                    "function_response": {"name": fc.name, "response": {"result": result}}
                })
            try:
                response = _send(tool_responses, round_num + 1)
            except gax.ResourceExhausted as e:
                logger.warning("Gemini quota exhausted mid-tool-loop: %s", e)
                yield json.dumps({"error": _quota_message(e)}) + "\n"
                return

        # Tool budget exhausted: ask once more with tools disabled so the user still
        # gets a written answer from the data already gathered, instead of an error.
        logger.info("Gemini tool loop hit MAX_TOOL_ROUNDS — final answer without tools")
        try:
            final_model = genai.GenerativeModel(
                model_name=self._model_name, system_instruction=system_prompt
            )
            final_chat = final_model.start_chat(history=chat.history)
            final = final_chat.send_message(
                "Answer the user's question now using the data already gathered above. "
                "Do not request any more tools."
            )
            yield json.dumps({"t": final.text}) + "\n"
        except gax.ResourceExhausted as e:
            yield json.dumps({"error": _quota_message(e)}) + "\n"
        except Exception as e:
            logger.warning("Gemini final-answer fallback failed: %s", e)
            yield json.dumps({"error": "Could not complete the analysis — please try a simpler question."}) + "\n"

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
