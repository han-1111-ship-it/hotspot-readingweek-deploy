import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).parents[1] / "app.py"


def test_demo_app_identifies_demo_data_and_renders_topics():
    app = AppTest.from_file(APP_PATH).run()

    assert not app.exception
    assert any("演示数据不代表实时知乎热榜" in item.value for item in app.caption)
    assert any(item.label == "热点总数" for item in app.metric)


def test_demo_app_searches_title_and_excerpt():
    app = AppTest.from_file(APP_PATH).run()

    app.text_input[0].input("睡眠").run()

    assert not app.exception
    assert any("健康与睡眠" in item.value for item in app.markdown)
    assert not any("人工智能的发展" in item.value for item in app.markdown)


def test_live_mode_waits_for_manual_request():
    app = AppTest.from_file(APP_PATH).run()

    app.radio[0].set_value("知乎 CLI 实时数据").run()

    assert not app.exception
    assert any("尚未获取真实热榜" in item.value for item in app.info)
    assert not any("quota exceeded" in item.value for item in app.info)
    assert not any("quota exceeded" in item.value for item in app.error)
    assert not any("人工智能的发展" in item.value for item in app.markdown)


def test_live_mode_passes_secret_and_reuses_cached_topics():
    app = AppTest.from_file(APP_PATH)
    app.secrets["HOTSPOT_OPERATOR_PASSWORD"] = "test-password"
    app.secrets["ZHIHU_ACCESS_SECRET"] = "test-secret"
    app.run()
    app.radio[0].set_value("知乎 CLI 实时数据").run()
    app.text_input(key="hotspot_password_input").input("test-password")
    next(button for button in app.button if button.label == "解锁实时数据操作").click().run()
    app.checkbox[0].check().run()

    output = json.dumps([{"title": "本地模拟热榜", "url": "https://www.zhihu.com/question/1"}])
    with patch("modules.cloud_cli.find_cli_path", return_value="zhihu-cli-test"), patch(
        "subprocess.run", return_value=subprocess.CompletedProcess([], 0, output, "")
    ) as cli:
        next(button for button in app.button if button.label == "获取一次真实热榜").click().run()
        assert not app.exception
        assert cli.call_args.args[0] == ["zhihu-cli-test", "hot", "--limit", "20"]
        assert cli.call_args.kwargs["env"]["ZHIHU_ACCESS_SECRET"] == "test-secret"
        assert any("本地模拟热榜" in item.value for item in app.markdown)
        app.text_input[0].input("本地模拟").run()
        assert any("本地模拟热榜" in item.value for item in app.markdown)
        cli.assert_called_once()
