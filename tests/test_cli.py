from __future__ import annotations

from types import SimpleNamespace

import app.cli as cli


def test_run_once_runs_all_subscriptions(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    default = SimpleNamespace(subscription_id="default")
    extra = SimpleNamespace(subscription_id="llm-data-synthesis")
    settings = SimpleNamespace(runtime_subscriptions=[default, extra])

    class FakePipeline:
        def __init__(self, subscription_settings) -> None:
            self.subscription_settings = subscription_settings
            calls.append(("init", subscription_settings.subscription_id))

        def run(self, *, dry_run: bool) -> int:
            calls.append(("run", self.subscription_settings.subscription_id))
            return 101 if self.subscription_settings.subscription_id == "default" else 202

        def close(self) -> None:
            calls.append(("close", self.subscription_settings.subscription_id))

    monkeypatch.setattr(cli, "load_settings", lambda _config_path: settings)
    monkeypatch.setattr(cli, "DailyDigestPipeline", FakePipeline)

    status = cli.run_once(config_path="config.toml", dry_run=True, verbose=False)

    assert status == 0
    assert calls == [
        ("init", "default"),
        ("run", "default"),
        ("close", "default"),
        ("init", "llm-data-synthesis"),
        ("run", "llm-data-synthesis"),
        ("close", "llm-data-synthesis"),
    ]


def test_run_once_continues_after_subscription_failure(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    default = SimpleNamespace(subscription_id="default")
    extra = SimpleNamespace(subscription_id="llm-data-synthesis")
    settings = SimpleNamespace(runtime_subscriptions=[default, extra])

    class FakePipeline:
        def __init__(self, subscription_settings) -> None:
            self.subscription_settings = subscription_settings
            calls.append(("init", subscription_settings.subscription_id))

        def run(self, *, dry_run: bool) -> int:
            calls.append(("run", self.subscription_settings.subscription_id))
            if self.subscription_settings.subscription_id == "default":
                raise RuntimeError("boom")
            return 202

        def close(self) -> None:
            calls.append(("close", self.subscription_settings.subscription_id))

    monkeypatch.setattr(cli, "load_settings", lambda _config_path: settings)
    monkeypatch.setattr(cli, "DailyDigestPipeline", FakePipeline)

    status = cli.run_once(config_path="config.toml", dry_run=True, verbose=False)

    assert status == 1
    assert calls == [
        ("init", "default"),
        ("run", "default"),
        ("close", "default"),
        ("init", "llm-data-synthesis"),
        ("run", "llm-data-synthesis"),
        ("close", "llm-data-synthesis"),
    ]
