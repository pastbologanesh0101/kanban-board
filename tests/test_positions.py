"""Unit tests for the pure position-management logic in kanban.positions.

These call the module functions directly against an app-scoped in-memory
SQLite DB — no HTTP/browser involved.
"""
import pytest

from kanban import positions


def card_ids(db, column_id):
    rows = db.execute(
        "SELECT id FROM card WHERE column_id = ? ORDER BY position ASC", (column_id,)
    ).fetchall()
    return [r["id"] for r in rows]


def card_positions(db, column_id):
    rows = db.execute(
        "SELECT id, position FROM card WHERE column_id = ? ORDER BY position ASC",
        (column_id,),
    ).fetchall()
    return [(r["id"], r["position"]) for r in rows]


def test_create_board(db):
    board_id = positions.create_board(db, "My Board")
    board = positions.get_board(db, board_id)
    assert board["name"] == "My Board"


def test_create_board_requires_name(db):
    with pytest.raises(positions.PositionError):
        positions.create_board(db, "   ")


def test_create_column(db):
    board_id = positions.create_board(db, "Board")
    col_id = positions.create_column(db, board_id, "To Do")
    col = positions.get_column(db, col_id)
    assert col["name"] == "To Do"
    assert col["position"] == 0

    col2_id = positions.create_column(db, board_id, "Done")
    col2 = positions.get_column(db, col2_id)
    assert col2["position"] == 1


def test_create_card(db):
    board_id = positions.create_board(db, "Board")
    col_id = positions.create_column(db, board_id, "To Do")
    card_id = positions.create_card(db, col_id, "Write tests", "desc")
    card = positions.get_card(db, card_id)
    assert card["title"] == "Write tests"
    assert card["position"] == 0


def test_move_card_within_same_column_reorders_siblings(db):
    board_id = positions.create_board(db, "Board")
    col_id = positions.create_column(db, board_id, "To Do")
    a = positions.create_card(db, col_id, "A")
    b = positions.create_card(db, col_id, "B")
    c = positions.create_card(db, col_id, "C")
    # Starting order: A(0) B(1) C(2)

    # Move C to position 0 -> C A B
    positions.move_card(db, c, col_id, 0)
    assert card_ids(db, col_id) == [c, a, b]
    assert card_positions(db, col_id) == [(c, 0), (a, 1), (b, 2)]


def test_move_card_to_different_column(db):
    board_id = positions.create_board(db, "Board")
    col1 = positions.create_column(db, board_id, "To Do")
    col2 = positions.create_column(db, board_id, "Done")

    a = positions.create_card(db, col1, "A")
    b = positions.create_card(db, col1, "B")
    x = positions.create_card(db, col2, "X")

    positions.move_card(db, a, col2, 0)

    # Source column loses A, B closes the gap to position 0.
    assert card_ids(db, col1) == [b]
    assert card_positions(db, col1) == [(b, 0)]

    # Destination column: A inserted at 0, X shifted to 1.
    assert card_ids(db, col2) == [a, x]
    assert card_positions(db, col2) == [(a, 0), (x, 1)]

    moved = positions.get_card(db, a)
    assert moved["column_id"] == col2


def test_move_card_to_position_zero(db):
    board_id = positions.create_board(db, "Board")
    col_id = positions.create_column(db, board_id, "To Do")
    a = positions.create_card(db, col_id, "A")
    b = positions.create_card(db, col_id, "B")
    c = positions.create_card(db, col_id, "C")

    positions.move_card(db, c, col_id, 0)
    assert card_ids(db, col_id)[0] == c


def test_move_card_to_end_of_list(db):
    board_id = positions.create_board(db, "Board")
    col_id = positions.create_column(db, board_id, "To Do")
    a = positions.create_card(db, col_id, "A")
    b = positions.create_card(db, col_id, "B")
    c = positions.create_card(db, col_id, "C")

    # Moving A to a position beyond the list should clamp to the end.
    positions.move_card(db, a, col_id, 999)
    assert card_ids(db, col_id) == [b, c, a]
    assert card_positions(db, col_id)[-1] == (a, 2)


