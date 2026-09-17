"""HTTP routes: a thin JSON API layer plus the single-page frontend.

All actual position-management logic lives in kanban.positions — these
view functions only parse the request, call into that module, and shape
the JSON response.
"""
from flask import Blueprint, jsonify, render_template, request

from . import positions
from .db import get_db

bp = Blueprint("kanban", __name__)


def board_to_dict(db, board_id):
    board = positions.get_board(db, board_id)
    columns = db.execute(
        'SELECT * FROM "column" WHERE board_id = ? ORDER BY position ASC',
        (board_id,),
    ).fetchall()

    columns_out = []
    for col in columns:
        cards = db.execute(
            "SELECT * FROM card WHERE column_id = ? ORDER BY position ASC",
            (col["id"],),
        ).fetchall()
        columns_out.append(
            {
                "id": col["id"],
                "board_id": col["board_id"],
                "name": col["name"],
                "position": col["position"],
                "cards": [dict(c) for c in cards],
            }
        )

    return {"id": board["id"], "name": board["name"], "columns": columns_out}


@bp.errorhandler(positions.PositionError)
def handle_position_error(err):
    return jsonify({"error": str(err)}), 400


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------


@bp.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Boards
# ---------------------------------------------------------------------------


@bp.route("/api/boards", methods=["POST"])
def create_board():
    db = get_db()
    data = request.get_json(silent=True) or {}
    board_id = positions.create_board(db, data.get("name", ""))
    return jsonify(board_to_dict(db, board_id)), 201


@bp.route("/api/boards", methods=["GET"])
def list_boards():
    db = get_db()
    rows = db.execute("SELECT id FROM board ORDER BY id ASC").fetchall()
    return jsonify([board_to_dict(db, row["id"]) for row in rows])


@bp.route("/api/boards/<int:board_id>", methods=["GET"])
def get_board(board_id):
    db = get_db()
    return jsonify(board_to_dict(db, board_id))


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------


@bp.route("/api/columns", methods=["POST"])
def create_column():
    db = get_db()
    data = request.get_json(silent=True) or {}
    column_id = positions.create_column(
        db,
        board_id=data.get("board_id"),
        name=data.get("name", ""),
        position=data.get("position"),
    )
    col = positions.get_column(db, column_id)
    return jsonify(dict(col)), 201


@bp.route("/api/columns/<int:column_id>", methods=["DELETE"])
def delete_column(column_id):
    db = get_db()
    force = request.args.get("force", "false").lower() == "true"
    positions.delete_column(db, column_id, force=force)
    return jsonify({"deleted": column_id})


@bp.route("/api/columns/reorder", methods=["POST"])
def reorder_columns():
    db = get_db()
    data = request.get_json(silent=True) or {}
    board_id = data.get("board_id")
    ordered_ids = data.get("ordered_column_ids", [])
    positions.reorder_columns(db, board_id, ordered_ids)
    return jsonify(board_to_dict(db, board_id))


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------


@bp.route("/api/cards", methods=["POST"])
def create_card():
    db = get_db()
    data = request.get_json(silent=True) or {}
    card_id = positions.create_card(
        db,
        column_id=data.get("column_id"),
        title=data.get("title", ""),
        description=data.get("description", ""),
        position=data.get("position"),
    )
    card = positions.get_card(db, card_id)
    return jsonify(dict(card)), 201


@bp.route("/api/cards/<int:card_id>", methods=["DELETE"])
def delete_card(card_id):
    db = get_db()
    positions.delete_card(db, card_id)
    return jsonify({"deleted": card_id})


@bp.route("/api/cards/<int:card_id>/move", methods=["POST"])
def move_card(card_id):
    db = get_db()
    data = request.get_json(silent=True) or {}
    dest_column_id = data.get("column_id")
    dest_position = data.get("position")
    if dest_column_id is None:
        raise positions.PositionError("column_id is required")
    positions.move_card(db, card_id, dest_column_id, dest_position)
    card = positions.get_card(db, card_id)
    return jsonify(dict(card))
