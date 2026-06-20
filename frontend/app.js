const BASE_KNOWLEDGE = [
  {
    crop: "番茄",
    issue_type: "病害",
    issue_name: "晚疫病",
    keywords: ["tomato", "late", "blight"],
    treatment: "移除病葉，噴灑代森錳鋅或烯酰嗎啉；改善通風，避免葉面長時間潮濕。",
    prevention: "輪作、選抗病品種、避免傍晚澆水、保持株距通風。",
  },
  {
    crop: "水稻",
    issue_type: "蟲害",
    issue_name: "稻飛蝨",
    keywords: ["rice", "planthopper"],
    treatment: "田水排乾後施用吡蟲啉或噻蟲嗪；嚴重時需連續防治 2-3 次。",
    prevention: "清除田邊雜草、合理施氮、使用誘蟲板監測蟲口密度。",
  },
  {
    crop: "蘋果",
    issue_type: "病害",
    issue_name: "蘋果黑星病",
    keywords: ["apple", "scab"],
    treatment: "發病初期噴多菌靈或戊唑醇；清除落葉減少病源。",
    prevention: "冬季清園、選抗病品種、花期前後預防性噴藥。",
  },
  {
    crop: "黃瓜",
    issue_type: "病害",
    issue_name: "霜霉病",
    keywords: ["cucumber", "mildew"],
    treatment: "噴烯酰嗎啉或嘧菌酯；降低棚內濕度，增加通風。",
    prevention: "控制澆水量、避免密植、發現病葉立即移除。",
  },
  {
    crop: "玉米",
    issue_type: "蟲害",
    issue_name: "玉米螟",
    keywords: ["corn", "maize", "borer"],
    treatment: "心葉期撒施辛硫磷顆粒劑；或噴氯蟲苯甲酰胺。",
    prevention: "秋後深翻滅蛹、性誘劑誘殺成蟲、適期播種避高峰。",
  },
];

const LS_IDENT = "agri_identifications";
const LS_TRAIN = "agri_training";
const LS_KNOWLEDGE = "agri_knowledge_entries";
const LS_INDEX = "agri_knowledge_index";
const LS_APP_VERSION = "agri_app_version";
const MATCH_THRESHOLD = 0.82;

let useLocal = false;

async function clearAppCaches() {
  if ("caches" in window) {
    const keys = await caches.keys();
    await Promise.all(keys.map((key) => caches.delete(key)));
  }
  if ("serviceWorker" in navigator) {
    const regs = await navigator.serviceWorker.getRegistrations();
    await Promise.all(regs.map((reg) => reg.unregister()));
  }
}

async function registerServiceWorker(version) {
  if (!("serviceWorker" in navigator)) return;
  try {
    await navigator.serviceWorker.register(`/sw.js?v=${encodeURIComponent(version)}`, { scope: "/" });
  } catch {
    /* ignore */
  }
}

function renderAppVersion(version) {
  const el = document.getElementById("app-version");
  if (el) el.textContent = `版本 ${version}`;
}

async function ensureLatestApp() {
  try {
    const res = await fetch("/api/version", { cache: "no-store" });
    if (!res.ok) return;
    const { version } = await res.json();
    renderAppVersion(version);
    const stored = localStorage.getItem(LS_APP_VERSION);
    if (stored && stored !== version) {
      await clearAppCaches();
      localStorage.setItem(LS_APP_VERSION, version);
      const url = new URL(window.location.href);
      url.searchParams.set("v", version);
      window.location.replace(url.toString());
      return;
    }
    localStorage.setItem(LS_APP_VERSION, version);
    await registerServiceWorker(version);
  } catch {
    /* ignore */
  }
}

window.addEventListener("pageshow", (event) => {
  if (event.persisted) ensureLatestApp();
});

async function apiAvailable() {
  try {
    const res = await fetch("/api/health", { method: "GET" });
    return res.ok;
  } catch {
    return false;
  }
}

function readLocal(key) {
  return JSON.parse(localStorage.getItem(key) || "[]");
}

