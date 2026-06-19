const ZOOM_LEVELS = [
  { label: "Week", pxPerDay: 12 },
  { label: "Day", pxPerDay: 24 },
  { label: "Detail", pxPerDay: 40 },
];

const COLORS = ["#4f86f7", "#22a06b", "#e5484d", "#f5a623", "#9b59b6", "#1abc9c"];

const WINDOW_STORAGE_KEY = "gantt-window";
const SIDEBAR_WIDTH_KEY = "gantt-sidebar-width";
const SIDEBAR_MIN = 120;
const SIDEBAR_MAX = 480;
const SIDEBAR_DEFAULT = 200;
const ROW_HEIGHT = 44;
const ROW_HEIGHT_WITH_DESC = 60;

let tasks = [];
let zoomIndex = 1;
let windowStart = null;
let windowEnd = null;
let sidebarWidth = SIDEBAR_DEFAULT;
let editingId = null;
let saveTimer = null;

const chart = document.getElementById("chart");
const sidebar = document.getElementById("sidebar");
const timelineHeader = document.getElementById("timeline-header");
const timelineBody = document.getElementById("timeline-body");
const windowStartInput = document.getElementById("window-start");
const windowEndInput = document.getElementById("window-end");
const hintEl = document.querySelector(".hint");
const dialog = document.getElementById("task-dialog");
const form = document.getElementById("task-form");

async function loadTasks() {
  const res = await fetch("/api/tasks");
  if (!res.ok) throw new Error("Failed to load tasks");
  return res.json();
}

async function saveTasks() {
  const res = await fetch("/api/tasks", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(tasks),
  });
  if (!res.ok) throw new Error("Failed to save tasks");
  setHint("Drag bars to move · Drag edges to resize · Double-click a bar to edit · Saved");
}

function scheduleSave() {
  clearTimeout(saveTimer);
  setHint("Saving…");
  saveTimer = setTimeout(async () => {
    try {
      await saveTasks();
    } catch {
      setHint("Could not save — check that the server is running");
    }
  }, 300);
}

function setHint(text) {
  if (hintEl) hintEl.textContent = text;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(str) {
  return escapeHtml(str).replace(/'/g, "&#39;");
}

function rowHeight(task) {
  return task.description?.trim() ? ROW_HEIGHT_WITH_DESC : ROW_HEIGHT;
}

function totalChartHeight() {
  return tasks.reduce((sum, t) => sum + rowHeight(t), 0);
}

function loadSidebarWidth() {
  const saved = Number(localStorage.getItem(SIDEBAR_WIDTH_KEY));
  if (Number.isFinite(saved)) applySidebarWidth(saved, { persist: false });
  else applySidebarWidth(SIDEBAR_DEFAULT, { persist: false });
}

function applySidebarWidth(width, { persist = true } = {}) {
  sidebarWidth = Math.max(SIDEBAR_MIN, Math.min(SIDEBAR_MAX, width));
  document.documentElement.style.setProperty("--sidebar-width", `${sidebarWidth}px`);
  if (persist) localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth));
}

function setupSidebarResize() {
  const handle = document.getElementById("sidebar-resize");
  if (!handle || handle.dataset.bound) return;
  handle.dataset.bound = "1";

  handle.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = sidebarWidth;
    handle.classList.add("resizing");
    handle.setPointerCapture?.(e.pointerId);

    const onMove = (ev) => {
      applySidebarWidth(startWidth + (ev.clientX - startX));
    };

    const onUp = () => {
      handle.classList.remove("resizing");
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
    };

    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
  });
}

function parseDate(str) {
  const [y, m, d] = str.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function formatDate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function daysBetween(a, b) {
  return Math.round((b - a) / 86400000);
}

function addDays(date, n) {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return d;
}

function computeBoundsFromTasks() {
  if (tasks.length === 0) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return { start: addDays(today, -7), end: addDays(today, 30) };
  }
  let min = parseDate(tasks[0].start);
  let max = parseDate(tasks[0].end);
  for (const t of tasks) {
    const s = parseDate(t.start);
    const e = parseDate(t.end);
    if (s < min) min = s;
    if (e > max) max = e;
  }
  return { start: addDays(min, -7), end: addDays(max, 14) };
}

