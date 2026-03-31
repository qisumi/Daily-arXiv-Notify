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


def _make_settings(endpoint: str, output_language: str = "English") -> LLMSettings:
    return LLMSettings(
        provider="openai",
        base_url="https://api.openai.com/v1",
        endpoint=endpoint,
        api_key="test-key",
        classify_model="gpt-5-mini",
        summarize_model="gpt-5.4",
        output_language=output_language,
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


def test_openai_client_includes_output_language_in_prompts():
    client = OpenAIClient(_make_settings("/responses", output_language="Chinese"))
    fake_responses = FakeResponsesAPI(
        parsed=SimpleNamespace(
            one_line="摘要",
            problem="问题",
            method="方法",
            why_it_matters="意义",
            limitations="限制",
            tags=["agent"],
        )
    )
    client._client = SimpleNamespace(
        responses=fake_responses,
        beta=SimpleNamespace(chat=SimpleNamespace(completions=FakeChatAPI(parsed=None))),
    )

    result = client.summarize_paper(
        title="Agent paper",
        abstract="This paper studies agent systems.",
    )

    assert result.one_line == "摘要"
    assert len(fake_responses.calls) == 1
    messages = fake_responses.calls[0]["input"]
    assert any("Chinese" in message["content"] for message in messages)
