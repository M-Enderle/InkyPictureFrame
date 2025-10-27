const state = {
  current: null,
  queue: [],
  history: [],
  settings: {},
};

const DRAG_MIME = "application/x-inky-image-id";

const elements = {
  liveImage: document.getElementById("live-image"),
  liveMeta: document.getElementById("live-meta"),
  queueList: document.getElementById("queue-list"),
  queueEmpty: document.getElementById("queue-empty"),
  queueMeta: document.getElementById("queue-meta"),
  historyGrid: document.getElementById("history-grid"),
  historyEmpty: document.getElementById("history-empty"),
  historyMeta: document.getElementById("history-meta"),
  fileInput: document.getElementById("file-input"),
  selectFiles: document.getElementById("select-files"),
  settingsForm: document.getElementById("settings-form"),
};

let settingsDebounceTimer = null;
let rotationTimer = null;
let rotationIntervalSeconds = null;
let rotationInFlight = false;
const OFFSET_EPSILON = 0.002;

const liveDragState = {
  active: false,
  pointerId: null,
  startX: 0,
  startY: 0,
  initialX: 0,
  initialY: 0,
};

let transformSaveTimer = null;
let lastSavedTransform = {
  imageId: null,
  offsetX: 0,
  offsetY: 0,
};
let transformRequestInFlight = false;

function formatTimeAgo(isoString) {
  if (!isoString) {
    return "";
  }
  const deltaSeconds = Math.floor((Date.now() - Date.parse(isoString)) / 1000);
  if (deltaSeconds < 60) return "Just now";
  if (deltaSeconds < 3600) {
    const minutes = Math.floor(deltaSeconds / 60);
    return `${minutes} min${minutes === 1 ? "" : "s"} ago`;
  }
  if (deltaSeconds < 86400) {
    const hours = Math.floor(deltaSeconds / 3600);
    return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  }
  const days = Math.floor(deltaSeconds / 86400);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function toObjectPosition(offsetX = 0, offsetY = 0) {
  const x = clamp(50 + (offsetX * 50), 0, 100);
  const y = clamp(50 + (offsetY * 50), 0, 100);
  return `${x}% ${y}%`;
}

function applyLiveImageTransform() {
  if (!elements.liveImage) return;
  if (!state.current) {
    elements.liveImage.style.removeProperty("object-position");
    return;
  }
  const offsetX = Number(state.current.offset_x ?? 0);
  const offsetY = Number(state.current.offset_y ?? 0);
  elements.liveImage.style.objectPosition = toObjectPosition(offsetX, offsetY);
}

function applyThumbnailTransform(img, item) {
  if (!img || !item) return;
  const offsetX = Number(item.offset_x ?? 0);
  const offsetY = Number(item.offset_y ?? 0);
  img.style.objectPosition = toObjectPosition(offsetX, offsetY);
}

function syncLastSavedTransform() {
  if (liveDragState.active && state.current && elements.liveImage) {
    if (lastSavedTransform.imageId !== state.current.id) {
      if (
        liveDragState.pointerId !== null &&
        elements.liveImage.hasPointerCapture?.(liveDragState.pointerId)
      ) {
        try {
          elements.liveImage.releasePointerCapture(liveDragState.pointerId);
        } catch (releaseError) {
          // ignore
        }
      }
      liveDragState.active = false;
      liveDragState.pointerId = null;
      elements.liveImage.classList.remove("is-dragging");
    }
  }
  if (state.current && lastSavedTransform.imageId && lastSavedTransform.imageId !== state.current.id) {
    if (transformSaveTimer) {
      window.clearTimeout(transformSaveTimer);
      transformSaveTimer = null;
    }
  }
  if (state.current) {
    lastSavedTransform = {
      imageId: state.current.id,
      offsetX: Number(state.current.offset_x ?? 0),
      offsetY: Number(state.current.offset_y ?? 0),
    };
  } else {
    lastSavedTransform = {
      imageId: null,
      offsetX: 0,
      offsetY: 0,
    };
  }
}

function updateImageCollections(image) {
  if (!image || !image.id) return;
  if (state.current && state.current.id === image.id) {
    state.current = { ...state.current, ...image };
    applyLiveImageTransform();
  }
  state.queue = state.queue.map((item) => (item.id === image.id ? { ...item, ...image } : item));
  state.history = state.history.map((item) => (item.id === image.id ? { ...item, ...image } : item));
  renderQueue();
  renderHistory();
}

function scheduleTransformPersistence(force = false) {
  if (!state.current) return;
  const imageId = state.current.id;

  const readOffsets = () => ({
    offsetX: Number(state.current?.offset_x ?? 0),
    offsetY: Number(state.current?.offset_y ?? 0),
  });

  const { offsetX, offsetY } = readOffsets();
  const unchanged =
    lastSavedTransform.imageId === imageId &&
    Math.abs(offsetX - lastSavedTransform.offsetX) < OFFSET_EPSILON &&
    Math.abs(offsetY - lastSavedTransform.offsetY) < OFFSET_EPSILON;
  if (unchanged) {
    if (transformSaveTimer) {
      window.clearTimeout(transformSaveTimer);
      transformSaveTimer = null;
    }
    return;
  }

  const persist = () => {
    transformSaveTimer = null;
    if (!state.current || state.current.id !== imageId) {
      return;
    }
    const latest = readOffsets();
    const stillUnchanged =
      lastSavedTransform.imageId === imageId &&
      Math.abs(latest.offsetX - lastSavedTransform.offsetX) < OFFSET_EPSILON &&
      Math.abs(latest.offsetY - lastSavedTransform.offsetY) < OFFSET_EPSILON;
    if (stillUnchanged) {
      return;
    }
    if (transformRequestInFlight) {
      transformSaveTimer = window.setTimeout(persist, 150);
      return;
    }
    transformRequestInFlight = true;
    saveImageTransform(imageId, latest.offsetX, latest.offsetY).finally(() => {
      transformRequestInFlight = false;
    });
  };

  if (transformSaveTimer) {
    window.clearTimeout(transformSaveTimer);
  }

  if (force) {
    persist();
  } else {
    transformSaveTimer = window.setTimeout(persist, 180);
  }
}

async function saveImageTransform(imageId, offsetX, offsetY) {
  try {
    const response = await fetch(`/api/images/${imageId}/transform`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ offset_x: offsetX, offset_y: offsetY }),
    });
    if (!response.ok) {
      if (response.status === 404) {
        await fetchState();
      }
      throw new Error("Failed to save image transform");
    }
    const data = await response.json();
    updateImageCollections(data);
    lastSavedTransform = {
      imageId: data.id,
      offsetX: Number(data.offset_x ?? 0),
      offsetY: Number(data.offset_y ?? 0),
    };
  } catch (error) {
    console.error(error);
  }
}

