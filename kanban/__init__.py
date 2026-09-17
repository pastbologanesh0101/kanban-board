"""Kanban Board Flask application (app factory)."""
import os
import sqlite3

from flask import Flask, g


def create_app(testing=False, db_path=None):
    """Application factory.

    Parameters
    ----------
    testing: bool
        If True, configures the app for testing (uses an isolated SQLite
        database, usually a temp file or in-memory DB via db_path).
    db_path: str or None
        Path to the SQLite database file. Defaults to ``instance/kanban.db``
        for normal runs, or an in-memory DB (":memory:") for tests when not
        explicitly provided.
    """
    app = Flask(__name__, instance_relative_config=True)

    if db_path is None:
        if testing:
            db_path = ":memory:"
        else:
            os.makedirs(app.instance_path, exist_ok=True)
            db_path = os.path.join(app.instance_path, "kanban.db")

    app.config.update(
        TESTING=testing,
        DATABASE=db_path,
    )

    # For in-memory DBs we must keep a single persistent connection alive
    # for the lifetime of the app, otherwise the DB disappears once the
    # request-scoped connection closes.
    if db_path == ":memory:":
        app._memory_conn = sqlite3.connect(":memory:")
        app._memory_conn.row_factory = sqlite3.Row
        app._memory_conn.execute("PRAGMA foreign_keys = ON")

    from . import db as db_module

    db_module.init_app(app)

    from . import routes

    app.register_blueprint(routes.bp)

    with app.app_context():
        db_module.init_db()

    return app
