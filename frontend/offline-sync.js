/**
 * 離線辨識 Fallback（Offline-First with Delayed Queue）
 *
 * 本地 IndexedDB 儲存相片 Blob；localStorage 儲存 OfflineDiagnosticTask 中繼資料。
 * 結構對齊後端 backend/offline_schemas.py :: OfflineDiagnosticTask
 */

const OFFLINE_IDB_NAME = "agri_offline_vault";
const OFFLINE_IDB_STORE = "images";
const LS_OFFLINE_QUEUE = "agri_offline_tasks";
const LS_OFFLINE_WIFI_ONLY = "agri_offline_wifi_only";

/** @returns {boolean} */
function isBrowserOffline() {
  return typeof navigator !== "undefined" && navigator.onLine === false;
}

function readOfflineQueue() {
  try {
    return JSON.parse(localStorage.getItem(LS_OFFLINE_QUEUE) || "[]");
  } catch {
    return [];
  }
}

function writeOfflineQueue(tasks) {
  localStorage.setItem(LS_OFFLINE_QUEUE, JSON.stringify(tasks));
}

function generateTaskId() {
  return crypto.randomUUID();
}

/**
 * 離線規則引擎（鏡像 backend/offline_rule_engine.py）
 * @param {string} cropName
 * @param {object} check
 */
function evaluateOfflineRuleEngine(cropName, check) {
  const crop = String(cropName || "").trim();
  const lower = crop.toLowerCase();
  const matched = [];
  let preliminary = "外觀特徵不夠典型，請等待連網後 AI 的精準診斷。";
  let emergency = "巡視周邊區域，隔離病灶株，避免盲目噴灑不明藥劑。";

  if (crop.includes("番茄") || lower.includes("tomato")) {
    if (check.has_water_soaked_spots && check.affected_part === "leaves") {
      matched.push("tomato_water_soaked_leaves");
      preliminary = "【離線預警】高度疑似真菌性病害（如番茄晚疫病或露菌病）。";
      emergency =
        "緊急處置：請立刻剪除受害嚴重葉片並移出設施銷毀。暫停修剪，注意排水。";
      if (check.after_rain) {
        matched.push("tomato_after_rain");
        preliminary += "（症狀於下雨後出現，與晚疫病高度吻合。）";
      }
    }
    if (check.has_white_powder && check.affected_part === "leaves") {
      matched.push("tomato_white_powder");
      preliminary = "【離線預警】疑似白粉病。";
      emergency = "加強通風、降低葉面濕度，避免過量氮肥。";
    }
  } else if (crop.includes("草莓") || lower.includes("strawberry")) {
    if (check.has_webbing && check.affected_part === "leaves") {
      matched.push("strawberry_spider_mite");
      preliminary = "【離線預警】高度疑似二點葉蟎（紅蜘蛛）危害。";
      emergency = "可利用清水高壓噴霧沖洗葉背，物理性降低害蟲密度。";
    }
  } else if (crop.includes("柑橘") || lower.includes("citrus") || crop.includes("柳橙")) {
    if (check.has_gummosis && check.affected_part === "stems_trunk") {
      matched.push("citrus_gummosis");
      preliminary = "【離線預警】疑似溃疡病或天牛危害導致流膠。";
      emergency = "檢查樹幹蟲孔與木屑，清除幼蟲並塗抹保護劑。";
    }
  }

  if (check.has_gummosis && check.affected_part === "stems_trunk" && !matched.length) {
    matched.push("generic_gummosis");
    preliminary = "【離線預警】疑似天牛危害或木質部潰瘍流膠病。";
    emergency = "檢查蟲孔，可物理清除幼蟲或塗抹波爾多液。";
  }

  return { preliminary_suggestion: preliminary, emergency_action: emergency, matched_rules: matched };
}

function openOfflineDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(OFFLINE_IDB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(OFFLINE_IDB_STORE)) {
        db.createObjectStore(OFFLINE_IDB_STORE);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function saveImageBlob(taskId, index, blob) {
  const db = await openOfflineDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(OFFLINE_IDB_STORE, "readwrite");
    tx.objectStore(OFFLINE_IDB_STORE).put(blob, `${taskId}:${index}`);
    tx.oncomplete = () => resolve(`${taskId}:${index}`);
    tx.onerror = () => reject(tx.error);
  });
}

