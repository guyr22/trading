import json
import os
import time
from typing import Iterator

import openai

from chat.providers.base import BaseChatProvider
from chat.tool_registry import TOOL_REGISTRY
from core.config import MAX_TOOL_ROUNDS
from core.logging import get_logger

logger = get_logger(__name__)


class OpenAIProvider(BaseChatProvider):

    def _client(self) -> openai.OpenAI:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key is not configured")
        return openai.OpenAI(api_key=api_key)

    def _stream_with_tools_impl(self, messages, system_prompt, executor) -> Iterator[str]:
        try:
            client = self._client()
        except ValueError as e:
            yield json.dumps({"error": str(e)}) + "\n"
            return

        msgs = [{"role": "system", "content": system_prompt}] + list(messages)
        for round_num in range(MAX_TOOL_ROUNDS):
            logger.info("OpenAI API call  round=%d  msgs=%d", round_num, len(msgs))
            t0 = time.perf_counter()
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    max_tokens=2048,
                    messages=msgs,
                    tools=TOOL_REGISTRY.openai_format,
                )
            except openai.RateLimitError:
                yield json.dumps({"error": "OpenAI rate limit reached — try again in a moment"}) + "\n"
                return
            except openai.AuthenticationError:
                yield json.dumps({"error": "Invalid OpenAI API key"}) + "\n"
                return
            except openai.APIError as e:
                yield json.dumps({"error": f"OpenAI error: {str(e)}"}) + "\n"
                return
            finish_reason = response.choices[0].finish_reason
            logger.info("OpenAI API response  round=%d  finish_reason=%s  %.2fs", round_num, finish_reason, time.perf_counter() - t0)

            msg = response.choices[0].message
            if msg.tool_calls:
                msgs.append(msg)
                for tc in msg.tool_calls:
                    yield json.dumps({"tool_call": tc.function.name}) + "\n"
                    args = json.loads(tc.function.arguments)
                    t1 = time.perf_counter()
                    result = executor.execute(tc.function.name, args)
                    logger.info("Tool done  name=%s  %.2fs", tc.function.name, time.perf_counter() - t1)
                    msgs.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
            else:
                yield json.dumps({"t": msg.content or ""}) + "\n"
                return

        yield json.dumps({"error": "Tool loop exceeded maximum rounds"}) + "\n"

    def _stream_technical_impl(self, messages, system_prompt, images) -> Iterator[str]:
        try:
            client = self._client()
        except ValueError as e:
            yield json.dumps({"error": str(e)}) + "\n"
            return

        history = messages[:-1]
        last_text = messages[-1]["content"] if messages else ""
        # images is list of (media_type, raw_bytes, b64); for OpenAI we need the original data URLs
        # The router passes the raw data_urls separately as the fourth element
        content: list = []
        for mt, _, b64 in images:
            content.append({"type": "image_url", "image_url": {"url": f"data:{mt};base64,{b64}"}})
        content.append({"type": "text", "text": last_text})

        full_msgs = [{"role": "system", "content": system_prompt}]
        full_msgs += [{"role": m["role"], "content": m["content"]} for m in history]
        full_msgs.append({"role": "user", "content": content})

        try:
            for chunk in client.chat.completions.create(
                model="gpt-4o", max_tokens=2048, messages=full_msgs, stream=True
            ):
                text = chunk.choices[0].delta.content or ""
                if text:
                    yield json.dumps({"t": text}) + "\n"
        except openai.RateLimitError:
            yield json.dumps({"error": "OpenAI rate limit reached — try again in a moment"}) + "\n"
        except openai.AuthenticationError:
            yield json.dumps({"error": "Invalid OpenAI API key"}) + "\n"
        except openai.APIError as e:
            yield json.dumps({"error": f"OpenAI error: {str(e)}"}) + "\n"
