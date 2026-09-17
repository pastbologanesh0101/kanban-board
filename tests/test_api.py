"""Integration tests hitting the Flask JSON API via the test client."""
import json


def post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


def test_create_board_endpoint(client):
    resp = post(client, "/api/boards", {"name": "Sprint 1"})
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["name"] == "Sprint 1"
    assert data["columns"] == []


def test_create_column_and_card_endpoints(client):
    board = post(client, "/api/boards", {"name": "Board"}).get_json()
    col = post(client, "/api/columns", {"board_id": board["id"], "name": "To Do"}).get_json()
    assert col["name"] == "To Do"

    card = post(
        client,
        "/api/cards",
        {"column_id": col["id"], "title": "Task 1", "description": "desc"},
    ).get_json()
    assert card["title"] == "Task 1"
    assert card["position"] == 0


def test_move_card_endpoint_cross_column(client):
    board = post(client, "/api/boards", {"name": "Board"}).get_json()
    col1 = post(client, "/api/columns", {"board_id": board["id"], "name": "To Do"}).get_json()
    col2 = post(client, "/api/columns", {"board_id": board["id"], "name": "Done"}).get_json()

    card = post(client, "/api/cards", {"column_id": col1["id"], "title": "A"}).get_json()

    move_resp = post(
        client, f"/api/cards/{card['id']}/move", {"column_id": col2["id"], "position": 0}
    )
    assert move_resp.status_code == 200
    moved = move_resp.get_json()
    assert moved["column_id"] == col2["id"]

    board_state = client.get(f"/api/boards/{board['id']}").get_json()
    to_do = next(c for c in board_state["columns"] if c["id"] == col1["id"])
    done = next(c for c in board_state["columns"] if c["id"] == col2["id"])
    assert to_do["cards"] == []
    assert [c["id"] for c in done["cards"]] == [card["id"]]


def test_delete_card_endpoint(client):
    board = post(client, "/api/boards", {"name": "Board"}).get_json()
    col = post(client, "/api/columns", {"board_id": board["id"], "name": "To Do"}).get_json()
    card = post(client, "/api/cards", {"column_id": col["id"], "title": "A"}).get_json()

    resp = client.delete(f"/api/cards/{card['id']}")
    assert resp.status_code == 200

    board_state = client.get(f"/api/boards/{board['id']}").get_json()
    assert board_state["columns"][0]["cards"] == []


def test_reorder_columns_endpoint(client):
    board = post(client, "/api/boards", {"name": "Board"}).get_json()
    col1 = post(client, "/api/columns", {"board_id": board["id"], "name": "A"}).get_json()
    col2 = post(client, "/api/columns", {"board_id": board["id"], "name": "B"}).get_json()

    resp = post(
        client,
        "/api/columns/reorder",
        {"board_id": board["id"], "ordered_column_ids": [col2["id"], col1["id"]]},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert [c["id"] for c in data["columns"]] == [col2["id"], col1["id"]]


def test_invalid_move_returns_400_with_message(client):
    board = post(client, "/api/boards", {"name": "Board"}).get_json()
    col = post(client, "/api/columns", {"board_id": board["id"], "name": "To Do"}).get_json()

    resp = post(client, "/api/cards/99999/move", {"column_id": col["id"], "position": 0})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_delete_column_with_cards_rejected(client):
    board = post(client, "/api/boards", {"name": "Board"}).get_json()
    col = post(client, "/api/columns", {"board_id": board["id"], "name": "To Do"}).get_json()
    post(client, "/api/cards", {"column_id": col["id"], "title": "A"})

    resp = client.delete(f"/api/columns/{col['id']}")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_delete_column_force_cascades(client):
    board = post(client, "/api/boards", {"name": "Board"}).get_json()
    col = post(client, "/api/columns", {"board_id": board["id"], "name": "To Do"}).get_json()
    post(client, "/api/cards", {"column_id": col["id"], "title": "A"})

    resp = client.delete(f"/api/columns/{col['id']}?force=true")
    assert resp.status_code == 200

    board_state = client.get(f"/api/boards/{board['id']}").get_json()
    assert board_state["columns"] == []


def test_index_page_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Kanban Board" in resp.data