async function getImageBlob(key) {
  const db = await openOfflineDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(OFFLINE_IDB_STORE, "readonly");
    const req = tx.objectStore(OFFLINE_IDB_STORE).get(key);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function deleteTaskImages(taskId, count) {
  const db = await openOfflineDb();
  const tx = db.transaction(OFFLINE_IDB_STORE, "readwrite");
  const store = tx.objectStore(OFFLINE_IDB_STORE);
  for (let i = 0; i < count; i += 1) {
    store.delete(`${taskId}:${i}`);
  }
}

function collectSelfCheckFromForm() {
  const partEl = document.querySelector('input[name="offline-affected-part"]:checked');
  return {
    has_webbing: document.getElementById("chk-webbing")?.checked || false,
    has_gummosis: document.getElementById("chk-gummosis")?.checked || false,
    has_white_powder: document.getElementById("chk-white-powder")?.checked || false,
    has_water_soaked_spots: document.getElementById("chk-water-spots")?.checked || false,
    after_rain: document.getElementById("chk-after-rain")?.checked || false,
    affected_part: partEl?.value || "leaves",
  };
}

function updateOfflineBanner() {
  const banner = document.getElementById("offline-banner");
  const identifyBtn = document.getElementById("identify-btn");
  if (!banner) return;

  const offline = isBrowserOffline() || window.useLocal === true;
  banner.classList.toggle("hidden", !offline);
  banner.textContent = offline
    ? "🟡 離線模式：已啟動田間鎖存，完成後將自動排隊上傳 AI 精準診斷"
    : "";

  if (identifyBtn && !window.identifyCompleted) {
    identifyBtn.textContent = offline ? "保存紀錄並進行離線自檢" : "開始辨識";
  }

  const pending = readOfflineQueue().filter((t) => t.sync_status === "PENDING").length;
  const syncBtn = document.getElementById("offline-sync-btn");
  if (syncBtn) {
    syncBtn.classList.toggle("hidden", pending === 0 || offline);
    syncBtn.textContent = `同步 ${pending} 筆離線任務`;
  }
}

/**
 * 保存離線任務至本地佇列
 * @param {object} params
 */
async function saveOfflineDiagnosticTask({ cropName, latitude, longitude, organFiles, selfCheck }) {
  const taskId = generateTaskId();
  const localImagePaths = [];
  let index = 0;
  for (const file of Object.values(organFiles)) {
    if (!file) continue;
    const key = await saveImageBlob(taskId, index, file);
    localImagePaths.push(key);
    index += 1;
  }
  if (!localImagePaths.length) throw new Error("請至少提供一張照片");

  const rule = evaluateOfflineRuleEngine(cropName, selfCheck);
  const task = {
    task_id: taskId,
    crop_name: cropName,
    latitude,
    longitude,
    local_image_paths: localImagePaths,
    offline_self_check: selfCheck,
    sync_status: "PENDING",
    created_at: new Date().toISOString(),
    offline_rule_hint: rule,
  };

  const queue = readOfflineQueue();
  queue.unshift(task);
  writeOfflineQueue(queue);
  updateOfflineBanner();
  return task;
}

function shouldSyncNow() {
  const wifiOnly = localStorage.getItem(LS_OFFLINE_WIFI_ONLY) === "1";
  if (!wifiOnly) return true;
  const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  if (conn && conn.type) {
    return conn.type === "wifi" || conn.type === "ethernet";
  }
  return true;
}

async function syncSingleOfflineTask(task) {
  const form = new FormData();
  form.append("task_id", task.task_id);
  form.append("crop_name", task.crop_name);
  form.append("latitude", String(task.latitude));
  form.append("longitude", String(task.longitude));
  const sc = task.offline_self_check;
  form.append("has_webbing", sc.has_webbing ? "true" : "false");
  form.append("has_gummosis", sc.has_gummosis ? "true" : "false");
  form.append("has_white_powder", sc.has_white_powder ? "true" : "false");
  form.append("has_water_soaked_spots", sc.has_water_soaked_spots ? "true" : "false");
  form.append("after_rain", sc.after_rain ? "true" : "false");
  form.append("affected_part", sc.affected_part);

  for (let i = 0; i < task.local_image_paths.length; i += 1) {
    const blob = await getImageBlob(task.local_image_paths[i]);
    if (!blob) continue;
    form.append("images", blob, `${task.task_id}__${i}.jpg`);
  }

  const res = await fetch("/api/v1/diagnostic/sync", { method: "POST", body: form });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "同步失敗");
  return data;
}