function writeLocal(key, data) {
  localStorage.setItem(key, JSON.stringify(data));
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function imageVectorFromDataUrl(dataUrl) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = 32;
      canvas.height = 32;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0, 32, 32);
      const data = ctx.getImageData(0, 0, 32, 32).data;
      const vector = [];
      for (let i = 0; i < data.length; i += 4) {
        vector.push(data[i] / 255, data[i + 1] / 255, data[i + 2] / 255);
      }
      resolve(vector);
    };
    img.onerror = reject;
    img.src = dataUrl;
  });
}

function similarity(a, b) {
  if (!a || !b || a.length !== b.length) return 0;
  let dist = 0;
  for (let i = 0; i < a.length; i++) dist += (a[i] - b[i]) ** 2;
  dist /= a.length;
  return Math.max(0, 1 - dist * 4);
}

function resolveAdvice(crop, issueType, issueName, treatment, prevention) {
  if (treatment?.trim() && prevention?.trim()) {
    return [treatment.trim(), prevention.trim()];
  }
  const builtin = BASE_KNOWLEDGE.find((x) => x.crop === crop && x.issue_name === issueName);
  if (builtin) {
    return [treatment?.trim() || builtin.treatment, prevention?.trim() || builtin.prevention];
  }
  if (issueType === "健康") {
    return [
      treatment?.trim() || "目前無需治療，持續觀察即可。",
      prevention?.trim() || "維持良好栽培管理與環境衛生。",
    ];
  }
  return [
    treatment?.trim() || "請依當地農會或植保人員建議，選擇核准藥劑並遵守安全間隔期。",
    prevention?.trim() || "保持田間通風、合理施肥、定期巡查，及早發現及早處理。",
  ];
}

function upsertLocalKnowledge(crop, issueType, issueName, treatment, prevention, source) {
  const entries = readLocal(LS_KNOWLEDGE);
  const key = `${crop}|${issueType}|${issueName}`;
  const idx = entries.findIndex((e) => e.key === key);
  const row = {
    key,
    crop,
    issue_type: issueType,
    issue_name: issueName,
    treatment,
    prevention,
    sample_count: idx >= 0 ? entries[idx].sample_count + 1 : 1,
    source,
    updated_at: new Date().toLocaleString("zh-TW"),
  };
  if (idx >= 0) entries[idx] = row;
  else entries.unshift(row);
  writeLocal(LS_KNOWLEDGE, entries);
}

function addLocalIndex(entry) {
  const items = readLocal(LS_INDEX);
  items.unshift(entry);
  writeLocal(LS_INDEX, items);
}

async function syncLocalTraining(record) {
  const [treatment, prevention] = resolveAdvice(
    record.crop,
    record.issue_type,
    record.issue_name,
    record.treatment,
    record.prevention
  );
  const vector = await imageVectorFromDataUrl(record.image_url);
  upsertLocalKnowledge(record.crop, record.issue_type, record.issue_name, treatment, prevention, "site_training");
  addLocalIndex({
    source_type: "training",
    source_id: record.id,
    image_url: record.image_url,
    image_vector: vector,
    crop: record.crop,
    issue_type: record.issue_type,
    issue_name: record.issue_name,
    treatment,
    prevention,
  });
}

async function syncLocalVerified(record) {
  const vector = await imageVectorFromDataUrl(record.image_url);
  upsertLocalKnowledge(
    record.crop,
    record.issue_type,
    record.issue_name,
    record.treatment,
    record.prevention,
    "site_verified"
  );
  addLocalIndex({
    source_type: "verified",
    source_id: record.id,
    image_url: record.image_url,
    image_vector: vector,
    crop: record.crop,
    issue_type: record.issue_type,
    issue_name: record.issue_name,
    treatment: record.treatment,
    prevention: record.prevention,
  });
}

