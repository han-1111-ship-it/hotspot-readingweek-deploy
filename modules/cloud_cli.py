"""知乎 CLI 平台适配工具。

仅负责寻找或安装官方 CLI 可执行程序，不执行任何知乎数据 API 调用。
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


# 项目根目录：本模块位于 <项目根>/modules/cloud_cli.py。
# 如果移动本文件，需要同步修改 parents[1] 的层级。
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 官方 Skill 的固定版本、安装包大小及 SHA-256：来自用户本机官方 CLI 状态检查。
# 当官方版本更新时，需先核验新版本 ZIP 的 SHA-256，再修改这三个值。
SKILL_VERSION = "0.7.4"
OFFICIAL_SKILL_URL = (
    "https://developer-cdn.zhihu.com/zhihu-cli/releases/stable/skill/"
    "0.7.4/zhihu-cli-skill-0.7.4.zip"
)
OFFICIAL_SKILL_SHA256 = "623534a8185d8b7f1c978c25b2f506464d9cf07243d83e6d6a9c4e780c017734"
OFFICIAL_SKILL_SIZE = 66425

# CLI Skill 下载到服务器用户目录（不上传 GitHub，不包含 Secret）。
# Streamlit Cloud 重启时若缓存丢失，下一次管理员手动安装会重新验证下载。
CACHE_ROOT = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
OFFICIAL_SKILL_DIR = CACHE_ROOT / "hotspot-zhihu-skill" / "zhihu"

# 安装超时时间（秒）：云平台下载官方 CLI 时，网络慢可以适当增大。
SETUP_TIMEOUT_SECONDS = 180

# 本地状态检查超时时间（秒）：只检查 CLI 安装状态，不请求知乎业务 API。
STATUS_TIMEOUT_SECONDS = 35


class CliSetupError(RuntimeError):
    """CLI 安装、路径检测或平台兼容性检查失败。"""


def _skill_present() -> bool:
    """只检查安装脚本文件是否存在；不访问网络。"""
    return (OFFICIAL_SKILL_DIR / "scripts" / "setup.sh").is_file() and (
        OFFICIAL_SKILL_DIR / "scripts" / "run.sh"
    ).is_file()


def _download_verified_skill() -> None:
    """下载固定版本的官方 Skill，校验字节数及 SHA-256 后才允许执行脚本。"""
    if _skill_present():
        return
    try:
        # 只从固定 HTTPS 域名获取官方发布包，不调用任何知乎开放平台 API。
        with urllib.request.urlopen(OFFICIAL_SKILL_URL, timeout=30) as response:
            archive = response.read(OFFICIAL_SKILL_SIZE + 1)
    except (OSError, urllib.error.URLError) as exc:
        raise CliSetupError("云端下载官方 CLI Skill 失败，请检查 Cloud logs 中的网络限制。") from exc

    if len(archive) != OFFICIAL_SKILL_SIZE:
        raise CliSetupError("官方 Skill 压缩包大小与已验证版本不一致，拒绝执行。")
    if hashlib.sha256(archive).hexdigest() != OFFICIAL_SKILL_SHA256:
        raise CliSetupError("官方 Skill 压缩包 SHA-256 不匹配，拒绝执行。")

    # 对 ZIP 文件路径做安全检查，避免脚本或归档路径越出缓存目录。
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            files = [entry for entry in zf.infolist() if entry.filename.startswith("zhihu/")]
            if not files:
                raise CliSetupError("官方 Skill 压缩包缺少 zhihu 目录。")
            destination = OFFICIAL_SKILL_DIR.parent.resolve()
            for entry in files:
                filepath = (destination / entry.filename).resolve()
                if destination not in filepath.parents and filepath != destination:
                    raise CliSetupError("官方 Skill 压缩包包含不安全路径。")
            destination.mkdir(parents=True, exist_ok=True)
            zf.extractall(destination, members=files)
    except (OSError, zipfile.BadZipFile) as exc:
        raise CliSetupError("官方 Skill 解压失败。") from exc

    if not _skill_present():
        raise CliSetupError("官方 Skill 缺少运行脚本，无法继续安装。")


def _extract_last_json(stdout: str) -> dict:
    """读取官方脚本最后一行 JSON，忽略之前的普通进度提示。"""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                result = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(result, dict):
                return result
    raise CliSetupError("官方脚本未返回可识别的 JSON 状态。")


def _run_official_script(name: str, *args: str, timeout: int) -> dict:
    """只执行本项目内保存的官方脚本，不执行其他网络下载来的未知脚本。"""
    script_path = OFFICIAL_SKILL_DIR / "scripts" / name
    if not script_path.is_file():
        raise CliSetupError("官方 Skill 尚未安装；请先点击“安装官方 CLI”。")

    # 官方 Linux 发行版中由 bash 执行 setup.sh/run.sh。
    # 注意：此处不传 Access Secret，也不会执行 hot 等知乎数据请求。
    try:
        proc = subprocess.run(
            ["bash", str(script_path), *args],
            cwd=str(OFFICIAL_SKILL_DIR),
            env={key: value for key, value in os.environ.items()
                 if key not in {"ZHIHU_ACCESS_SECRET", "HOTSPOT_OPERATOR_PASSWORD"}},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CliSetupError(f"官方 CLI 脚本无法运行：{type(exc).__name__}") from exc

    try:
        result = _extract_last_json(proc.stdout)
    except CliSetupError as exc:
        # 不原样展示第三方脚本的 stderr，避免未来脚本变化导致意外输出敏感信息。
        raise CliSetupError(f"官方 CLI 脚本状态读取失败（退出码 {proc.returncode}）。") from exc

    if proc.returncode != 0 or result.get("ok") is False:
        raise CliSetupError(f"官方 CLI 脚本执行失败（退出码 {proc.returncode}）。")
    return result


def find_cli_path() -> str | None:
    """查找可用的官方 CLI 文件；本函数不进行安装和 API 请求。"""
    # Windows 本机使用你之前安装的官方 CLI，云端 Linux 则使用 Skill 状态检查。
    if sys.platform.startswith("win"):
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            executable = Path(local_app_data) / "ZhihuCLI" / "current" / "zhihu-cli.exe"
            if executable.is_file():
                return str(executable)
        return shutil.which("zhihu-cli")

    # Linux 云端：CLI 默认不进 PATH，必须读官方状态脚本返回的绝对 binary_path。
    # Skill 不在缓存中时，只报告未安装，不触发联网下载。
    if not _skill_present():
        return None
    status = _run_official_script("run.sh", "status", timeout=STATUS_TIMEOUT_SECONDS)
    if not status.get("installed", False):
        return None
    cli = status.get("cli") or {}
    if cli.get("compatible") is False:
        raise CliSetupError("已安装的 Zhihu CLI 与 Skill 版本不兼容。")
    path = cli.get("binary_path") or status.get("binary_path")
    if not isinstance(path, str) or not Path(path).is_file():
        raise CliSetupError("状态检查显示已安装，但未找到有效的 CLI 主程序路径。")
    return path


def install_official_cli() -> str:
    """手动安装官方 CLI，仅下载并校验程序，不验证密钥，不调用热榜 API。"""
    existing = find_cli_path()
    if existing:
        return existing
    if sys.platform.startswith("win"):
        raise CliSetupError("Windows 请先按官方 Skill 的 setup.ps1 安装 CLI。")

    # 安装动作仅由管理员点击按钮触发，不在启动或切换数据模式时自动发生。
    _download_verified_skill()
    result = _run_official_script("setup.sh", timeout=SETUP_TIMEOUT_SECONDS)
    path = result.get("binary_path")
    if not isinstance(path, str) or not Path(path).is_file():
        # 有些版本只在 status 中提供完整绝对路径，再次读取官方状态。
        path = find_cli_path()
    if not path:
        raise CliSetupError("官方脚本结束后仍未找到 CLI，请查看 Cloud logs。")
    return path