async function pollTaskUntilComplete(taskId, onUpdate) {
  for (let i = 0; i < 60; i += 1) {
    await new Promise((r) => setTimeout(r, 3000));
    const res = await fetch(`/api/v1/diagnostic/sync/${taskId}`);
    if (!res.ok) continue;
    const data = await res.json();
    onUpdate?.(data);
    if (data.sync_status === "COMPLETED" || data.sync_status === "FAILED") return data;
  }
  return null;
}

async function syncPendingOfflineTasks({ onProgress } = {}) {
  if (!shouldSyncNow()) {
    throw new Error("已設定僅 Wi-Fi 同步，請連上 Wi-Fi 或關閉此選項");
  }

  const queue = readOfflineQueue();
  const pending = queue.filter((t) => t.sync_status === "PENDING");
  const results = [];

  for (const task of pending) {
    task.sync_status = "SYNCING";
    writeOfflineQueue(queue);
    onProgress?.(`上傳中：${task.crop_name}…`);

    try {
      const data = await syncSingleOfflineTask(task);
      task.sync_status = "SYNCING";
      task.server_queued_at = data.sync_time;
      writeOfflineQueue(queue);
      results.push({ task, queued: data });

      pollTaskUntilComplete(task.task_id, (status) => {
        if (status.sync_status === "COMPLETED") {
          task.sync_status = "COMPLETED";
          task.diagnosis_result = status.diagnosis_result;
          writeOfflineQueue(queue.filter((t) => t.task_id !== task.task_id));
          deleteTaskImages(task.task_id, task.local_image_paths.length);
          onProgress?.(`✅ ${task.crop_name} AI 診斷完成`);
        } else if (status.sync_status === "FAILED") {
          task.sync_status = "FAILED";
          task.error_message = status.error_message;
          writeOfflineQueue(queue);
        }
      });
    } catch (err) {
      task.sync_status = "PENDING";
      writeOfflineQueue(queue);
      throw err;
    }
  }

  updateOfflineBanner();
  return results;
}

function renderOfflineRuleCard(rule) {
  return `<div class="offline-rule-card">
    <h4>🩺 離線自主檢查結果</h4>
    <p><strong>${rule.preliminary_suggestion}</strong></p>
    <p class="weather-hint">${rule.emergency_action}</p>
    <p class="muted">紀錄已鎖存於手機，連網後將自動上傳 Gemini 精準診斷。</p>
  </div>`;
}

function setupOfflineSyncUI() {
  window.addEventListener("online", () => {
    updateOfflineBanner();
    if (shouldSyncNow() && readOfflineQueue().some((t) => t.sync_status === "PENDING")) {
      syncPendingOfflineTasks().catch(() => {});
    }
  });
  window.addEventListener("offline", updateOfflineBanner);

  document.getElementById("offline-sync-btn")?.addEventListener("click", async () => {
    const errEl = document.getElementById("identify-error");
    try {
      await syncPendingOfflineTasks({
        onProgress: (msg) => {
          if (errEl) errEl.textContent = msg;
        },
      });
      if (errEl) errEl.textContent = "離線任務已排入雲端背景佇列";
    } catch (err) {
      if (errEl) errEl.textContent = err.message;
    }
  });

  document.getElementById("offline-wifi-only")?.addEventListener("change", (e) => {
    localStorage.setItem(LS_OFFLINE_WIFI_ONLY, e.target.checked ? "1" : "0");
  });

  const wifiChk = document.getElementById("offline-wifi-only");
  if (wifiChk) wifiChk.checked = localStorage.getItem(LS_OFFLINE_WIFI_ONLY) === "1";

  updateOfflineBanner();
}

window.OfflineSync = {
  isBrowserOffline,
  evaluateOfflineRuleEngine,
  saveOfflineDiagnosticTask,
  syncPendingOfflineTasks,
  renderOfflineRuleCard,
  collectSelfCheckFromForm,
  updateOfflineBanner,
  setupOfflineSyncUI,
};

document.addEventListener("DOMContentLoaded", setupOfflineSyncUI);