async function localPredict(file) {
  const queryVector = await imageVectorFromDataUrl(await fileToDataUrl(file));
  const indexRows = readLocal(LS_INDEX);
  let best = null;
  let bestScore = 0;

  for (const row of indexRows) {
    const score = similarity(queryVector, row.image_vector);
    if (score > bestScore) {
      bestScore = score;
      best = row;
    }
  }

  if (best && bestScore >= MATCH_THRESHOLD) {
    let source = "驗收確認資料";
    if (best.source_type === "training") source = "網站訓練資料";
    if (best.source_type === "corrected") source = "手動更正資料";
    return {
      crop: best.crop,
      issue_type: best.issue_type,
      issue_name: best.issue_name,
      treatment: best.treatment,
      prevention: best.prevention,
      confidence: Math.min(0.99, 0.7 + bestScore * 0.29),
      source,
      match_score: bestScore,
    };
  }

  const entries = readLocal(LS_KNOWLEDGE);
  const hint = (file.name || "").toLowerCase();
  for (const entry of entries) {
    if (hint.includes(entry.crop.toLowerCase()) || hint.includes(entry.issue_name.toLowerCase())) {
      return {
        crop: entry.crop,
        issue_type: entry.issue_type,
        issue_name: entry.issue_name,
        treatment: entry.treatment,
        prevention: entry.prevention,
        confidence: 0.75,
        source: "網站知識庫",
      };
    }
  }

  for (const item of BASE_KNOWLEDGE) {
    if (item.keywords.some((k) => hint.includes(k))) {
      return { ...item, confidence: 0.68, source: "內建知識庫" };
    }
  }

  if (entries.length) {
    const entry = entries[0];
    return {
      crop: entry.crop,
      issue_type: entry.issue_type,
      issue_name: entry.issue_name,
      treatment: entry.treatment,
      prevention: entry.prevention,
      confidence: 0.55,
      source: "網站知識庫（低信心）",
    };
  }

  const item = BASE_KNOWLEDGE[0];
  return { ...item, confidence: 0.52, source: "內建知識庫（低信心）" };
}