function loadWindowFromStorage() {
  try {
    const raw = localStorage.getItem(WINDOW_STORAGE_KEY);
    if (!raw) return null;
    const { start, end } = JSON.parse(raw);
    if (!start || !end || start > end) return null;
    return { start: parseDate(start), end: parseDate(end) };
  } catch {
    return null;
  }
}

function saveWindowToStorage() {
  if (!windowStart || !windowEnd) return;
  localStorage.setItem(
    WINDOW_STORAGE_KEY,
    JSON.stringify({ start: formatDate(windowStart), end: formatDate(windowEnd) })
  );
}

function setWindow(start, end, { persist = true } = {}) {
  windowStart = start;
  windowEnd = end;
  windowStartInput.value = formatDate(start);
  windowEndInput.value = formatDate(end);
  if (persist) saveWindowToStorage();
}

function ensureWindow() {
  if (windowStart && windowEnd && windowStart <= windowEnd) return;
  const saved = loadWindowFromStorage();
  if (saved) {
    setWindow(saved.start, saved.end, { persist: false });
    return;
  }
  const bounds = computeBoundsFromTasks();
  setWindow(bounds.start, bounds.end);
}

function getTimelineBounds() {
  ensureWindow();
  return { start: windowStart, end: windowEnd };
}

function syncWindowInputs() {
  const bounds = getTimelineBounds();
  windowStartInput.value = formatDate(bounds.start);
  windowEndInput.value = formatDate(bounds.end);
}

function pxPerDay() {
  return ZOOM_LEVELS[zoomIndex].pxPerDay;
}

function render() {
  const bounds = getTimelineBounds();
  const totalDays = daysBetween(bounds.start, bounds.end) + 1;
  const width = totalDays * pxPerDay();

  syncWindowInputs();
  document.getElementById("zoom-label").textContent = ZOOM_LEVELS[zoomIndex].label;

  if (tasks.length === 0) {
    sidebar.innerHTML = `<div class="sidebar-header">Tasks</div><div class="empty-state"><p>No tasks yet</p></div>`;
    timelineHeader.innerHTML = "";
    timelineBody.innerHTML = `<div class="empty-state"><p>Click "+ Add task" to get started</p><button class="btn primary" onclick="document.getElementById('add-task-btn').click()">Add task</button></div>`;
    return;
  }

  sidebar.innerHTML = `<div class="sidebar-header">Tasks</div>` +
    tasks.map((t) => {
      const h = rowHeight(t);
      const desc = t.description?.trim();
      return `<div class="task-label${desc ? " has-description" : ""}" data-id="${t.id}" style="height:${h}px" title="${escapeAttr(t.name)}">
        <span class="task-name">${escapeHtml(t.name)}</span>
        ${desc ? `<span class="task-description">${escapeHtml(desc)}</span>` : ""}
      </div>`;
    }).join("");

  const chartHeight = totalChartHeight();
  timelineHeader.style.width = width + "px";
  timelineHeader.innerHTML = buildHeaderCells(bounds, totalDays);

  timelineBody.style.width = width + "px";
  timelineBody.innerHTML =
    `<div class="grid-overlay" style="width:${width}px;height:${chartHeight}px">` +
    buildGrid(bounds, totalDays) + buildTodayLine(bounds) +
    `</div>` +
    tasks.map((t) => buildTaskRow(t, bounds)).join("");

  bindSidebarClicks();
  bindBarInteractions(bounds);
}

function updateAndSave() {
  render();
  scheduleSave();
}

function buildHeaderCells(bounds, totalDays) {
  const ppd = pxPerDay();
  let html = "";
  const showDays = ppd >= 24;

  if (showDays) {
    for (let i = 0; i < totalDays; i++) {
      const d = addDays(bounds.start, i);
      const left = i * ppd;
      const isMonthStart = d.getDate() === 1;
      const label = isMonthStart
        ? d.toLocaleDateString(undefined, { month: "short", year: "numeric" })
        : d.getDate();
      html += `<div class="header-cell${isMonthStart ? " month" : ""}" style="left:${left}px;width:${ppd}px">${label}</div>`;
    }
  } else {
    let i = 0;
    while (i < totalDays) {
      const d = addDays(bounds.start, i);
      const weekStart = i;
      const daysInWeek = Math.min(7 - (d.getDay() === 0 ? 6 : d.getDay() - 1), totalDays - i);
      const w = daysInWeek * ppd;
      const label = d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
      html += `<div class="header-cell month" style="left:${weekStart * ppd}px;width:${w}px">${label}</div>`;
      i += daysInWeek;
    }
  }
  return html;
}

