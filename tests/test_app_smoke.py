from streamlit.testing.v1 import AppTest


def test_app_renders_without_errors():
    at = AppTest.from_file("../app.py", default_timeout=30).run()

    assert not at.exception
    assert at.title[0].value.endswith("igomgoNodes")
