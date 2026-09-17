# Kanban Board

A small, self-contained Kanban-style project board built with **Flask** and
**SQLite**. It has a JSON API for boards, columns and cards, and a minimal
single-page frontend with drag-and-drop (using the native HTML5 Drag and
Drop API — no JS framework).

The interesting part of a Kanban board is keeping card/column *positions*
consistent as things move around. That logic is isolated in a plain Python
module (`kanban/positions.py`) with no Flask/HTTP dependency, so it's fully
unit-testable.

## Features

- Boards, columns ("To Do" / "In Progress" / "Done", or whatever you name
  them) and cards.
- Create boards/columns/cards.
- Drag a card within a column to reorder it, or drag it to another column.
- Drag a column header to reorder columns.
- Delete cards. Delete columns (rejected if the column still has cards,
  unless you pass `force=true` — see below).
- All positions are kept as a clean, contiguous, zero-indexed sequence
  within their parent (columns are ordered within a board, cards within a
  column) — no gaps, no duplicates, ever.

## Running it

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Then open <http://127.0.0.1:5000/>. A default board with three columns is
created automatically the first time you load the page if none exist yet.

The SQLite database file is created at `instance/kanban.db` on first run
(the `instance/` directory is git-ignored).

## Running the tests

```bash
pip install -r requirements.txt pytest
pytest -v
```

Tests use `create_app(testing=True)`, which points the app at an in-memory
SQLite database, so they don't touch `instance/kanban.db` and run fast with
no setup.

## How the position-reordering logic works

Every column belongs to a board and has a `position` (0, 1, 2, ...) among
that board's columns. Every card belongs to a column and has a `position`
among that column's cards. `kanban/positions.py` guarantees these are
always a clean contiguous sequence:

- **Insert** (`create_column` / `create_card`): existing items at or after
  the target position are shifted up by one (`position = position + 1`)
  before the new row is inserted at that position.
- **Move within the same column** (`move_card` with
  `dest_column_id == source column`): the column's card ids are read out in
  position order, the moved card is removed from that in-memory list and
  re-inserted at the target index, then positions `0..n-1` are rewritten
  for the whole list. This is what makes moving to position `0` or past the
  end of the list ("end-of-list", clamped to `len(list)`) both work
  correctly — the target position is clamped into `[0, len(list)]`.
- **Move across columns**: the card is deleted from the source column and
  the source column's remaining cards are re-normalized to `0..n-1` (this
  closes the gap left behind). Then the destination column's cards at or
  after the target position are shifted up by one, and the card is
  re-inserted into the destination column at the (clamped) target
  position. The card keeps its id, title, description and `created_at`.
- **Delete a card**: the row is deleted and the rest of its column is
  re-normalized to `0..n-1`, closing the gap.
- **Delete a column**: rejected by default if the column still has cards
  (`PositionError`, surfaced as HTTP 400) — this is a deliberate choice to
  avoid silently losing cards. Pass `force=True` (or `?force=true` on the
  `DELETE /api/columns/<id>` endpoint) to cascade-delete the column's cards
  along with it. Either way, the board's remaining columns are
  re-normalized to `0..n-1` afterwards. This is tested in
  `tests/test_positions.py::test_delete_column_rejected_when_it_has_cards`
  and `::test_delete_column_force_cascades_cards`.
- **Reorder columns**: `reorder_columns(db, board_id, ordered_column_ids)`
  takes the full desired order of *all* of a board's column ids and
  rewrites their positions to match that order. It's rejected if the id
  list doesn't exactly match the board's current columns (wrong length,
  missing id, or an id from another board).
- **Invalid moves**: moving a card that doesn't exist, or moving into a
  column that doesn't exist, raises `PositionError`. The Flask layer turns
  any `PositionError` into an `HTTP 400` with a JSON `{"error": "..."}`
  body via an `errorhandler` on the blueprint.

All of this is exercised directly (no HTTP, no browser) in
`tests/test_positions.py`, and again through the HTTP API in
`tests/test_api.py`.

## API

All endpoints accept/return JSON. Errors come back as
`{"error": "message"}` with HTTP 400.

### Create a board

```bash
curl -X POST http://localhost:5000/api/boards \
  -H 'Content-Type: application/json' \
  -d '{"name": "Sprint 1"}'
```

### Create a column

```bash
curl -X POST http://localhost:5000/api/columns \
  -H 'Content-Type: application/json' \
  -d '{"board_id": 1, "name": "To Do"}'
```

Optional `"position"` to insert at a specific index (defaults to the end).

### Create a card

```bash
curl -X POST http://localhost:5000/api/cards \
  -H 'Content-Type: application/json' \
  -d '{"column_id": 1, "title": "Write README", "description": "..."}'
```

### Move a card (reorder within a column, or move to another column)

```bash
curl -X POST http://localhost:5000/api/cards/5/move \
  -H 'Content-Type: application/json' \
  -d '{"column_id": 2, "position": 0}'
```

### Reorder columns

```bash
curl -X POST http://localhost:5000/api/columns/reorder \
  -H 'Content-Type: application/json' \
  -d '{"board_id": 1, "ordered_column_ids": [3, 1, 2]}'
```

### Delete a card

```bash
curl -X DELETE http://localhost:5000/api/cards/5
```

### Delete a column

```bash
curl -X DELETE http://localhost:5000/api/columns/2          # 400 if it has cards
curl -X DELETE "http://localhost:5000/api/columns/2?force=true"  # cascades
```

### Get a board (with its columns and cards, in order)

```bash
curl http://localhost:5000/api/boards/1
```

## Project layout

```
kanban/
  __init__.py     # create_app() application factory
  db.py           # SQLite connection handling + schema
  positions.py    # plain-Python position-management logic (the core)
  routes.py       # Flask blueprint: thin JSON API + index page
  templates/
    index.html
  static/
    app.js        # drag-and-drop frontend, calls the JSON API
    style.css
tests/
  test_positions.py   # unit tests against kanban/positions.py directly
  test_api.py         # integration tests via Flask's test client
run.py            # entry point: python run.py
```

## License

MIT — see [LICENSE](LICENSE).
