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
            # Streaming: text deltas are forwarded live; tool-call deltas arrive in
            # fragments (name + arguments split across chunks) and must be reassembled
            # per tool_call index before execution.
            content = ""
            tool_calls: dict[int, dict] = {}
            try:
                stream = client.chat.completions.create(
                    model="gpt-4o-mini",
                    max_tokens=2048,
                    messages=msgs,
                    tools=TOOL_REGISTRY.openai_format,
                    stream=True,
                )
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta.content:
                        content += delta.content
                        yield json.dumps({"t": delta.content}) + "\n"
                    for tcd in (delta.tool_calls or []):
                        slot = tool_calls.setdefault(tcd.index, {"id": "", "name": "", "args": ""})
                        if tcd.id:
                            slot["id"] = tcd.id
                        if tcd.function and tcd.function.name:
                            slot["name"] = tcd.function.name
                        if tcd.function and tcd.function.arguments:
                            slot["args"] += tcd.function.arguments
            except openai.RateLimitError:
                yield json.dumps({"error": "OpenAI rate limit reached — try again in a moment"}) + "\n"
                return
            except openai.AuthenticationError:
                yield json.dumps({"error": "Invalid OpenAI API key"}) + "\n"
                return
            except openai.APIError as e:
                yield json.dumps({"error": f"OpenAI error: {str(e)}"}) + "\n"
                return
            logger.info("OpenAI API response  round=%d  tool_calls=%d  %.2fs", round_num, len(tool_calls), time.perf_counter() - t0)

            if tool_calls:
                ordered = [tool_calls[i] for i in sorted(tool_calls)]
                msgs.append({
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": [
                        {"id": c["id"], "type": "function",
                         "function": {"name": c["name"], "arguments": c["args"] or "{}"}}
                        for c in ordered
                    ],
                })
                for c in ordered:
                    yield json.dumps({"tool_call": c["name"]}) + "\n"
                    args = json.loads(c["args"] or "{}")
                    t1 = time.perf_counter()
                    result = executor.execute(c["name"], args)
                    logger.info("Tool done  name=%s  %.2fs", c["name"], time.perf_counter() - t1)
                    msgs.append({"role": "tool", "tool_call_id": c["id"], "content": result})
            else:
                return  # final answer already streamed token-by-token

        # Tool budget exhausted: one final call with tools disabled so the user still
        # gets a written answer from the data already gathered, instead of an error.
        logger.info("OpenAI tool loop hit MAX_TOOL_ROUNDS — final answer without tools")
        try:
            for chunk in client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=2048,
                messages=msgs + [{
                    "role": "user",
                    "content": "Answer my question now using the data already gathered. Do not call any more tools.",
                }],
                stream=True,
            ):
                if chunk.choices and chunk.choices[0].delta.content:
                    yield json.dumps({"t": chunk.choices[0].delta.content}) + "\n"
        except openai.APIError as e:
            yield json.dumps({"error": f"OpenAI error: {str(e)}"}) + "\n"

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