function buildGrid(bounds, totalDays) {
  const ppd = pxPerDay();
  let html = "";
  for (let i = 0; i < totalDays; i++) {
    const d = addDays(bounds.start, i);
    const day = d.getDay();
    if (day === 0 || day === 6) {
      html += `<div class="grid-line weekend" style="left:${i * ppd}px;width:${ppd}px"></div>`;
    } else {
      html += `<div class="grid-line" style="left:${i * ppd}px"></div>`;
    }
  }
  return html;
}

function buildTodayLine(bounds) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const offset = daysBetween(bounds.start, today);
  const totalDays = daysBetween(bounds.start, bounds.end) + 1;
  if (offset < 0 || offset >= totalDays) return "";
  const ppd = pxPerDay();
  return `<div class="today-line" style="left:${offset * ppd + ppd / 2}px"></div>`;
}

function buildTaskRow(task, bounds) {
  const ppd = pxPerDay();
  const start = parseDate(task.start);
  const end = parseDate(task.end);
  const left = daysBetween(bounds.start, start) * ppd;
  const width = Math.max((daysBetween(start, end) + 1) * ppd - 2, 8);
  const h = rowHeight(task);

  return `<div class="timeline-row" style="height:${h}px">
    <div class="task-bar" data-id="${task.id}" style="left:${left}px;width:${width}px;background:${task.color}" title="${escapeAttr(task.name)}: ${task.start} → ${task.end}">
      <span class="resize-handle left" data-resize="start"></span>
      ${escapeHtml(task.name)}
      <span class="resize-handle right" data-resize="end"></span>
    </div>
  </div>`;
}

function bindSidebarClicks() {
  sidebar.querySelectorAll(".task-label").forEach((el) => {
    el.addEventListener("click", () => openDialog(el.dataset.id));
  });
}

function bindBarInteractions(bounds) {
  timelineBody.querySelectorAll(".task-bar").forEach((bar) => {
    const id = bar.dataset.id;
    bar.addEventListener("dblclick", (e) => {
      if (e.target.classList.contains("resize-handle")) return;
      openDialog(id);
    });

    const leftHandle = bar.querySelector('[data-resize="start"]');
    const rightHandle = bar.querySelector('[data-resize="end"]');

    setupDrag(bar, id, bounds, "move");
    setupDrag(leftHandle, id, bounds, "start");
    setupDrag(rightHandle, id, bounds, "end");
  });
}

function setupDrag(el, taskId, bounds, mode) {
  el.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    e.stopPropagation();

    const task = tasks.find((t) => t.id === taskId);
    if (!task) return;

    const bar = el.classList.contains("task-bar") ? el : el.closest(".task-bar");
    bar.classList.add("dragging");
    bar.setPointerCapture?.(e.pointerId);

    const ppd = pxPerDay();
    const origStart = parseDate(task.start);
    const origEnd = parseDate(task.end);
    const startX = e.clientX;

    const applyDates = (deltaDays) => {
      if (mode === "move") {
        task.start = formatDate(addDays(origStart, deltaDays));
        task.end = formatDate(addDays(origEnd, deltaDays));
      } else if (mode === "start") {
        const newStart = addDays(origStart, deltaDays);
        if (newStart <= origEnd) task.start = formatDate(newStart);
      } else {
        const newEnd = addDays(origEnd, deltaDays);
        if (newEnd >= origStart) task.end = formatDate(newEnd);
      }

      const start = parseDate(task.start);
      const end = parseDate(task.end);
      const left = daysBetween(bounds.start, start) * ppd;
      const width = Math.max((daysBetween(start, end) + 1) * ppd - 2, 8);
      bar.style.left = left + "px";
      bar.style.width = width + "px";
      bar.title = `${task.name}: ${task.start} → ${task.end}`;
    };

    const onMove = (ev) => {
      const deltaDays = Math.round((ev.clientX - startX) / ppd);
      if (deltaDays !== 0 || mode === "move") applyDates(deltaDays);
    };

    const onUp = () => {
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      bar.classList.remove("dragging");
      scheduleSave();
    };

    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
  });
}