function renderResultCard(data, corrected = false) {
  const source = data.source ? `<span class="source-tag">${data.source}</span>` : "";
  const correctedTag = corrected ? `<div class="corrected-badge">已手動更正並同步知識庫</div>` : "";
  return `
    <div class="result-card">
      <h3>辨識結果 ${source}</h3>
      <p><span class="badge ${badgeClass(data.issue_type)}">${data.issue_type}</span>
      信心度 ${Math.round(data.confidence * 100)}%</p>
      <p><strong>品種：</strong>${escapeHtml(data.crop)}</p>
      <p><strong>問題：</strong>${escapeHtml(data.issue_name)}</p>
      <p><strong>治療：</strong>${escapeHtml(data.treatment)}</p>
      <p><strong>預防：</strong>${escapeHtml(data.prevention)}</p>
      ${correctedTag}
    </div>`;
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderCorrectionForm(data) {
  return `
    <div class="correction-panel" id="correction-panel">
      <h4>辨識錯誤 — 手動更正</h4>
      <p class="muted">修正後會更新結果並同步至知識庫，下次上傳相似照片會優先比對。</p>
      <form id="correction-form">
        <label for="corr-crop">正確品種</label>
        <input id="corr-crop" name="crop" value="${escapeHtml(data.crop)}" required />

        <label for="corr-issue-type">問題類型</label>
        <select id="corr-issue-type" name="issue_type">
          <option value="病害" ${data.issue_type === "病害" ? "selected" : ""}>病害</option>
          <option value="蟲害" ${data.issue_type === "蟲害" ? "selected" : ""}>蟲害</option>
          <option value="健康" ${data.issue_type === "健康" ? "selected" : ""}>健康</option>
          <option value="待確認" ${data.issue_type === "待確認" ? "selected" : ""}>待確認</option>
        </select>

        <label for="corr-issue-name">正確問題名稱</label>
        <input id="corr-issue-name" name="issue_name" value="${escapeHtml(data.issue_name)}" required />

        <label for="corr-treatment">治療方式</label>
        <textarea id="corr-treatment" name="treatment">${escapeHtml(data.treatment)}</textarea>

        <label for="corr-prevention">預防方式</label>
        <textarea id="corr-prevention" name="prevention">${escapeHtml(data.prevention)}</textarea>

        <button type="submit" class="btn btn-primary">儲存更正並同步知識庫</button>
        <button type="button" id="cancel-correction" class="btn btn-secondary">取消</button>
        <div id="correction-error" class="error"></div>
      </form>
    </div>`;
}

function renderIdentifyPanel(data, corrected = false) {
  const showCorrectBtn = !corrected && data.id;
  return (
    renderResultCard(data, corrected) +
    (showCorrectBtn
      ? `<button type="button" id="show-correction" class="btn btn-danger">辨識錯誤，手動更正</button>`
      : "") +
    (showCorrectBtn ? `<div id="correction-slot"></div>` : "")
  );
}

let lastIdentifyData = null;

async function submitCorrection(recordId, formData) {
  if (!useLocal) {
    const res = await fetch(`/api/correct/${recordId}`, { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "更正失敗");
    return data;
  }

  const items = readLocal(LS_IDENT);
  const target = items.find((i) => i.id === recordId);
  if (!target) throw new Error("找不到紀錄");

  const updated = {
    ...target,
    crop: formData.get("crop"),
    issue_type: formData.get("issue_type"),
    issue_name: formData.get("issue_name"),
    treatment: formData.get("treatment") || "請依實際狀況處理。",
    prevention: formData.get("prevention") || "維持良好栽培管理。",
    confidence: 0.95,
    source: "手動更正",
    verified: 1,
  };

  writeLocal(
    LS_IDENT,
    items.map((i) => (i.id === recordId ? updated : i))
  );
  await syncLocalCorrected(updated);

  return {
    message: "已更正並同步知識庫（本機模式）",
    ...updated,
  };
}

async function syncLocalCorrected(record) {
  const vector = await imageVectorFromDataUrl(record.image_url);
  upsertLocalKnowledge(
    record.crop,
    record.issue_type,
    record.issue_name,
    record.treatment,
    record.prevention,
    "manual_correction"
  );
  addLocalIndex({
    source_type: "corrected",
    source_id: record.id,
    image_url: record.image_url,
    image_vector: vector,
    crop: record.crop,
    issue_type: record.issue_type,
    issue_name: record.issue_name,
    treatment: record.treatment,
    prevention: record.prevention,
  });
}

function bindIdentifyPanelEvents() {
  const showBtn = document.getElementById("show-correction");
  const slot = document.getElementById("correction-slot");
  if (!showBtn || !slot || !lastIdentifyData) return;

  showBtn.addEventListener("click", () => {
    slot.innerHTML = renderCorrectionForm(lastIdentifyData);
    showBtn.classList.add("hidden");

    document.getElementById("cancel-correction")?.addEventListener("click", () => {
      slot.innerHTML = "";
      showBtn.classList.remove("hidden");
    });

    document.getElementById("correction-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errEl = document.getElementById("correction-error");
      errEl.textContent = "";
      try {
        const formData = new FormData(e.target);
        const result = await submitCorrection(lastIdentifyData.id, formData);
        lastIdentifyData = { ...lastIdentifyData, ...result, id: lastIdentifyData.id };
        identifyResult.innerHTML = renderIdentifyPanel(lastIdentifyData, true);
        alert(result.message || "已更正並同步知識庫");
      } catch (err) {
        errEl.textContent = err.message;
      }
    });
  });
}

function showIdentifyResult(data, corrected = false) {
  lastIdentifyData = data;
  identifyResult.innerHTML = renderIdentifyPanel(data, corrected);
  bindIdentifyPanelEvents();
}

async function identifyPhoto(file) {
  if (!useLocal) {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/identify", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "辨識失敗");
    return data;
  }

  const image_url = await fileToDataUrl(file);
  const pred = await localPredict(file);
  const items = readLocal(LS_IDENT);
  const id = items.length ? items[0].id + 1 : 1;
  const record = {
    id,
    image_url,
    created_at: new Date().toLocaleString("zh-TW"),
    verified: null,
    ...pred,
  };
  writeLocal(LS_IDENT, [record, ...items]);
  return record;
}

async function submitTraining(formData, file) {
  if (!useLocal) {
    const res = await fetch("/api/training", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "提交失敗");
    return data;
  }

  const image_url = await fileToDataUrl(file);
  const items = readLocal(LS_TRAIN);
  const id = items.length ? items[0].id + 1 : 1;
  const record = {
    id,
    image_url,
    crop: formData.get("crop"),
    issue_type: formData.get("issue_type"),
    issue_name: formData.get("issue_name"),
    notes: formData.get("notes") || "",
    treatment: formData.get("treatment") || "",
    prevention: formData.get("prevention") || "",
    created_at: new Date().toLocaleString("zh-TW"),
  };
  writeLocal(LS_TRAIN, [record, ...items]);
  await syncLocalTraining(record);
  const entries = readLocal(LS_KNOWLEDGE).length;
  const images = readLocal(LS_INDEX).length;
  return { message: `已同步至辨識知識庫（共 ${entries} 類、${images} 張參考圖）` };
}

async function fetchTrainingList() {
  if (!useLocal) {
    const res = await fetch("/api/training");
    return res.json();
  }
  return readLocal(LS_TRAIN);
}

async function fetchKnowledge() {
  if (!useLocal) {
    const res = await fetch("/api/knowledge");
    return res.json();
  }
  const entries = readLocal(LS_KNOWLEDGE);
  return { entries, entries_count: entries.length, indexed_images: readLocal(LS_INDEX).length };
}

async function fetchIdentifications() {
  if (!useLocal) {
    const res = await fetch("/api/identifications");
    if (!res.ok) {
      throw new Error(`載入辨識紀錄失敗 (${res.status})`);
    }
    return res.json();
  }
  return readLocal(LS_IDENT);
}

async function fetchStats() {
  if (!useLocal) {
    const res = await fetch("/api/stats");
    return res.json();
  }
  const items = readLocal(LS_IDENT);
  const correct = items.filter((i) => i.verified === 1).length;
  const incorrect = items.filter((i) => i.verified === 0).length;
  const pending = items.filter((i) => i.verified == null).length;
  const reviewed = correct + incorrect;
  return {
    total: items.length,
    correct,
    incorrect,
    pending,
    accuracy: reviewed ? Math.round((correct / reviewed) * 1000) / 10 : null,
    entries: readLocal(LS_KNOWLEDGE).length,
    indexed_images: readLocal(LS_INDEX).length,
  };
}

async function verifyRecord(id, isCorrect) {
  if (!useLocal) {
    const form = new FormData();
    form.append("is_correct", String(isCorrect));
    await fetch(`/api/verify/${id}`, { method: "POST", body: form });
    return;
  }
  const items = readLocal(LS_IDENT);
  const target = items.find((item) => item.id === id);
  if (target && isCorrect) await syncLocalVerified(target);
  writeLocal(
    LS_IDENT,
    items.map((item) => (item.id === id ? { ...item, verified: isCorrect ? 1 : 0 } : item))
  );
}

function exportTrainingLocal() {
  const data = readLocal(LS_TRAIN);
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "training_manifest.json";
  a.click();
  URL.revokeObjectURL(url);
}

const tabs = document.querySelectorAll(".tab-btn");
const panels = {
  identify: document.getElementById("panel-identify"),
  training: document.getElementById("panel-training"),
  verify: document.getElementById("panel-verify"),
};

tabs.forEach((btn) => {
  btn.addEventListener("click", () => {
    tabs.forEach((b) => b.classList.remove("active"));
    Object.values(panels).forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    panels[btn.dataset.tab].classList.add("active");
    if (btn.dataset.tab === "training") loadTrainingPanel();
    if (btn.dataset.tab === "verify") loadVerifyPanel();
  });
});

function badgeClass(type) {
  if (type === "病害") return "badge-disease";
  if (type === "蟲害") return "badge-pest";
  return "badge-unknown";
}

function setupCameraDropzone(dropzone, cameraInput, onFile) {
  dropzone.addEventListener("click", () => cameraInput.click());
  cameraInput.addEventListener("change", () => {
    if (cameraInput.files[0]) onFile(cameraInput.files[0]);
    cameraInput.value = "";
  });
}

function setupUploadButton(button, input, onFile) {
  button.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    if (input.files[0]) onFile(input.files[0]);
    input.value = "";
  });
}

