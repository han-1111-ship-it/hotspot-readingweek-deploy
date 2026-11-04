"""HotSpot：支持演示数据和人工授权的一次性知乎 CLI 实时展示。"""

from __future__ import annotations

import hmac
import os
import subprocess
from datetime import datetime, timezone
from threading import Lock

import streamlit as st

from modules.classifier import CATEGORY_NAMES, classify_topic
from modules.cloud_cli import CliSetupError, find_cli_path, install_official_cli
from modules.data_provider import CliDataProvider, DataProviderError, get_topics


# Streamlit Cloud 重启会清空内存中的记录；因此这个限制仅用于防止
# 正常使用中的重复点击，不能作为跨进程、跨重启的硬性配额保证。
# 正式录屏时建议设置为 1，保留第二次额度供人工处置异常。
DEFAULT_MAX_REQUESTS_PER_PROCESS = 1


class SharedLiveState:
    """服务器进程内共享的热榜结果和手动调用记录。"""

    def __init__(self):
        # 多个浏览器会话共用服务器，互斥锁避免两个按钮同时发起请求。
        self.lock = Lock()
        self.attempts = 0
        self.snapshot = None
        self.last_error = None
        self.raw_response = None
        self.raw_exit_code = None


@st.cache_resource
def get_shared_state():
    """在同一个 Streamlit 服务器进程里复用真实数据，不设置自动过期。"""
    return SharedLiveState()


def get_secret(name: str) -> str:
    """读取云端 Secrets；没有配置时返回空字符串，不把值显示到页面上。"""
    try:
        value = st.secrets[name]
    except (KeyError, FileNotFoundError):
        return ""
    return str(value).strip()


def get_request_limit() -> int:
    """允许的本进程人工请求次数，默认严格设为一次。"""
    try:
        number = int(get_secret("HOTSPOT_MAX_LIVE_REQUESTS") or DEFAULT_MAX_REQUESTS_PER_PROCESS)
    except ValueError:
        number = DEFAULT_MAX_REQUESTS_PER_PROCESS
    return max(1, min(number, 2))


def is_operator() -> bool:
    """只有知道管理员口令的会话才可以安装 CLI 或使用真实 API。"""
    if not get_secret("HOTSPOT_OPERATOR_PASSWORD"):
        return False
    return bool(st.session_state.get("hotspot_operator_authenticated", False))


st.set_page_config(page_title="HotSpot 热点观察", page_icon="🔥", layout="wide")
st.title("🔥 HotSpot · 知乎热点观察")
st.caption("发现热点、整理议题、快速浏览相关讨论")

shared = get_shared_state()

