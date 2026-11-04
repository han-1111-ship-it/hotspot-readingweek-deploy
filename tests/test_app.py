from pathlib import Path

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


def test_live_mode_reports_unavailable_data_without_exposing_cli_reason():
    app = AppTest.from_file(APP_PATH).run()

    app.radio[0].set_value("知乎 CLI 实时数据").run()

    assert not app.exception
    assert any("当前暂无可用的实时热点数据" in item.value for item in app.info)
    assert not any("quota exceeded" in item.value for item in app.info)
    assert not any("quota exceeded" in item.value for item in app.error)
    assert not any("人工智能的发展" in item.value for item in app.markdown)
