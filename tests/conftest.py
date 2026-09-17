import pytest

from kanban import create_app
from kanban.db import get_db


@pytest.fixture
def app():
    app = create_app(testing=True)
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    with app.app_context():
        yield get_db()
