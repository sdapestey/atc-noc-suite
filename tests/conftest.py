import pytest

from web import create_app


def assert_csv_attachment(disposition: str, filename: str) -> None:
    """Acepta filename con o sin comillas (RFC 6266 / Flask)."""
    assert disposition.startswith("attachment;")
    assert filename in disposition
    assert f'filename="{filename}"' in disposition or f"filename={filename}" in disposition


@pytest.fixture
def app():
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()
