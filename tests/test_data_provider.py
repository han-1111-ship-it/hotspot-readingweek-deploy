import json
import subprocess

import pytest

from modules.data_provider import CliDataProvider, DataProviderError, get_topics


def test_demo_topics_are_isolated_between_calls():
    first_topics, _, _ = get_topics()
    first_topics[0]["title"] = "已修改"

    second_topics, _, _ = get_topics()

    assert second_topics[0]["title"] != "已修改"


def test_demo_topics_do_not_claim_a_collection_time():
    _, source_label, updated_at = get_topics()

    assert "演示" in source_label
    assert updated_at is None


def test_cli_provider_maps_official_hot_response(monkeypatch):
    payload = {
        "data": [
            {"Rank": 1, "Title": "人工智能热点", "Excerpt": "大模型趋势", "Url": "https://www.zhihu.com/question/1"}
        ]
    }

    def run(*args, **kwargs):
        assert args[0] == ["zhihu-cli", "hot", "--limit", "20"]
        return subprocess.CompletedProcess(args[0], 0, json.dumps(payload), "")

    monkeypatch.setattr(subprocess, "run", run)
    topics, source_label, updated_at = CliDataProvider().get_topics()

    assert topics == [
        {
            "rank": 1,
            "title": "人工智能热点",
            "excerpt": "大模型趋势",
            "url": "https://www.zhihu.com/question/1",
        }
    ]
    assert source_label == "知乎 CLI 实时热榜"
    assert updated_at is not None


def test_cli_provider_reports_quota_exceeded(monkeypatch):
    payload = {"Code": 30002, "Message": "quota exceeded", "Data": None}

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 4, json.dumps(payload), ""),
    )

    with pytest.raises(DataProviderError, match="调用额度已用尽"):
        CliDataProvider().get_topics()


def test_cli_provider_reports_authentication_failure(monkeypatch):
    payload = {"ok": False, "error": {"code": "AUTH_REQUIRED"}}

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 3, json.dumps(payload), ""),
    )

    with pytest.raises(DataProviderError, match="Access Secret"):
        CliDataProvider().get_topics()


def test_cli_provider_reports_missing_command(monkeypatch):
    def run(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(DataProviderError, match="未安装"):
        CliDataProvider().get_topics()


def test_cli_provider_preserves_official_rank(monkeypatch):
    payload = {
        "data": [
            {
                "Rank": 7,
                "Title": "热点标题",
                "Url": "https://www.zhihu.com/question/7",
            }
        ]
    }

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, json.dumps(payload), ""),
    )

    topics, _, _ = CliDataProvider().get_topics()

    assert topics[0]["rank"] == 7


def test_cli_provider_rejects_malformed_url(monkeypatch):
    payload = {
        "data": [
            {
                "Title": "热点标题",
                "Url": "https://[invalid",
            }
        ]
    }

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, json.dumps(payload), ""),
    )

    with pytest.raises(DataProviderError, match="不可信"):
        CliDataProvider().get_topics()


def test_cli_provider_rejects_url_with_userinfo(monkeypatch):
    payload = {
        "data": [
            {
                "Title": "热点标题",
                "Url": "https://user:password@www.zhihu.com/question/7",
            }
        ]
    }

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, json.dumps(payload), ""),
    )

    with pytest.raises(DataProviderError, match="不可信"):
        CliDataProvider().get_topics()


def test_cli_provider_reports_timeout(monkeypatch):
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 30)

    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(DataProviderError, match="超时"):
        CliDataProvider().get_topics()
