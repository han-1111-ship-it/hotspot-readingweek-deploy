import json
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import urlparse

from modules.demo_data import DEMO_TOPICS


class DataProviderError(RuntimeError):
    """Raised when a hotspot source cannot provide valid data."""


class CliDataProvider:
    def __init__(self, executable="zhihu-cli", limit=20, timeout=30):
        self.executable = executable
        self.limit = limit
        self.timeout = timeout

    def get_topics(self):
        command = [self.executable, "hot", "--limit", str(self.limit)]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise DataProviderError("Zhihu CLI 未安装，请先安装官方 CLI。") from exc
        except subprocess.TimeoutExpired as exc:
            raise DataProviderError("Zhihu CLI 获取热点超时，请稍后重试。") from exc
        except OSError as exc:
            raise DataProviderError("无法启动 Zhihu CLI。") from exc

        payload = self._parse_response(result.stdout, result.returncode)
        topics = self._normalize_topics(payload)
        return topics, "知乎 CLI 实时热榜", datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_response(stdout, returncode):
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise DataProviderError("Zhihu CLI 返回了无法识别的数据。") from exc

        if isinstance(payload, dict) and payload.get("ok") is False:
            error = payload.get("error") or {}
            code = error.get("code")
            if code in {"AUTH_REQUIRED", "AUTH_INVALID", "KEYCHAIN_UNAVAILABLE"}:
                raise DataProviderError("Zhihu CLI 未配置有效的 Access Secret。")
            raise DataProviderError("Zhihu CLI 获取热点失败。")
        if isinstance(payload, dict) and payload.get("Code") == 30002:
            raise DataProviderError("知乎 CLI 调用额度已用尽，请稍后再试或查看开放平台额度。")
        if returncode != 0:
            raise DataProviderError("Zhihu CLI 获取热点失败。")
        return payload

    @staticmethod
    def _normalize_topics(payload):
        items = payload.get("Data", payload.get("data")) if isinstance(payload, dict) else payload
        if isinstance(items, dict):
            items = items.get("Items", items.get("items", items.get("List", items.get("list"))))
        if not isinstance(items, list):
            raise DataProviderError("Zhihu CLI 返回的数据格式不受支持。")

        topics = []
        for rank, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise DataProviderError("Zhihu CLI 返回了无效的热点条目。")
            title = item.get("Title", item.get("title"))
            url = item.get("Url", item.get("url"))
            if not isinstance(title, str) or not title.strip():
                raise DataProviderError("Zhihu CLI 返回的热点缺少标题。")
            if not _is_zhihu_url(url):
                raise DataProviderError("Zhihu CLI 返回了不可信的热点链接。")
            excerpt = item.get("Summary", item.get("summary", item.get("Excerpt", item.get("excerpt", ""))))
            official_rank = item.get("Rank", item.get("rank", rank))
            if not isinstance(official_rank, int) or official_rank < 1:
                raise DataProviderError("Zhihu CLI 返回了无效的热点排名。")
            topics.append({
                "rank": official_rank,
                "title": title.strip(),
                "excerpt": excerpt.strip() if isinstance(excerpt, str) else "",
                "url": url,
            })
        return topics


def _is_zhihu_url(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
        hostname = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and not parsed.username
        and not parsed.password
        and (hostname == "zhihu.com" or hostname.endswith(".zhihu.com"))
    )


def get_topics():
    # 先使用演示数据完成界面和分类逻辑。
    # 接入 Zhihu CLI 前，必须先用官方 CLI 帮助确认真实命令和返回格式。
    return deepcopy(DEMO_TOPICS), "本地演示数据（待接入 Zhihu CLI）", None