let identifyFile = null;
const identifyCameraInput = document.getElementById("identify-camera-input");
const identifyInput = document.getElementById("identify-input");
const identifyPreview = document.getElementById("identify-preview");
const identifyBtn = document.getElementById("identify-btn");
const identifyError = document.getElementById("identify-error");
const identifyResult = document.getElementById("identify-result");

function setIdentifyFile(file) {
  identifyFile = file;
  identifyPreview.src = URL.createObjectURL(file);
  identifyPreview.classList.remove("hidden");
  identifyBtn.disabled = false;
  identifyError.textContent = "";
}

setupCameraDropzone(
  document.getElementById("identify-dropzone"),
  identifyCameraInput,
  setIdentifyFile
);
setupUploadButton(
  document.getElementById("identify-upload-btn"),
  identifyInput,
  setIdentifyFile
);

identifyBtn.addEventListener("click", async () => {
  if (!identifyFile) return;
  identifyBtn.disabled = true;
  identifyError.textContent = "";
  identifyResult.innerHTML = "<p class='muted'>比對知識庫中...</p>";
  try {
    const data = await identifyPhoto(identifyFile);
    showIdentifyResult(data);
  } catch (err) {
    identifyError.textContent = err.message;
    identifyResult.innerHTML = "";
  } finally {
    identifyBtn.disabled = false;
  }
});