function handleLiveImageDrag() {
  const img = elements.liveImage;
  if (!img) return;

  const endDrag = (event) => {
    if (!liveDragState.active || event.pointerId !== liveDragState.pointerId) return;
    liveDragState.active = false;
    liveDragState.pointerId = null;
    img.classList.remove("is-dragging");
    if (img.hasPointerCapture(event.pointerId)) {
      img.releasePointerCapture(event.pointerId);
    }
    scheduleTransformPersistence(true);
  };

  img.addEventListener("pointerdown", (event) => {
    if (!state.current) return;
    if (event.button !== undefined && event.button !== 0 && event.pointerType !== "touch") return;
    event.preventDefault();
    event.stopPropagation();
    liveDragState.active = true;
    liveDragState.pointerId = event.pointerId;
    liveDragState.startX = event.clientX;
    liveDragState.startY = event.clientY;
  liveDragState.initialX = Number(state.current.offset_x ?? 0);
  liveDragState.initialY = Number(state.current.offset_y ?? 0);
    img.classList.add("is-dragging");
    try {
      img.setPointerCapture(event.pointerId);
    } catch (captureError) {
      // Ignore capture failures (e.g., unsupported platforms)
    }
  });

  img.addEventListener("pointermove", (event) => {
    if (!liveDragState.active || event.pointerId !== liveDragState.pointerId || !state.current) return;
    const width = img.clientWidth || 1;
    const height = img.clientHeight || 1;
    const deltaX = (event.clientX - liveDragState.startX) / (width / 2);
    const deltaY = (event.clientY - liveDragState.startY) / (height / 2);
    const nextX = clamp(liveDragState.initialX + deltaX, -1, 1);
    const nextY = clamp(liveDragState.initialY + deltaY, -1, 1);
    state.current.offset_x = nextX;
    state.current.offset_y = nextY;
    applyLiveImageTransform();
    scheduleTransformPersistence();
  });

  img.addEventListener("pointerup", endDrag);
  img.addEventListener("pointercancel", endDrag);
  img.addEventListener("lostpointercapture", () => {
    if (!liveDragState.active) return;
    liveDragState.active = false;
    liveDragState.pointerId = null;
    img.classList.remove("is-dragging");
    scheduleTransformPersistence(true);
  });
}