def test_delete_card_closes_position_gap(db):
    board_id = positions.create_board(db, "Board")
    col_id = positions.create_column(db, board_id, "To Do")
    a = positions.create_card(db, col_id, "A")
    b = positions.create_card(db, col_id, "B")
    c = positions.create_card(db, col_id, "C")

    positions.delete_card(db, b)

    assert card_ids(db, col_id) == [a, c]
    assert card_positions(db, col_id) == [(a, 0), (c, 1)]


def test_delete_column_rejected_when_it_has_cards(db):
    board_id = positions.create_board(db, "Board")
    col_id = positions.create_column(db, board_id, "To Do")
    positions.create_card(db, col_id, "A")

    with pytest.raises(positions.PositionError):
        positions.delete_column(db, col_id)

    # Column should still exist.
    positions.get_column(db, col_id)


def test_delete_column_force_cascades_cards(db):
    board_id = positions.create_board(db, "Board")
    col_id = positions.create_column(db, board_id, "To Do")
    card_id = positions.create_card(db, col_id, "A")

    positions.delete_column(db, col_id, force=True)

    with pytest.raises(positions.PositionError):
        positions.get_column(db, col_id)
    with pytest.raises(positions.PositionError):
        positions.get_card(db, card_id)


def test_delete_empty_column_normalizes_positions(db):
    board_id = positions.create_board(db, "Board")
    col1 = positions.create_column(db, board_id, "A")
    col2 = positions.create_column(db, board_id, "B")
    col3 = positions.create_column(db, board_id, "C")

    positions.delete_column(db, col2)

    remaining = db.execute(
        'SELECT id, position FROM "column" WHERE board_id = ? ORDER BY position',
        (board_id,),
    ).fetchall()
    assert [(r["id"], r["position"]) for r in remaining] == [(col1, 0), (col3, 1)]


def test_reorder_columns(db):
    board_id = positions.create_board(db, "Board")
    col1 = positions.create_column(db, board_id, "A")
    col2 = positions.create_column(db, board_id, "B")
    col3 = positions.create_column(db, board_id, "C")

    positions.reorder_columns(db, board_id, [col3, col1, col2])

    rows = db.execute(
        'SELECT id, position FROM "column" WHERE board_id = ? ORDER BY position',
        (board_id,),
    ).fetchall()
    assert [(r["id"], r["position"]) for r in rows] == [(col3, 0), (col1, 1), (col2, 2)]


def test_reorder_columns_rejects_mismatched_ids(db):
    board_id = positions.create_board(db, "Board")
    col1 = positions.create_column(db, board_id, "A")
    col2 = positions.create_column(db, board_id, "B")

    with pytest.raises(positions.PositionError):
        positions.reorder_columns(db, board_id, [col1])  # missing col2

    with pytest.raises(positions.PositionError):
        positions.reorder_columns(db, board_id, [col1, col2, 9999])


def test_move_card_invalid_card_id_rejected(db):
    board_id = positions.create_board(db, "Board")
    col_id = positions.create_column(db, board_id, "To Do")
    with pytest.raises(positions.PositionError):
        positions.move_card(db, 9999, col_id, 0)


def test_move_card_invalid_column_id_rejected(db):
    board_id = positions.create_board(db, "Board")
    col_id = positions.create_column(db, board_id, "To Do")
    card_id = positions.create_card(db, col_id, "A")
    with pytest.raises(positions.PositionError):
        positions.move_card(db, card_id, 9999, 0)


def test_move_card_negative_position_rejected(db):
    board_id = positions.create_board(db, "Board")
    col_id = positions.create_column(db, board_id, "To Do")
    card_id = positions.create_card(db, col_id, "A")
    with pytest.raises(positions.PositionError):
        positions.move_card(db, card_id, col_id, -1)
