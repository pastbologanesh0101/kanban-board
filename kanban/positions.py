"""Core position-management logic for boards, columns and cards.

This module contains plain Python functions that operate on a sqlite3
connection. They hold *all* of the reordering logic so it can be unit
tested directly, without going through Flask or HTTP at all.

Positions are always a clean, contiguous, zero-indexed sequence
(0, 1, 2, ...) within their parent scope:

  * Column positions are contiguous within a board.
  * Card positions are contiguous within a column.

Every mutation (insert, move, delete, reorder) re-normalizes the affected
scopes so there are never gaps or duplicate positions.
"""


class PositionError(ValueError):
    """Raised for invalid reordering/move operations (bad ids, bad positions)."""


# ---------------------------------------------------------------------------
# Boards
# ---------------------------------------------------------------------------


def create_board(db, name):
    if not name or not name.strip():
        raise PositionError("Board name is required")
    cur = db.execute("INSERT INTO board (name) VALUES (?)", (name.strip(),))
    db.commit()
    return cur.lastrowid


def get_board(db, board_id):
    row = db.execute("SELECT * FROM board WHERE id = ?", (board_id,)).fetchone()
    if row is None:
        raise PositionError(f"Board {board_id} does not exist")
    return row


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------


def create_column(db, board_id, name, position=None):
    get_board(db, board_id)
    if not name or not name.strip():
        raise PositionError("Column name is required")

    count = db.execute(
        "SELECT COUNT(*) AS c FROM \"column\" WHERE board_id = ?", (board_id,)
    ).fetchone()["c"]

    if position is None or position > count:
        position = count
    if position < 0:
        position = 0

    # make room for the new column
    db.execute(
        'UPDATE "column" SET position = position + 1 '
        "WHERE board_id = ? AND position >= ?",
        (board_id, position),
    )
    cur = db.execute(
        'INSERT INTO "column" (board_id, name, position) VALUES (?, ?, ?)',
        (board_id, name.strip(), position),
    )
    db.commit()
    return cur.lastrowid


def get_column(db, column_id):
    row = db.execute('SELECT * FROM "column" WHERE id = ?', (column_id,)).fetchone()
    if row is None:
        raise PositionError(f"Column {column_id} does not exist")
    return row


def _normalize_column_positions(db, board_id):
    rows = db.execute(
        'SELECT id FROM "column" WHERE board_id = ? ORDER BY position ASC, id ASC',
        (board_id,),
    ).fetchall()
    for index, row in enumerate(rows):
        db.execute('UPDATE "column" SET position = ? WHERE id = ?', (index, row["id"]))


def delete_column(db, column_id, force=False):
    """Delete a column.

    By default, deletion is rejected if the column still has cards in it
    (to avoid silently losing data). Pass ``force=True`` to cascade-delete
    the column's cards along with it.
    """
    column = get_column(db, column_id)

    card_count = db.execute(
        "SELECT COUNT(*) AS c FROM card WHERE column_id = ?", (column_id,)
    ).fetchone()["c"]

    if card_count > 0 and not force:
        raise PositionError(
            f"Column {column_id} still has {card_count} card(s); "
            "delete or move them first, or pass force=True to cascade delete"
        )

    if force:
        db.execute("DELETE FROM card WHERE column_id = ?", (column_id,))

    db.execute('DELETE FROM "column" WHERE id = ?', (column_id,))
    _normalize_column_positions(db, column["board_id"])
    db.commit()


def reorder_columns(db, board_id, ordered_column_ids):
    """Reorder all columns of a board to match ``ordered_column_ids``.

    ``ordered_column_ids`` must contain exactly the ids of every column
    currently belonging to the board, each exactly once.
    """
    get_board(db, board_id)
    rows = db.execute(
        'SELECT id FROM "column" WHERE board_id = ?', (board_id,)
    ).fetchall()
    existing_ids = {row["id"] for row in rows}

    if set(ordered_column_ids) != existing_ids or len(ordered_column_ids) != len(
        existing_ids
    ):
        raise PositionError(
            "ordered_column_ids must contain exactly the board's current columns"
        )

    for index, column_id in enumerate(ordered_column_ids):
        db.execute('UPDATE "column" SET position = ? WHERE id = ?', (index, column_id))
    db.commit()


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------