async function fetchState() {
  try {
    const response = await fetch("/api/state");
    if (!response.ok) throw new Error("Failed to load state");
    const data = await response.json();
    state.current = data.current;
    state.queue = data.queue;
    state.history = data.history;
    state.settings = data.settings;
    syncLastSavedTransform();
    renderAll();
    ensureAutoAdvance();
  } catch (error) {
    console.error(error);
  }
}

function renderAll() {
  renderLive();
  renderQueue();
  renderHistory();
  renderSettings();
}

function renderLive() {
  if (!elements.liveImage) return;
  if (state.current) {
    const nextId = state.current.id;
    const currentId = elements.liveImage.dataset.imageId;
    if (!liveDragState.active || currentId !== nextId) {
      elements.liveImage.src = state.current.image_url;
      elements.liveImage.dataset.imageId = nextId;
    }
    elements.liveImage.alt = state.current.filename;
    const parts = [state.current.filename];
    const updatedLabel = formatTimeAgo(state.current.uploaded_at);
    if (updatedLabel) {
      parts.push(`Updated ${updatedLabel}`);
    }
    parts.push("Drag to reposition");
    elements.liveMeta.textContent = parts.join(" · ");
    applyLiveImageTransform();
  } else {
    elements.liveImage.removeAttribute("src");
    elements.liveImage.alt = "No image";
    elements.liveMeta.textContent = "No image currently displayed";
    elements.liveImage.style.removeProperty("object-position");
    delete elements.liveImage.dataset.imageId;
  }
}

function renderQueue() {
  const { queueList, queueEmpty, queueMeta } = elements;
  queueList.innerHTML = "";
  if (!state.queue.length) {
    queueEmpty.style.display = "block";
    queueMeta.textContent = "Empty queue";
  } else {
    queueEmpty.style.display = "none";
    queueMeta.textContent = `${state.queue.length} awaiting`;
  }
  if (state.queue.length === 1) {
    queueMeta.textContent = "1 image awaiting";
  }
  const template = document.getElementById("queue-item-template");

  state.queue.forEach((item) => {
    const clone = template.content.firstElementChild.cloneNode(true);
    clone.dataset.id = item.id;
    const img = clone.querySelector("img");
  img.src = item.image_url;
    img.alt = item.filename;
    applyThumbnailTransform(img, item);
    clone.querySelector(".queue-item__name").textContent = item.filename;
    clone.querySelector(".queue-item__time").textContent = formatTimeAgo(item.uploaded_at);
    queueList.appendChild(clone);
  });
}

function renderHistory() {
  const { historyGrid, historyEmpty, historyMeta } = elements;
  historyGrid.innerHTML = "";
  if (!state.history.length) {
    historyEmpty.style.display = "block";
    historyMeta.textContent = "No past images yet";
  } else {
    historyEmpty.style.display = "none";
    historyMeta.textContent = `${state.history.length} already shown`;
  }
  if (state.history.length === 1) {
    historyMeta.textContent = "1 image shown previously";
  }
  const template = document.getElementById("history-item-template");
  state.history.forEach((item) => {
    const clone = template.content.firstElementChild.cloneNode(true);
    clone.dataset.id = item.id;
    clone.draggable = true;
    const img = clone.querySelector("img");
  img.src = item.image_url;
    img.alt = item.filename;
    applyThumbnailTransform(img, item);
    clone.querySelector(".history-item__name").textContent = item.filename;
    historyGrid.appendChild(clone);
  });
}

