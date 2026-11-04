import streamlit as st

from modules.classifier import CATEGORY_NAMES, classify_topic
from modules.data_provider import CliDataProvider, DataProviderError, get_topics


@st.cache_data(ttl=300, show_spinner=False)
def get_live_topics():
    return CliDataProvider().get_topics()


st.set_page_config(page_title="HotSpot 热点观察", page_icon="🔥", layout="wide")
st.title("🔥 HotSpot · 知乎热点观察")
st.caption("发现热点、整理议题、快速浏览相关讨论")

with st.sidebar:
    st.header("筛选与设置")
    data_mode = st.radio("数据模式", ["演示数据", "知乎 CLI 实时数据"])
    category_filter = st.selectbox("热点分类", ["全部"] + CATEGORY_NAMES)
    keyword = st.text_input("搜索热点关键词", placeholder="例如：人工智能、大学生")
    refresh = st.button("刷新热点数据")
    st.divider()
    if data_mode == "演示数据":
        st.caption("演示数据不代表实时知乎热榜。")
    else:
        st.caption("实时数据需要已安装 Zhihu CLI 并配置 Access Secret。")

if data_mode == "演示数据":
    topics, source_label, updated_at = get_topics()
else:
    if refresh:
        get_live_topics.clear()
    try:
        topics, source_label, updated_at = get_live_topics()
        st.session_state["live_snapshot"] = (topics, source_label, updated_at)
    except DataProviderError:
        st.info("当前暂无可用的实时热点数据，请稍后再试。")
        topics, source_label, updated_at = st.session_state.get(
            "live_snapshot", ([], "知乎 CLI 实时热榜", None)
        )
        if topics:
            st.warning("当前显示上一次成功获取的热点数据。")

for topic in topics:
    topic["category"] = classify_topic(topic.get("title", ""), topic.get("excerpt", ""))

filtered = [
    t for t in topics
    if (category_filter == "全部" or t["category"] == category_filter)
    and (not keyword.strip() or keyword.strip().lower() in (t.get("title", "") + t.get("excerpt", "")).lower())
]
counts = {c: sum(1 for t in topics if t["category"] == c) for c in CATEGORY_NAMES}

a, b, c = st.columns(3)
a.metric("热点总数", len(topics))
b.metric("当前显示", len(filtered))
c.metric("热点分类", len([v for v in counts.values() if v]))
if updated_at:
    updated_text = updated_at
elif data_mode == "演示数据":
    updated_text = "未采集（演示数据）"
else:
    updated_text = "实时数据未成功采集"
st.caption(f"数据来源：{source_label} · 更新时间：{updated_text}")

st.subheader("分类概览")
cols = st.columns(len(CATEGORY_NAMES))
for col, name in zip(cols, CATEGORY_NAMES):
    col.metric(name, counts[name])

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
