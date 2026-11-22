"""An Inspect AI model that answers through the Claude Code command line.

It lets the study run on a Claude subscription when there is no API key:

    --model claude-code/haiku

This is not the same call as the API makes. Claude Code adds about 1,000
tokens of its own context to every request, even with the system prompt
replaced and every tool switched off. Results made this way are kept apart
from the API results and labelled.

The binary is found on PATH, or named in KNOWNBAD_CLAUDE_BIN.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile

from inspect_ai.model import (
    ChatMessageSystem,
    ChatMessageUser,
    GenerateConfig,
    ModelAPI,
    ModelOutput,
    ModelUsage,
    modelapi,
)

ATTEMPTS = 4
# Texts the command line prints when the subscription's limit is reached.
LIMIT_WORDS = ("usage limit", "rate limit", "limit reached", "out of extra usage")


class LimitReached(RuntimeError):
    """The subscription will not answer more calls for now."""


def split(messages: list) -> tuple[str, str]:
    """The system prompt and the one user message a judge sends."""
    system = [m.text for m in messages if isinstance(m, ChatMessageSystem)]
    users = [m.text for m in messages if isinstance(m, ChatMessageUser)]
    if len(users) != 1 or len(system) + len(users) != len(messages):
        raise ValueError("claude-code takes one user message and at most a system prompt")
    return "\n\n".join(system), users[0]


def read(reply: str) -> tuple[str, ModelUsage]:
    """The answer and the token use from the command line's JSON."""
    data = json.loads(reply)
    text = data.get("result")
    if data.get("is_error") or not isinstance(text, str):
        message = str(text or data.get("subtype") or "no result")
        if any(word in message.lower() for word in LIMIT_WORDS):
            raise LimitReached(message)
        raise RuntimeError(f"claude-code: {message[:200]}")
    use = data.get("usage") or {}
    written = use.get("cache_creation_input_tokens", 0)
    cached = use.get("cache_read_input_tokens", 0)
    tokens_in = use.get("input_tokens", 0) + written + cached
    tokens_out = use.get("output_tokens", 0)
    return text, ModelUsage(
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        total_tokens=tokens_in + tokens_out,
        input_tokens_cache_write=written,
        input_tokens_cache_read=cached,
    )


@modelapi(name="claude-code")
class ClaudeCode(ModelAPI):
    def __init__(
        self,
        model_name: str,
        base_url: str | None = None,
        api_key: str | None = None,
        config: GenerateConfig = GenerateConfig(),  # noqa: B008
        **model_args: object,
    ) -> None:
        super().__init__(model_name, base_url, api_key, [], config)
        binary = os.environ.get("KNOWNBAD_CLAUDE_BIN") or shutil.which("claude")
        if not binary:
            raise RuntimeError("no claude binary on PATH; set KNOWNBAD_CLAUDE_BIN")
        self.binary = binary
        # An empty folder: no project instructions or memory reach the judge.
        self.folder = tempfile.mkdtemp(prefix="knownbad-judge-")

    def command(self, system: str) -> list[str]:
        return [
            self.binary,
            "--print",
            "--model",
            self.model_name,
            "--system-prompt",
            system,
            "--tools",
            "",
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--no-session-persistence",
            "--output-format",
            "json",
        ]

    async def generate(self, input, tools, tool_choice, config) -> ModelOutput:  # noqa: A002
        if tools:
            raise ValueError("claude-code is a judge only: it takes no tools")
        system, prompt = split(input)
        # The key is taken out so the call is made on the subscription, not billed to a key.
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        error: Exception | None = None
        for attempt in range(ATTEMPTS):
            process = await asyncio.create_subprocess_exec(
                *self.command(system),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.folder,
                env=env,
            )
            out, err = await process.communicate(prompt.encode())
            try:
                text, usage = read(out.decode())
            except LimitReached:
                raise
            except (ValueError, RuntimeError) as problem:
                error = RuntimeError(f"{problem} {err.decode()[:200]}".strip())
                await asyncio.sleep(2 * 2**attempt)
                continue
            output = ModelOutput.from_content(self.model_name, text)
            output.usage = usage
            return output
        raise error or RuntimeError("claude-code: no reply")

    def max_connections(self) -> int:
        return 4