let trainingFile = null;
const trainingCameraInput = document.getElementById("training-camera-input");
const trainingInput = document.getElementById("training-input");
const trainingPreview = document.getElementById("training-preview");
const trainingError = document.getElementById("training-error");

function setTrainingFile(file) {
  trainingFile = file;
  trainingPreview.src = URL.createObjectURL(file);
  trainingPreview.classList.remove("hidden");
  trainingError.textContent = "";
}

setupCameraDropzone(
  document.getElementById("training-dropzone"),
  trainingCameraInput,
  setTrainingFile
);
setupUploadButton(
  document.getElementById("training-upload-btn"),
  trainingInput,
  setTrainingFile
);

document.getElementById("training-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!trainingFile) {
    trainingError.textContent = "請先上傳照片";
    return;
  }
  const form = new FormData(e.target);
  form.append("file", trainingFile);
  try {
    const data = await submitTraining(form, trainingFile);
    trainingError.textContent = "";
    alert(data.message);
    e.target.reset();
    trainingFile = null;
    trainingPreview.classList.add("hidden");
    loadTrainingPanel();
  } catch (err) {
    trainingError.textContent = err.message;
  }
});

document.getElementById("export-btn").addEventListener("click", () => {
  if (useLocal) exportTrainingLocal();
  else window.open("/api/training/export", "_blank");
});