function renderSettings() {
  const form = elements.settingsForm;
  if (!form) return;
  form.elements.change_interval.value = state.settings.change_interval ?? 60;
  form.elements.led_brightness.value = state.settings.led_brightness ?? 50;
  form.querySelector('[data-display="led_brightness"]').textContent = `${state.settings.led_brightness ?? 50}%`;
  form.elements.power_on.checked = Boolean(state.settings.power_on);
  form.elements.saturation.value = state.settings.saturation ?? 0.5;
  form.querySelector('[data-display="saturation"]').textContent = (state.settings.saturation ?? 0.5).toFixed(2);
}

async function uploadFiles(fileList) {
  if (!fileList || !fileList.length) return;
  const formData = new FormData();
  Array.from(fileList).forEach((file) => {
    formData.append("files", file);
  });
  try {
    const response = await fetch("/api/upload", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) throw new Error("Upload failed");
    await fetchState();
  } catch (error) {
    console.error(error);
  }
}

async function removeFromQueue(imageId) {
  try {
    const response = await fetch(`/api/queue/${imageId}`, { method: "DELETE" });
    if (!response.ok) throw new Error("Failed to remove from queue");
    await fetchState();
  } catch (error) {
    console.error(error);
  }
}

async function reorderQueue(newOrder) {
  try {
    const response = await fetch("/api/queue/reorder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_ids: newOrder }),
    });
    if (!response.ok) throw new Error("Failed to reorder queue");
    await fetchState();
  } catch (error) {
    console.error(error);
  }
}

async function insertIntoQueue(imageId, index) {
  try {
    const response = await fetch("/api/queue/insert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_id: imageId, index }),
    });
    if (!response.ok) throw new Error("Failed to insert into queue");
    await fetchState();
  } catch (error) {
    console.error(error);
  }
}

async function moveToHistory(imageId, index) {
  try {
    const response = await fetch("/api/history/insert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_id: imageId, index }),
    });
    if (!response.ok) throw new Error("Failed to move image to history");
    await fetchState();
  } catch (error) {
    console.error(error);
  }
}

function handleQueueDragAndDrop() {
  let draggedQueueId = null;
  elements.queueList.addEventListener("dragstart", (event) => {
    const item = event.target.closest(".queue-item");
    if (!item) return;
    draggedQueueId = item.dataset.id;
    item.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData(DRAG_MIME, draggedQueueId);
    event.dataTransfer.setData("text/plain", draggedQueueId);
    event.dataTransfer.setData("text/source", "queue");
  });

  elements.queueList.addEventListener("dragend", (event) => {
    const item = event.target.closest(".queue-item");
    if (!item) return;
    item.classList.remove("dragging");
    draggedQueueId = null;
    elements.queueList.classList.remove("queue__list--dropping");
    elements.queueList.querySelectorAll(".queue-item").forEach((node) => node.classList.remove("drag-over"));
  });

  elements.queueList.addEventListener("dragenter", (event) => {
    if (!isImageDragEvent(event)) return;
    event.preventDefault();
    elements.queueList.classList.add("queue__list--dropping");
  });

  elements.queueList.addEventListener("dragover", (event) => {
    if (!isImageDragEvent(event)) return;
    event.preventDefault();
    const overItem = event.target.closest(".queue-item");
    elements.queueList.querySelectorAll(".queue-item").forEach((node) => {
      if (node !== overItem) {
        node.classList.remove("drag-over");
      }
    });
    if (overItem && !overItem.classList.contains("dragging")) {
      overItem.classList.add("drag-over");
    }
    elements.queueList.classList.add("queue__list--dropping");
    const afterElement = getDragAfterElement(event.clientY);
    const dragging = elements.queueList.querySelector(".queue-item.dragging");
    if (dragging) {
      if (!afterElement) {
        elements.queueList.appendChild(dragging);
      } else if (afterElement !== dragging) {
        elements.queueList.insertBefore(dragging, afterElement);
      }
    }
  });

  elements.queueList.addEventListener("drop", async (event) => {
    if (!isImageDragEvent(event)) return;
    event.preventDefault();
    const incomingId = event.dataTransfer.getData(DRAG_MIME);
    if (incomingId && incomingId !== draggedQueueId) {
      elements.queueList.classList.remove("queue__list--dropping");
      elements.queueList.querySelectorAll(".queue-item").forEach((node) => node.classList.remove("drag-over"));
      const dropIndex = getQueueDropIndex(event.clientY);
      await insertIntoQueue(incomingId, dropIndex);
      draggedQueueId = null;
      return;
    }
    elements.queueList.classList.remove("queue__list--dropping");
    elements.queueList.querySelectorAll(".queue-item").forEach((node) => node.classList.remove("drag-over"));
    const orderedIds = Array.from(elements.queueList.querySelectorAll(".queue-item"), (node) => node.dataset.id);
    if (orderedIds.length && draggedQueueId) {
      await reorderQueue(orderedIds);
      draggedQueueId = null;
    }
  });

  elements.queueList.addEventListener("dragleave", (event) => {
    if (event.dataTransfer && !isImageDragEvent(event)) return;
    const item = event.target.closest(".queue-item");
    if (item) {
      item.classList.remove("drag-over");
    }
    if (!elements.queueList.contains(event.relatedTarget)) {
      elements.queueList.classList.remove("queue__list--dropping");
    }
  });
}