with st.sidebar:
    st.header("筛选与设置")
    data_mode = st.radio("数据模式", ["演示数据", "知乎 CLI 实时数据"])
    category_filter = st.selectbox("热点分类", ["全部"] + CATEGORY_NAMES)
    keyword = st.text_input("搜索热点关键词", placeholder="例如：人工智能、大学生")

    if data_mode == "演示数据":
        # 演示模式与在线 API 完全隔离；按钮仅会让 Streamlit 重绘同一批模拟数据。
        st.button("刷新热点数据")
        st.divider()
        st.caption("演示数据不代表实时知乎热榜，不消耗 API 额度。")
    else:
        st.divider()
        st.caption("切换到实时模式不会自动发起请求。只有管理员手动确认才会调用。")

        if not is_operator():
            password = st.text_input("管理员口令", type="password", key="hotspot_password_input")
            if st.button("解锁实时数据操作"):
                expected = get_secret("HOTSPOT_OPERATOR_PASSWORD")
                if expected and hmac.compare_digest(password, expected):
                    st.session_state["hotspot_operator_authenticated"] = True
                    st.rerun()
                else:
                    st.error("口令错误或管理员口令尚未配置。")
        else:
            if st.button("锁定实时数据操作"):
                st.session_state["hotspot_operator_authenticated"] = False
                st.rerun()

            # 只进行 CLI 环境检查，不验证 Access Secret，不请求知乎业务接口。
            if st.button("检查 CLI 安装状态（不耗业务额度）"):
                try:
                    path = find_cli_path()
                    if path:
                        st.success("官方 Zhihu CLI 已安装。")
                    else:
                        st.warning("云端还没有安装官方 Zhihu CLI。")
                except CliSetupError as exc:
                    st.error(str(exc))

            if st.button("安装官方 CLI（不调用热榜 API）"):
                with st.spinner("正在安装并校验官方 CLI ..."):
                    try:
                        install_official_cli()
                        st.success("CLI 已安装。此操作没有请求实时热榜。")
                    except CliSetupError as exc:
                        st.error(str(exc))

            # 只有明确勾选确认框并点击按钮才会发生一次真实数据请求。
            with shared.lock:
                used = shared.attempts
            limit = get_request_limit()
            st.caption(f"本次服务器运行期间已发起 {used}/{limit} 次实时请求。")
            consent = st.checkbox(
                "我确认现在才调用真实热榜，可能消耗知乎 API 额度",
                value=False,
                key="hotspot_live_request_consent",
            )
            if st.button("获取一次真实热榜", disabled=(not consent or used >= limit)):
                secret = get_secret("ZHIHU_ACCESS_SECRET")
                if not secret:
                    st.error("尚未在 Streamlit Secrets 配置 ZHIHU_ACCESS_SECRET。")
                else:
                    try:
                        executable = find_cli_path()
                        if not executable:
                            raise CliSetupError("请先点击“安装官方 CLI”，然后再获取热榜。")
                    except CliSetupError as exc:
                        st.error(str(exc))
                    else:
                        with shared.lock:
                            if shared.attempts >= limit:
                                st.warning("本次运行的人工请求上限已达到。")
                            else:
                                # 在调用前计数，避免接口失败时自动重试而意外耗额。
                                shared.attempts += 1
                                # 自行获取一次 CLI 原始输出，再使用原有解析方法处理。
                                # 即使解析失败，也允许管理员下载本次响应进行离线排查，
                                # 防止为了修复字段差异而反复消耗珍贵的接口额度。
                                shared.raw_response = None
                                shared.raw_exit_code = None
                                try:
                                    provider = CliDataProvider(executable=executable)
                                    result = subprocess.run(
                                        [provider.executable, "hot", "--limit", str(provider.limit)],
                                        capture_output=True,
                                        text=True,
                                        encoding="utf-8",
                                        errors="replace",
                                        timeout=provider.timeout,
                                        env={**os.environ, "ZHIHU_ACCESS_SECRET": secret},
                                        check=False,
                                    )
                                    shared.raw_response = result.stdout.replace(secret, "[REDACTED]")
                                    shared.raw_exit_code = result.returncode
                                    payload = provider._parse_response(result.stdout, result.returncode)
                                    topics_live = provider._normalize_topics(payload)
                                    shared.snapshot = (
                                        topics_live,
                                        "知乎 CLI 实时热榜",
                                        datetime.now(timezone.utc).isoformat(),
                                    )
                                    shared.last_error = None
                                    st.success("真实热榜获取成功！结果和原始响应已保存在当前服务器进程内。")
                                except subprocess.TimeoutExpired:
                                    shared.last_error = "CLI 请求超时"
                                    st.error("本次请求超时，系统不会自动重试。")
                                except OSError:
                                    shared.last_error = "CLI 进程启动失败"
                                    st.error("CLI 进程启动失败，系统不会自动重试。")
                                except DataProviderError as exc:
                                    shared.last_error = str(exc)
                                    st.error(f"已请求一次，但解析/接口返回异常：{exc}。不会自动重试。")

            # 原始返回数据只允许管理员下载，避免公开展示诊断内容。
            # 如果 CLI 实际数据结构与原解析器不同，可在本地修复而不再次请求。
            with shared.lock:
                raw_response = shared.raw_response
                raw_exit_code = shared.raw_exit_code
            if raw_response is not None:
                st.download_button(
                    "保存本次 CLI 原始响应（仅管理员）",
                    data=raw_response.encode("utf-8"),
                    file_name="zhihu_hot_raw_response.json",
                    mime="application/json",
                    help="保存后请勿公开原始文件；分享排查信息前先检查是否包含敏感内容。",
                )
                st.caption(f"上一次 CLI 退出码：{raw_exit_code}")

if data_mode == "演示数据":
    topics, source_label, updated_at = get_topics()
else:
    with shared.lock:
        latest = shared.snapshot
        error = shared.last_error
    if latest is None:
        topics, source_label, updated_at = [], "知乎 CLI 实时热榜", None
        st.info("尚未获取真实热榜。管理员可在侧边栏手动发起一次请求。")
        if error:
            st.warning("上一次人工请求未成功，请查看管理员操作信息。")
    else:
        topics, source_label, updated_at = latest
        st.success("当前显示本次已获取并缓存的真实知乎热榜；筛选和搜索不会重复请求 API。")

# 原有关键词分类、筛选、统计和热点卡片保持不变。
for topic in topics:
    topic["category"] = classify_topic(topic.get("title", ""), topic.get("excerpt", ""))

filtered = [
    topic for topic in topics
    if (category_filter == "全部" or topic["category"] == category_filter)
    and (
        not keyword.strip()
        or keyword.strip().lower() in (
            topic.get("title", "") + topic.get("excerpt", "")
        ).lower()
    )
]
counts = {category: sum(1 for topic in topics if topic["category"] == category)
          for category in CATEGORY_NAMES}

column_total, column_filtered, column_categories = st.columns(3)
column_total.metric("热点总数", len(topics))
column_filtered.metric("当前显示", len(filtered))
column_categories.metric("热点分类", len([value for value in counts.values() if value]))

if updated_at:
    updated_text = updated_at
elif data_mode == "演示数据":
    updated_text = "未采集（演示数据）"
else:
    updated_text = "尚未执行实时采集"
st.caption(f"数据来源：{source_label} · 更新时间：{updated_text}")

st.subheader("分类概览")
columns = st.columns(len(CATEGORY_NAMES))
for column, name in zip(columns, CATEGORY_NAMES):
    column.metric(name, counts[name])

st.subheader("热点列表")
if not filtered:
    st.info("没有找到符合条件的热点，请更换关键词或分类。")
for item in filtered:
    with st.container(border=True):
        st.write(f"{item.get('rank', '-')}. {item.get('title', '未命名话题')}")
        st.caption(f"分类：{item['category']}")
        if item.get("excerpt"):
            st.write(item["excerpt"])
        if item.get("url"):
            link_label = "查看知乎原文" if data_mode != "演示数据" else "查看知乎首页（演示）"
            st.link_button(link_label, item["url"])

st.divider()
st.caption("热点分类采用本地关键词规则，不调用额外大模型 API。")