def create_card(db, column_id, title, description="", position=None):
    get_column(db, column_id)
    if not title or not title.strip():
        raise PositionError("Card title is required")

    count = db.execute(
        "SELECT COUNT(*) AS c FROM card WHERE column_id = ?", (column_id,)
    ).fetchone()["c"]

    if position is None or position > count:
        position = count
    if position < 0:
        position = 0

    db.execute(
        "UPDATE card SET position = position + 1 WHERE column_id = ? AND position >= ?",
        (column_id, position),
    )
    cur = db.execute(
        "INSERT INTO card (column_id, title, description, position) "
        "VALUES (?, ?, ?, ?)",
        (column_id, title.strip(), description or "", position),
    )
    db.commit()
    return cur.lastrowid


def get_card(db, card_id):
    row = db.execute("SELECT * FROM card WHERE id = ?", (card_id,)).fetchone()
    if row is None:
        raise PositionError(f"Card {card_id} does not exist")
    return row


def _normalize_card_positions(db, column_id):
    rows = db.execute(
        "SELECT id FROM card WHERE column_id = ? ORDER BY position ASC, id ASC",
        (column_id,),
    ).fetchall()
    for index, row in enumerate(rows):
        db.execute("UPDATE card SET position = ? WHERE id = ?", (index, row["id"]))


def delete_card(db, card_id):
    card = get_card(db, card_id)
    db.execute("DELETE FROM card WHERE id = ?", (card_id,))
    _normalize_card_positions(db, card["column_id"])
    db.commit()


def move_card(db, card_id, dest_column_id, dest_position):
    """Move a card to ``dest_position`` within ``dest_column_id``.

    Handles both same-column reordering and moving to a different column.
    The source column's positions are closed up (gap removed) and the
    destination column's positions are shifted to make room, so both
    columns end up with a clean, contiguous 0-indexed sequence.
    """
    card = get_card(db, card_id)
    get_column(db, dest_column_id)

    if dest_position is None or dest_position < 0:
        raise PositionError("dest_position must be a non-negative integer")

    src_column_id = card["column_id"]

    if src_column_id == dest_column_id:
        # Same-column reorder.
        siblings = db.execute(
            "SELECT id FROM card WHERE column_id = ? ORDER BY position ASC, id ASC",
            (src_column_id,),
        ).fetchall()
        ids = [row["id"] for row in siblings]
        ids.remove(card_id)

        dest_position = max(0, min(dest_position, len(ids)))
        ids.insert(dest_position, card_id)

        for index, cid in enumerate(ids):
            db.execute("UPDATE card SET position = ? WHERE id = ?", (index, cid))
        db.commit()
        return

    # Cross-column move: remove from source, close the gap, then insert
    # into destination, shifting destination cards down.
    db.execute("DELETE FROM card WHERE id = ?", (card_id,))
    _normalize_card_positions(db, src_column_id)

    dest_count = db.execute(
        "SELECT COUNT(*) AS c FROM card WHERE column_id = ?", (dest_column_id,)
    ).fetchone()["c"]
    dest_position = max(0, min(dest_position, dest_count))

    db.execute(
        "UPDATE card SET position = position + 1 WHERE column_id = ? AND position >= ?",
        (dest_column_id, dest_position),
    )
    db.execute(
        "INSERT INTO card (id, column_id, title, description, position, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            card_id,
            dest_column_id,
            card["title"],
            card["description"],
            dest_position,
            card["created_at"],
        ),
    )
    db.commit()
