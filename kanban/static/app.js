// Minimal vanilla-JS frontend. All position-reordering logic lives on the
// server (kanban/positions.py) — this file just renders state and posts
// move/create/delete requests, using the HTML5 Drag and Drop API.

const boardEl = document.getElementById("board");
const boardSelect = document.getElementById("board-select");
const newBoardBtn = document.getElementById("new-board-btn");
const newColumnBtn = document.getElementById("new-column-btn");

let boards = [];
let currentBoard = null;

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed: ${res.status}`);
  }
  return data;
}

async function loadBoards() {
  boards = await api("/api/boards");
  if (boards.length === 0) {
    const board = await api("/api/boards", {
      method: "POST",
      body: JSON.stringify({ name: "My Board" }),
    });
    boards = [board];
    await api("/api/columns", {
      method: "POST",
      body: JSON.stringify({ board_id: board.id, name: "To Do" }),
    });
    await api("/api/columns", {
      method: "POST",
      body: JSON.stringify({ board_id: board.id, name: "In Progress" }),
    });
    await api("/api/columns", {
      method: "POST",
      body: JSON.stringify({ board_id: board.id, name: "Done" }),
    });
    boards = await api("/api/boards");
  }
  renderBoardSelect();
  currentBoard = boards[0];
  await refreshBoard();
}

function renderBoardSelect() {
  boardSelect.innerHTML = "";
  for (const b of boards) {
    const opt = document.createElement("option");
    opt.value = b.id;
    opt.textContent = b.name;
    boardSelect.appendChild(opt);
  }
}

async function refreshBoard() {
  currentBoard = await api(`/api/boards/${currentBoard.id}`);
  renderBoard();
}

function renderBoard() {
  boardEl.innerHTML = "";
  for (const col of currentBoard.columns) {
    boardEl.appendChild(renderColumn(col));
  }
}

function renderColumn(col) {
  const colEl = document.createElement("div");
  colEl.className = "column";
  colEl.dataset.columnId = col.id;

  const header = document.createElement("div");
  header.className = "column-header";
  header.draggable = true;
  header.innerHTML = `<span>${escapeHtml(col.name)}</span>`;

  const actions = document.createElement("div");
  actions.className = "column-actions";
  const delBtn = document.createElement("button");
  delBtn.className = "icon-btn";
  delBtn.textContent = "✕";
  delBtn.title = "Delete column (must be empty)";
  delBtn.onclick = async () => {
    try {
      await api(`/api/columns/${col.id}`, { method: "DELETE" });
      await refreshBoard();
    } catch (e) {
      alert(e.message);
    }
  };
  actions.appendChild(delBtn);
  header.appendChild(actions);

  header.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/column-id", col.id);
  });

  colEl.addEventListener("dragover", (e) => {
    e.preventDefault();
    colEl.classList.add("drag-over");
  });
  colEl.addEventListener("dragleave", () => colEl.classList.remove("drag-over"));
  colEl.addEventListener("drop", async (e) => {
    e.preventDefault();
    colEl.classList.remove("drag-over");

    const cardId = e.dataTransfer.getData("text/card-id");
    const draggedColumnId = e.dataTransfer.getData("text/column-id");

    if (cardId) {
      const position = currentBoard.columns.find((c) => c.id === col.id).cards.length;
      try {
        await api(`/api/cards/${cardId}/move`, {
          method: "POST",
          body: JSON.stringify({ column_id: col.id, position }),
        });
        await refreshBoard();
      } catch (err) {
        alert(err.message);
      }
    } else if (draggedColumnId && Number(draggedColumnId) !== col.id) {
      const ids = currentBoard.columns.map((c) => c.id);
      const from = ids.indexOf(Number(draggedColumnId));
      const to = ids.indexOf(col.id);
      ids.splice(from, 1);
      ids.splice(to, 0, Number(draggedColumnId));
      try {
        await api("/api/columns/reorder", {
          method: "POST",
          body: JSON.stringify({
            board_id: currentBoard.id,
            ordered_column_ids: ids,
          }),
        });
        await refreshBoard();
      } catch (err) {
        alert(err.message);
      }
    }
  });

  const cardsEl = document.createElement("div");
  cardsEl.className = "column-cards";
  for (const card of col.cards) {
    cardsEl.appendChild(renderCard(card));
  }

  const addBtn = document.createElement("button");
  addBtn.className = "add-card-btn";
  addBtn.textContent = "+ Add card";
  addBtn.onclick = async () => {
    const title = prompt("Card title?");
    if (!title) return;
    try {
      await api("/api/cards", {
        method: "POST",
        body: JSON.stringify({ column_id: col.id, title }),
      });
      await refreshBoard();
    } catch (e) {
      alert(e.message);
    }
  };

  colEl.appendChild(header);
  colEl.appendChild(cardsEl);
  colEl.appendChild(addBtn);
  return colEl;
}

function renderCard(card) {
  const el = document.createElement("div");
  el.className = "card";
  el.draggable = true;
  el.dataset.cardId = card.id;

  el.innerHTML = `<h3>${escapeHtml(card.title)}</h3><p>${escapeHtml(
    card.description || ""
  )}</p>`;

  const delBtn = document.createElement("button");
  delBtn.className = "icon-btn";
  delBtn.textContent = "✕";
  delBtn.onclick = async (e) => {
    e.stopPropagation();
    try {
      await api(`/api/cards/${card.id}`, { method: "DELETE" });
      await refreshBoard();
    } catch (err) {
      alert(err.message);
    }
  };
  el.appendChild(delBtn);

  el.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/card-id", card.id);
    el.classList.add("dragging");
  });
  el.addEventListener("dragend", () => el.classList.remove("dragging"));

  return el;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

boardSelect.addEventListener("change", async () => {
  currentBoard = boards.find((b) => b.id === Number(boardSelect.value));
  await refreshBoard();
});

newBoardBtn.addEventListener("click", async () => {
  const name = prompt("Board name?");
  if (!name) return;
  const board = await api("/api/boards", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  boards.push(board);
  renderBoardSelect();
  boardSelect.value = board.id;
  currentBoard = board;
  renderBoard();
});

newColumnBtn.addEventListener("click", async () => {
  const name = prompt("Column name?");
  if (!name) return;
  try {
    await api("/api/columns", {
      method: "POST",
      body: JSON.stringify({ board_id: currentBoard.id, name }),
    });
    await refreshBoard();
  } catch (e) {
    alert(e.message);
  }
});

loadBoards();
