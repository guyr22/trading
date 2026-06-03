import json
import os
import time
from typing import Iterator

import anthropic

from chat.providers.base import BaseChatProvider
from chat.tool_registry import TOOL_REGISTRY
from core.config import MAX_TOOL_ROUNDS
from core.logging import get_logger

logger = get_logger(__name__)


class ClaudeProvider(BaseChatProvider):

    def _client(self) -> anthropic.Anthropic:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("Anthropic API key is not configured")
        return anthropic.Anthropic(api_key=api_key)

    def _stream_with_tools_impl(self, messages, system_prompt, executor) -> Iterator[str]:
        try:
            client = self._client()
        except ValueError as e:
            yield json.dumps({"error": str(e)}) + "\n"
            return

        msgs = list(messages)
        for round_num in range(MAX_TOOL_ROUNDS):
            logger.info("Claude API call  round=%d  msgs=%d", round_num, len(msgs))
            t0 = time.perf_counter()
            try:
                with client.messages.stream(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=2048,
                    system=system_prompt,
                    messages=msgs,
                    tools=TOOL_REGISTRY.claude_format,
                ) as stream:
                    # Forward the model's prose token-by-token as it is generated.
                    for text in stream.text_stream:
                        yield json.dumps({"t": text}) + "\n"
                    response = stream.get_final_message()
            except anthropic.RateLimitError:
                yield json.dumps({"error": "Claude rate limit reached — try again in a moment"}) + "\n"
                return
            except anthropic.AuthenticationError:
                yield json.dumps({"error": "Invalid Anthropic API key"}) + "\n"
                return
            except anthropic.APIError as e:
                yield json.dumps({"error": f"Claude error: {e.message}"}) + "\n"
                return
            logger.info("Claude API response  round=%d  stop_reason=%s  %.2fs", round_num, response.stop_reason, time.perf_counter() - t0)

            if response.stop_reason == "tool_use":
                msgs.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        yield json.dumps({"tool_call": block.name}) + "\n"
                        t1 = time.perf_counter()
                        result = executor.execute(block.name, block.input)
                        logger.info("Tool done  name=%s  %.2fs", block.name, time.perf_counter() - t1)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                msgs.append({"role": "user", "content": tool_results})
            else:
                return  # final answer already streamed token-by-token

        # Tool budget exhausted: one final call with tools disabled so the user still
        # gets a written answer from the data already gathered, instead of an error.
        logger.info("Claude tool loop hit MAX_TOOL_ROUNDS — final answer without tools")
        try:
            with client.messages.stream(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                system=system_prompt,
                messages=msgs + [{
                    "role": "user",
                    "content": "Answer my question now using the data already gathered. Do not call any more tools.",
                }],
            ) as stream:
                for text in stream.text_stream:
                    yield json.dumps({"t": text}) + "\n"
        except anthropic.APIError as e:
            yield json.dumps({"error": f"Claude error: {e.message}"}) + "\n"

    def _stream_technical_impl(self, messages, system_prompt, images) -> Iterator[str]:
        try:
            client = self._client()
        except ValueError as e:
            yield json.dumps({"error": str(e)}) + "\n"
            return

        history = messages[:-1]
        last_text = messages[-1]["content"] if messages else ""
        content: list = [
            {"type": "image", "source": {"type": "base64", "media_type": mt, "data": b64}}
            for mt, _, b64 in images
        ]
        content.append({"type": "text", "text": last_text})
        full_msgs = [{"role": m["role"], "content": m["content"]} for m in history]
        full_msgs.append({"role": "user", "content": content})

        try:
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=system_prompt,
                messages=full_msgs,
            ) as stream:
                for text in stream.text_stream:
                    yield json.dumps({"t": text}) + "\n"
        except anthropic.RateLimitError:
            yield json.dumps({"error": "Claude rate limit reached — try again in a moment"}) + "\n"
        except anthropic.AuthenticationError:
            yield json.dumps({"error": "Invalid Anthropic API key"}) + "\n"
        except anthropic.APIError as e:
            yield json.dumps({"error": f"Claude error: {e.message}"}) + "\n"
