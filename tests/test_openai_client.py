from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.clients.openai_client import OpenAIClient
from app.config import LLMSettings
from app.models import PaperDetailResult


class FakeResponsesAPI:
    def __init__(self, parsed, errors: list[Exception] | None = None) -> None:
        self.parsed = parsed
        self.errors = list(errors or [])
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.errors:
            raise self.errors.pop(0)
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


class FakeFilesAPI:
    def __init__(
        self,
        *,
        create_status: str | None = None,
        retrieve_statuses: list[str] | None = None,
    ) -> None:
        self.create_status = create_status
        self.retrieve_statuses = list(retrieve_statuses or [])
        self.calls: list[dict] = []
        self.retrieve_calls: list[str] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        payload = {"id": "file-123"}
        if self.create_status is not None:
            payload["status"] = self.create_status
        return SimpleNamespace(**payload)

    def retrieve(self, file_id: str):
        self.retrieve_calls.append(file_id)
        status = self.retrieve_statuses.pop(0) if self.retrieve_statuses else "processed"
        return SimpleNamespace(id=file_id, status=status)


def _make_settings(endpoint: str, output_language: str = "English") -> LLMSettings:
    return LLMSettings(
        provider="openai",
        base_url="https://api.openai.com/v1",
        endpoint=endpoint,
        api_key="test-key",
        classify_model="gpt-5-mini",
        summarize_model="gpt-5.4",
        detail_model="doubao-seed-2-0-pro-260215",
        output_language=output_language,
        reasoning_effort="low",
        detail_reasoning_effort="high",
        timeout_seconds=30,
        detail_timeout_seconds=300,
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


def test_openai_client_uploads_pdf_and_uses_detail_model(tmp_path: Path):
    client = OpenAIClient(_make_settings("/responses"))
    fake_responses = FakeResponsesAPI(
        parsed=PaperDetailResult(
            source="pdf",
            headline="Detailed headline",
            contribution_summary="Contribution summary",
            problem_and_context="Problem and context",
            research_question="What is the paper solving?",
            method_overview="A PDF-grounded method overview.",
            novelty_and_positioning="Novelty and positioning",
            experimental_setup="Experimental setup",
            key_findings=["Finding 1"],
            evidence_and_credibility="Evidence and credibility",
            strengths=["Strength 1"],
            limitations=["Limitation 1"],
            practical_implications=["Practical implication 1"],
            open_questions=["Open question 1"],
            relevance_to_keywords="Relevant to the configured focus.",
            reading_guide=["Read the experiments."],
        )
    )
    fake_files = FakeFilesAPI()
    client._client = SimpleNamespace(
        responses=fake_responses,
        files=fake_files,
        beta=SimpleNamespace(chat=SimpleNamespace(completions=FakeChatAPI(parsed=None))),
    )
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%fake pdf\n")

    result = client.analyze_paper_pdf(
        pdf_path=pdf_path,
        title="Agent paper",
        abstract="This paper studies agent systems.",
        matched_keywords=["agent"],
        upload_expires_after_hours=24,
    )

    assert result.source == "pdf"
    assert len(fake_files.calls) == 1
    assert fake_files.calls[0]["purpose"] == "user_data"
    assert fake_files.calls[0]["expires_after"] == {"anchor": "created_at", "seconds": 86400}
    assert len(fake_responses.calls) == 1
    assert fake_responses.calls[0]["model"] == "doubao-seed-2-0-pro-260215"
    assert fake_responses.calls[0]["reasoning"] == {"effort": "high"}
    assert fake_responses.calls[0]["timeout"] == 300
    input_payload = fake_responses.calls[0]["input"]
    assert input_payload[1]["content"][1] == {"type": "input_file", "file_id": "file-123"}
    assert "comprehensive but scannable paper analysis" in input_payload[1]["content"][0]["text"]


def test_openai_client_waits_for_uploaded_pdf_processing(tmp_path: Path, monkeypatch) -> None:
    client = OpenAIClient(_make_settings("/responses"))
    fake_responses = FakeResponsesAPI(
        parsed=PaperDetailResult(
            source="pdf",
            headline="Detailed headline",
            contribution_summary="Contribution summary",
            problem_and_context="Problem and context",
            research_question="What is the paper solving?",
            method_overview="A PDF-grounded method overview.",
            novelty_and_positioning="Novelty and positioning",
            experimental_setup="Experimental setup",
            key_findings=["Finding 1"],
            evidence_and_credibility="Evidence and credibility",
            strengths=["Strength 1"],
            limitations=["Limitation 1"],
            practical_implications=["Practical implication 1"],
            open_questions=["Open question 1"],
            relevance_to_keywords="Relevant to the configured focus.",
            reading_guide=["Read the experiments."],
        )
    )
    fake_files = FakeFilesAPI(
        create_status="processing",
        retrieve_statuses=["processing", "processed"],
    )
    client._client = SimpleNamespace(
        responses=fake_responses,
        files=fake_files,
        beta=SimpleNamespace(chat=SimpleNamespace(completions=FakeChatAPI(parsed=None))),
    )
    sleep_calls: list[float] = []
    monkeypatch.setattr(
        "app.clients.openai_client.time.sleep",
        lambda seconds: sleep_calls.append(seconds),
    )
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%fake pdf\n")

    result = client.analyze_paper_pdf(
        pdf_path=pdf_path,
        title="Agent paper",
        abstract="This paper studies agent systems.",
        matched_keywords=["agent"],
        upload_expires_after_hours=24,
    )

    assert result.source == "pdf"
    assert fake_files.retrieve_calls == ["file-123", "file-123"]
    assert sleep_calls == [client.FILE_READY_POLL_SECONDS]
    assert len(fake_responses.calls) == 1


def test_openai_client_retries_when_response_api_sees_processing_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client = OpenAIClient(_make_settings("/responses"))
    fake_responses = FakeResponsesAPI(
        parsed=PaperDetailResult(
            source="pdf",
            headline="Detailed headline",
            contribution_summary="Contribution summary",
            problem_and_context="Problem and context",
            research_question="What is the paper solving?",
            method_overview="A PDF-grounded method overview.",
            novelty_and_positioning="Novelty and positioning",
            experimental_setup="Experimental setup",
            key_findings=["Finding 1"],
            evidence_and_credibility="Evidence and credibility",
            strengths=["Strength 1"],
            limitations=["Limitation 1"],
            practical_implications=["Practical implication 1"],
            open_questions=["Open question 1"],
            relevance_to_keywords="Relevant to the configured focus.",
            reading_guide=["Read the experiments."],
        ),
        errors=[
            RuntimeError(
                "OperationDenied.InvalidState: The specified file file-123 is in invalid state: processing. param: file_id"
            )
        ],
    )
    fake_files = FakeFilesAPI(create_status="processed", retrieve_statuses=["processed"])
    client._client = SimpleNamespace(
        responses=fake_responses,
        files=fake_files,
        beta=SimpleNamespace(chat=SimpleNamespace(completions=FakeChatAPI(parsed=None))),
    )
    monkeypatch.setattr("app.clients.openai_client.time.sleep", lambda _: None)
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%fake pdf\n")

    result = client.analyze_paper_pdf(
        pdf_path=pdf_path,
        title="Agent paper",
        abstract="This paper studies agent systems.",
        matched_keywords=["agent"],
        upload_expires_after_hours=24,
    )

    assert result.source == "pdf"
    assert len(fake_responses.calls) == 2
    assert fake_files.retrieve_calls == ["file-123"]