function getDragAfterElement(y) {
  const draggableElements = [...elements.queueList.querySelectorAll(".queue-item:not(.dragging)")];
  return draggableElements.reduce(
    (closest, child) => {
      const box = child.getBoundingClientRect();
      const offset = y - box.top - box.height / 2;
      if (offset < 0 && offset > closest.offset) {
        return { offset, element: child };
      }
      return closest;
    },
    { offset: Number.NEGATIVE_INFINITY, element: null }
  ).element;
}

function getQueueDropIndex(y) {
  const candidates = [...elements.queueList.querySelectorAll(".queue-item:not(.dragging)")];
  if (!candidates.length) return 0;
  for (let index = 0; index < candidates.length; index += 1) {
    const box = candidates[index].getBoundingClientRect();
    const offset = y - box.top - box.height / 2;
    if (offset < 0) {
      return index;
    }
  }
  return candidates.length;
}

function getHistoryDropIndex(y) {
  const candidates = [...elements.historyGrid.querySelectorAll(".history-item:not(.dragging)")];
  if (!candidates.length) return 0;
  for (let index = 0; index < candidates.length; index += 1) {
    const box = candidates[index].getBoundingClientRect();
    const offset = y - box.top - box.height / 2;
    if (offset < 0) {
      return index;
    }
  }
  return candidates.length;
}

function isImageDragEvent(event) {
  const types = event.dataTransfer?.types;
  if (!types) return false;
  return Array.from(types).includes(DRAG_MIME);
}

function handleQueueRemoveClicks() {
  elements.queueList.addEventListener("click", async (event) => {
    const button = event.target.closest(".queue-item__remove");
    if (!button) return;
    const container = button.closest(".queue-item");
    if (!container) return;
    await removeFromQueue(container.dataset.id);
  });
}

