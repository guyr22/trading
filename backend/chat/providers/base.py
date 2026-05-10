"""Strategy interface for all chat providers."""
import json
import traceback
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Iterator

from core.logging import get_logger

if TYPE_CHECKING:
    from chat.tool_executor import ToolExecutor

logger = get_logger(__name__)


class BaseChatProvider(ABC):

    # ---- Abstract contract --------------------------------------------------

    @abstractmethod
    def _stream_with_tools_impl(
        self,
        messages: list[dict],
        system_prompt: str,
        executor: "ToolExecutor",
    ) -> Iterator[str]: ...

    @abstractmethod
    def _stream_technical_impl(
        self,
        messages: list[dict],
        system_prompt: str,
        images: list[tuple[str, bytes, str]],  # (media_type, raw_bytes, b64_str)
    ) -> Iterator[str]: ...

    # ---- Public entry points (add done/error wrapper) -----------------------

    def stream_with_tools(
        self,
        messages: list[dict],
        system_prompt: str,
        executor: "ToolExecutor",
        provider_name: str = "",
    ) -> Iterator[str]:
        try:
            yield from self._stream_with_tools_impl(messages, system_prompt, executor)
        except Exception as e:
            msg = str(e)
            logger.error("Chat stream error (%s): %s\n%s", provider_name, msg, traceback.format_exc())
            yield json.dumps({"error": f"Provider error: {msg}"}) + "\n"
            return
        yield json.dumps({"done": True}) + "\n"

    def stream_technical(
        self,
        messages: list[dict],
        system_prompt: str,
        images: list[tuple[str, bytes, str]],
        provider_name: str = "",
    ) -> Iterator[str]:
        try:
            yield from self._stream_technical_impl(messages, system_prompt, images)
        except Exception as e:
            msg = str(e)
            logger.error("Technical chat stream error (%s): %s\n%s", provider_name, msg, traceback.format_exc())
            yield json.dumps({"error": f"Provider error: {msg}"}) + "\n"
            return
        yield json.dumps({"done": True}) + "\n"
