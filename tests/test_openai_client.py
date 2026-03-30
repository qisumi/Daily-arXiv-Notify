from __future__ import annotations

from types import SimpleNamespace

from app.clients.openai_client import OpenAIClient
from app.config import LLMSettings


class FakeResponsesAPI:
    def __init__(self, parsed) -> None:
        self.parsed = parsed
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=self.parsed)


class FakeChatAPI:
    def __init__(self, parsed) -> None:
        self.parsed = parsed
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(parsed=self.parsed)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


def _make_settings(endpoint: str) -> LLMSettings:
    return LLMSettings(
        provider="openai",
        base_url="https://api.openai.com/v1",
        endpoint=endpoint,
        api_key="test-key",
        classify_model="gpt-5-mini",
        summarize_model="gpt-5.4",
        reasoning_effort="low",
        timeout_seconds=30,
    )


def test_openai_client_uses_responses_api_for_responses_endpoint():
    client = OpenAIClient(_make_settings("/responses"))
    fake_responses = FakeResponsesAPI(parsed=SimpleNamespace(is_related=True, matched_keywords=["agent"], reason="ok"))
    fake_chat = FakeChatAPI(parsed=None)
    client._client = SimpleNamespace(
        responses=fake_responses,
        beta=SimpleNamespace(chat=SimpleNamespace(completions=fake_chat)),
    )

    result = client.classify_paper(
        keywords=["agent"],
        title="Agent paper",
        abstract="This paper studies agent systems.",
    )

    assert result.is_related is True
    assert len(fake_responses.calls) == 1
    assert len(fake_chat.calls) == 0


def test_openai_client_uses_chat_api_for_chat_endpoint():
    client = OpenAIClient(_make_settings("/chat/completions"))
    fake_responses = FakeResponsesAPI(parsed=None)
    fake_chat = FakeChatAPI(parsed=SimpleNamespace(is_related=True, matched_keywords=["agent"], reason="ok"))
    client._client = SimpleNamespace(
        responses=fake_responses,
        beta=SimpleNamespace(chat=SimpleNamespace(completions=fake_chat)),
    )

    result = client.classify_paper(
        keywords=["agent"],
        title="Agent paper",
        abstract="This paper studies agent systems.",
    )

    assert result.is_related is True
    assert len(fake_responses.calls) == 0
    assert len(fake_chat.calls) == 1