function openDialog(id) {
  editingId = id;
  const task = tasks.find((t) => t.id === id);
  if (!task) return;

  document.getElementById("dialog-title").textContent = "Edit task";
  document.getElementById("task-name").value = task.name;
  document.getElementById("task-description").value = task.description || "";
  document.getElementById("task-start").value = task.start;
  document.getElementById("task-end").value = task.end;
  document.getElementById("task-color").value = task.color;
  document.getElementById("delete-task-btn").style.display = "";

  dialog.showModal();
}

function openNewDialog() {
  editingId = null;
  const today = formatDate(new Date());
  const end = formatDate(addDays(new Date(), 7));

  document.getElementById("dialog-title").textContent = "Add task";
  document.getElementById("task-name").value = "";
  document.getElementById("task-description").value = "";
  document.getElementById("task-start").value = today;
  document.getElementById("task-end").value = end;
  document.getElementById("task-color").value = COLORS[tasks.length % COLORS.length];
  document.getElementById("delete-task-btn").style.display = "none";

  dialog.showModal();
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const name = document.getElementById("task-name").value.trim();
  const description = document.getElementById("task-description").value.trim();
  const start = document.getElementById("task-start").value;
  const end = document.getElementById("task-end").value;
  const color = document.getElementById("task-color").value;

  if (!name || !start || !end || start > end) return;

  const payload = { name, description, start, end, color };

  if (editingId) {
    const task = tasks.find((t) => t.id === editingId);
    if (task) Object.assign(task, payload);
  } else {
    tasks.push({ id: crypto.randomUUID(), ...payload });
  }

  dialog.close();
  updateAndSave();
});

document.getElementById("cancel-btn").addEventListener("click", () => dialog.close());
document.getElementById("delete-task-btn").addEventListener("click", () => {
  if (editingId) {
    tasks = tasks.filter((t) => t.id !== editingId);
    dialog.close();
    updateAndSave();
  }
});

document.getElementById("add-task-btn").addEventListener("click", openNewDialog);

document.getElementById("zoom-in").addEventListener("click", () => {
  if (zoomIndex < ZOOM_LEVELS.length - 1) { zoomIndex++; render(); }
});

document.getElementById("zoom-out").addEventListener("click", () => {
  if (zoomIndex > 0) { zoomIndex--; render(); }
});

function applyWindowFromInputs() {
  const start = windowStartInput.value;
  const end = windowEndInput.value;
  if (!start || !end || start > end) return;
  setWindow(parseDate(start), parseDate(end));
  render();
}

windowStartInput.addEventListener("change", applyWindowFromInputs);
windowEndInput.addEventListener("change", applyWindowFromInputs);

document.getElementById("fit-tasks-btn").addEventListener("click", () => {
  const bounds = computeBoundsFromTasks();
  setWindow(bounds.start, bounds.end);
  render();
});

document.getElementById("export-btn").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(tasks, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "gantt-tasks.json";
  a.click();
  URL.revokeObjectURL(a.href);
});

document.getElementById("import-input").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const imported = JSON.parse(reader.result);
      if (Array.isArray(imported) && imported.every((t) => t.name && t.start && t.end)) {
        tasks = imported.map((t) => ({
          ...t,
          id: t.id || crypto.randomUUID(),
          description: t.description || "",
        }));
        updateAndSave();
      }
    } catch (_) {}
    e.target.value = "";
  };
  reader.readAsText(file);
});

async function init() {
  loadSidebarWidth();
  setupSidebarResize();
  try {
    tasks = (await loadTasks()).map((t) => ({ ...t, description: t.description || "" }));
    ensureWindow();
    render();
  } catch {
    setHint("Could not connect to server — run: python app.py");
    sidebar.innerHTML = `<div class="sidebar-header">Tasks</div><div class="empty-state"><p>Server offline</p></div>`;
    timelineBody.innerHTML = `<div class="empty-state"><p>Start the Python server to load your chart</p></div>`;
  }
}

init();