async function loadTrainingPanel() {
  const [items, knowledge] = await Promise.all([fetchTrainingList(), fetchKnowledge()]);
  const entryCount = knowledge.entries?.length ?? knowledge.entries_count ?? 0;
  const imageCount = knowledge.indexed_images ?? 0;

  document.getElementById("knowledge-summary").innerHTML = `
    <div class="stat-box"><strong>${entryCount}</strong>知識類別</div>
    <div class="stat-box"><strong>${imageCount}</strong>參考影像</div>`;

  const knowledgeList = document.getElementById("knowledge-list");
  const entries = knowledge.entries || [];
  if (!entries.length) {
    knowledgeList.innerHTML = "<p class='muted'>尚無同步資料，請先提交訓練樣本</p>";
  } else {
    knowledgeList.innerHTML = entries
      .map(
        (item) => `
        <div class="list-item">
          <div></div>
          <div>
            <strong>${item.crop}</strong>
            <span class="badge ${badgeClass(item.issue_type)}">${item.issue_type}</span>
            <div>${item.issue_name} · ${item.sample_count} 筆樣本</div>
            <div class="muted">來源：${item.source || "site"} · ${item.updated_at || ""}</div>
          </div>
        </div>`
      )
      .join("");
  }

  const list = document.getElementById("training-list");
  if (!items.length) {
    list.innerHTML = "<p class='muted'>尚無訓練樣本</p>";
    return;
  }
  list.innerHTML = items
    .map(
      (item) => `
      <div class="list-item">
        <img src="${item.image_url}" alt="${item.crop}" />
        <div>
          <strong>${item.crop}</strong>
          <span class="badge ${badgeClass(item.issue_type)}">${item.issue_type}</span>
          <div>${item.issue_name}</div>
          <div class="muted">${item.notes || "無備註"} · ${item.created_at}</div>
        </div>
      </div>`
    )
    .join("");
}

async function loadVerifyPanel() {
  const statsEl = document.getElementById("stats");
  const listEl = document.getElementById("verify-list");
  try {
    const [stats, items] = await Promise.all([fetchStats(), fetchIdentifications()]);

    statsEl.innerHTML = `
    <div class="stat-box"><strong>${stats.total}</strong>總辨識數</div>
    <div class="stat-box"><strong>${stats.correct}</strong>正確</div>
    <div class="stat-box"><strong>${stats.incorrect}</strong>錯誤</div>
    <div class="stat-box"><strong>${stats.accuracy ?? "-"}${stats.accuracy != null ? "%" : ""}</strong>準確率</div>
    <div class="stat-box"><strong>${stats.entries ?? 0}</strong>知識類別</div>
    <div class="stat-box"><strong>${stats.indexed_images ?? 0}</strong>參考影像</div>`;

    if (!items.length) {
      listEl.innerHTML = "<p class='muted'>尚無辨識紀錄</p>";
      return;
    }

    listEl.innerHTML = items
      .map((item) => {
        const status =
          item.verified === 1
            ? "<span class='muted'>已標記：正確（已同步知識庫）</span>"
            : item.verified === 0
              ? "<span class='muted'>已標記：錯誤</span>"
              : `<div class="actions">
                <button class="btn btn-ok" data-id="${item.id}" data-correct="true">正確</button>
                <button class="btn btn-danger" data-id="${item.id}" data-correct="false">錯誤</button>
              </div>`;
        return `
        <div class="list-item">
          <img src="${item.image_url}" alt="${item.crop}" />
          <div>
            <strong>${item.crop}</strong>
            <span class="badge ${badgeClass(item.issue_type)}">${item.issue_type}</span>
            <div>${item.issue_name} · 信心度 ${Math.round(item.confidence * 100)}%</div>
            <div class="muted">${item.created_at}</div>
          </div>
          ${status}
        </div>`;
      })
      .join("");

    listEl.querySelectorAll("button[data-id]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await verifyRecord(Number(btn.dataset.id), btn.dataset.correct === "true");
        loadVerifyPanel();
      });
    });
  } catch (err) {
    statsEl.innerHTML = "";
    listEl.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
  }
}

(async () => {
  await ensureLatestApp();
  useLocal = !(await apiAvailable());
  const notice = document.getElementById("identify-notice");
  if (useLocal) {
    notice.innerHTML +=
      " <strong>本機模式</strong>：未連伺服器，無法使用 Gemini；訓練資料仍會存入瀏覽器。";
    return;
  }
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    if (data.gemini) {
      notice.innerHTML += " <strong>Gemini 已啟用</strong>。";
    } else {
      notice.innerHTML +=
        " <strong>Gemini 未設定</strong>：請在專案根目錄建立 `.env` 並填入 `GEMINI_API_KEY` 後重啟伺服器。";
    }
  } catch {
    /* ignore */
  }
})();
