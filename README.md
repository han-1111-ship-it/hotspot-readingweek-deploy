# HotSpot · 知乎热点观察与议题速览助手

## 项目简介

HotSpot 是一个知乎热点观察与议题速览助手，旨在获取知乎热点内容，并通过本地分类、搜索和筛选等功能，帮助用户更方便地浏览和整理热点信息。

当前版本支持本地演示数据和 Zhihu CLI 实时数据两种模式。实时模式需要单独安装官方 `zhihu-cli` 并配置 Access Secret；未配置时仍可离线使用演示模式。

## 核心功能

- **热点展示**：展示热点排名、标题、摘要和原文链接。
- **热点分类**：根据关键词将热点划分为科技、教育、社会、生活、其他等类别。
- **分类统计**：统计不同类别的热点数量。
- **分类筛选**：按类别筛选热点。
- **关键词搜索**：根据关键词搜索热点标题和摘要。
- **原文跳转**：支持跳转到知乎相关页面。

## 技术栈

- Python
- Streamlit
- 知乎 CLI（官方 `zhihu-cli hot --limit 20`，实时模式使用）
- GitHub
- AI Works（计划部署）

## 本地运行

### 1. 创建虚拟环境

```bash
python -m venv .venv
```

### 2. 激活虚拟环境（Windows CMD）

```bash
.venv\Scripts\activate.bat
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 启动项目

```bash
python -m streamlit run app.py
```

浏览器访问：

```text
http://localhost:8501
```

## 项目进度

- [x] 基础网页搭建
- [x] 演示数据展示
- [x] 本地热点分类
- [x] 分类统计与筛选
- [x] 关键词搜索
- [x] Zhihu CLI 适配器与实时模式
- [ ] 使用真实 Access Secret 的数据测试
- [ ] AI Works 应用部署
- [ ] 演示视频与项目海报

## 项目结构

```text
HotSpot/
├── app.py
├── modules/
├── tests/
├── docs/
├── requirements.txt
├── README.md
└── .gitignore
```

## 数据模式与实时数据配置

- **演示数据**：默认模式，完全离线，可用于界面演示；更新时间显示为“未采集”，链接会标记为“知乎首页（演示）”。
- **知乎 CLI 实时数据**：选择实时模式后，应用调用官方 `zhihu-cli hot --limit 20`，结果缓存 5 分钟；点击“刷新热点数据”可清除当前缓存。
- CLI 输出必须是 JSON，应用会校验标题、HTTPS 知乎链接和可选摘要。获取失败时不会静默切换到演示数据；如果本次会话有上一次成功结果，会保留并标记旧数据。

安装并初始化 CLI 请以官方 Skill/CLI 文档为准。Access Secret 应通过 CLI 安全配置，或由运行环境提供 `ZHIHU_ACCESS_SECRET`，不要写入源码、`.env` 或日志。官方配置入口：<https://developer.zhihu.com/profile>。

## 测试

```bash
python -m pytest -q
python -m compileall app.py modules tests
```

## 注意事项

真实热榜测试需要本机完成官方 CLI 安装并配置有效 Access Secret；AI Works 部署还需要平台运行环境和 Secret 配置权限。
## Streamlit Community Cloud 实时热榜

部署入口选个人部署仓库的 `main` 分支和根目录 `app.py`。
在应用设置的 Secrets 中配置以下根级键，使用实际值替换占位符：

```toml
ZHIHU_ACCESS_SECRET = "知乎开放平台 Access Secret"
HOTSPOT_OPERATOR_PASSWORD = "独立的管理员口令"
HOTSPOT_MAX_LIVE_REQUESTS = 1
```

在站点切换到实时数据模式，输入管理员口令解锁。先检查 CLI 安装状态，
缺少时点击安装，再勾选确认并手动获取一次热榜。采集成功后，浏览器会话
共享本次结果，筛选与搜索会使用缓存。调用次数和缓存按服务器进程计算，
应用重启后会重新计数，必要时需重新安装 CLI。

如果安装失败，先查看页面上的安装提示和云端日志。如果热榜请求失败，
查看管理员提示和退出码。若提示解析失败，可下载本次 CLI 响应做离线排查。