function handleHistoryDrag() {
  elements.historyGrid.addEventListener("dragstart", (event) => {
    const card = event.target.closest(".history-item");
    if (!card || !event.dataTransfer) return;
    card.classList.add("dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData(DRAG_MIME, card.dataset.id ?? "");
    event.dataTransfer.setData("text/plain", card.dataset.id ?? "");
    event.dataTransfer.setData("text/source", "history");
  });

  elements.historyGrid.addEventListener("dragend", (event) => {
    const card = event.target.closest(".history-item");
    if (!card) return;
    card.classList.remove("dragging");
  });
}

function handleHistoryDropZone() {
  const grid = elements.historyGrid;
  grid.addEventListener("dragenter", (event) => {
    if (!isImageDragEvent(event)) return;
    event.preventDefault();
    grid.classList.add("history__grid--dropping");
  });

  grid.addEventListener("dragover", (event) => {
    if (!isImageDragEvent(event)) return;
    event.preventDefault();
    grid.classList.add("history__grid--dropping");
    const overItem = event.target.closest(".history-item");
    grid.querySelectorAll(".history-item").forEach((node) => {
      if (node !== overItem) {
        node.classList.remove("drag-over");
      }
    });
    if (overItem && !overItem.classList.contains("dragging")) {
      overItem.classList.add("drag-over");
    }
  });

  grid.addEventListener("drop", async (event) => {
    if (!isImageDragEvent(event)) return;
    event.preventDefault();
    const incomingId = event.dataTransfer.getData(DRAG_MIME);
    grid.classList.remove("history__grid--dropping");
    grid.querySelectorAll(".history-item").forEach((node) => node.classList.remove("drag-over"));
    if (!incomingId) return;
    const dropIndex = getHistoryDropIndex(event.clientY);
    await moveToHistory(incomingId, dropIndex);
  });

  grid.addEventListener("dragleave", (event) => {
    if (event.dataTransfer && !isImageDragEvent(event)) return;
    const card = event.target.closest(".history-item");
    if (card) {
      card.classList.remove("drag-over");
    }
    if (!grid.contains(event.relatedTarget)) {
      grid.classList.remove("history__grid--dropping");
    }
  });
}

function handleFileSelection() {
  if (!elements.selectFiles || !elements.fileInput) return;
  elements.selectFiles.addEventListener("click", () => {
    elements.fileInput.click();
  });
  elements.fileInput.addEventListener("change", async (event) => {
    await uploadFiles(event.target.files);
    event.target.value = "";
  });
}

function handleSettingsForm() {
  elements.settingsForm.addEventListener("input", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) return;

    if (target.name === "led_brightness") {
      elements.settingsForm
        .querySelector('[data-display="led_brightness"]').textContent = `${target.value}%`;
    }
    if (target.name === "saturation") {
      elements.settingsForm.querySelector('[data-display="saturation"]').textContent = Number(target.value).toFixed(2);
    }

    scheduleSettingsUpdate(target);
  });
}

function scheduleSettingsUpdate(input) {
  if (settingsDebounceTimer) window.clearTimeout(settingsDebounceTimer);
  settingsDebounceTimer = window.setTimeout(async () => {
    const payload = buildSettingsPayload();
    await applySettings(payload);
  }, 250);
}

function buildSettingsPayload() {
  const form = elements.settingsForm;
  const payload = {};
  payload.change_interval = Number(form.elements.change_interval.value);
  payload.led_brightness = Number(form.elements.led_brightness.value);
  payload.power_on = form.elements.power_on.checked;
  payload.saturation = Number(form.elements.saturation.value);
  return payload;
}

async function applySettings(payload) {
  try {
    const response = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error("Failed to save settings");
    const data = await response.json();
    state.settings = data;
    renderSettings();
    ensureAutoAdvance();
  } catch (error) {
    console.error(error);
  }
}

function ensureAutoAdvance() {
  const interval = Number(state.settings.change_interval ?? 0);
  const enabled = Boolean(state.settings.power_on);
  if (!enabled || interval <= 0) {
    if (rotationTimer) {
      window.clearInterval(rotationTimer);
      rotationTimer = null;
      rotationIntervalSeconds = null;
    }
    return;
  }
  if (rotationTimer && rotationIntervalSeconds === interval) {
    return;
  }
  if (rotationTimer) {
    window.clearInterval(rotationTimer);
  }
  rotationIntervalSeconds = interval;
  rotationTimer = window.setInterval(() => {
    if (rotationInFlight) return;
    if (!state.settings.power_on) return;
    advanceFrame();
  }, interval * 1000);
}

async function advanceFrame() {
  if (rotationInFlight) return;
  rotationInFlight = true;
  try {
    const response = await fetch("/api/frame/advance", { method: "POST" });
    if (!response.ok) {
      if (response.status === 404) {
        await fetchState();
      }
      return;
    }
    await fetchState();
  } catch (error) {
    console.error(error);
  } finally {
    rotationInFlight = false;
  }
}

function init() {
  fetchState();
  handleLiveImageDrag();
  handleQueueDragAndDrop();
  handleQueueRemoveClicks();
  handleHistoryDrag();
  handleHistoryDropZone();
  handleFileSelection();
  handleSettingsForm();
  window.setInterval(fetchState, 20000);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
