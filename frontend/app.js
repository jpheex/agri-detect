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
const LS_REJECTIONS = "agri_knowledge_rejections";
const LS_APP_VERSION = "agri_app_version";
const MATCH_THRESHOLD = 0.82;
const STRONG_MATCH_THRESHOLD = 0.88;
const NEGATIVE_MATCH_THRESHOLD = 0.82;

const COMMUNITY_SOURCE_LABELS = {
  training: "群眾知識庫（預防訓練）",
  verified: "群眾知識庫（成果驗收）",
  corrected: "群眾知識庫（手動更正）",
};

function communitySourceLabel(sourceType) {
  return COMMUNITY_SOURCE_LABELS[sourceType] || "群眾知識庫";
}

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

function formatVersionLabel(version) {
  const raw = String(version ?? "").replace(/^v\s*/i, "").trim();
  return raw ? `版本 v ${raw}` : "版本 v —";
}

function renderAppVersion(payload) {
  const el = document.getElementById("app-version");
  if (!el) return;
  const label = typeof payload === "object" && payload?.label ? payload.label : null;
  const version = typeof payload === "object" ? payload.version : payload;
  el.textContent = label ? `版本 ${label}` : formatVersionLabel(version);
}

async function ensureLatestApp() {
  try {
    const res = await fetch("/api/version", { cache: "no-store" });
    if (!res.ok) return;
    const payload = await res.json();
    const version = payload.version;
    renderAppVersion(payload);
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

function getShareUrl() {
  const url = new URL(window.location.href);
  url.searchParams.delete("v");
  url.hash = "";
  let path = url.pathname.replace(/\/+$/, "");
  if (!path) path = "";
  return `${url.origin}${path}`;
}

function setupShareQrModal() {
  const shareBtn = document.getElementById("share-qr-btn");
  const modal = document.getElementById("qr-modal");
  const qrImage = document.getElementById("qr-image");
  const shareUrlEl = document.getElementById("qr-share-url");
  const copyBtn = document.getElementById("qr-copy-btn");
  if (!shareBtn || !modal || !qrImage || !shareUrlEl) return;

  const closeModal = () => {
    modal.classList.add("hidden");
    document.body.style.overflow = "";
  };

  const openModal = () => {
    const shareUrl = getShareUrl();
    shareUrlEl.textContent = shareUrl;
    qrImage.src = `/api/qrcode?url=${encodeURIComponent(shareUrl)}&t=${Date.now()}`;
    modal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
  };

  shareBtn.addEventListener("click", openModal);
  modal.querySelectorAll("[data-close-modal='qr']").forEach((el) => {
    el.addEventListener("click", closeModal);
  });

  copyBtn?.addEventListener("click", async () => {
    const text = getShareUrl();
    try {
      await navigator.clipboard.writeText(text);
      copyBtn.textContent = "已複製";
      setTimeout(() => {
        copyBtn.textContent = "複製連結";
      }, 1500);
    } catch {
      window.prompt("請手動複製連結", text);
    }
  });

  modal.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
  });
}

setupShareQrModal();

async function apiAvailable() {
  try {
    const res = await fetch("/api/health", { method: "GET" });
    return res.ok;
  } catch {
    return false;
  }
}

function showStorageWarning(storage) {
  const el = document.getElementById("storage-warning");
  if (!el || !storage || storage.persistent) {
    if (el) el.classList.add("hidden");
    return;
  }
  el.textContent = storage.warning || "資料可能於伺服器重啟後遺失，請改用持久化部署。";
  el.classList.remove("hidden");
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

function addLocalIndex(entry, replace = false) {
  let items = readLocal(LS_INDEX);
  if (replace) {
    items = items.filter(
      (item) => !(item.source_type === entry.source_type && item.source_id === entry.source_id)
    );
  }
  items.unshift(entry);
  writeLocal(LS_INDEX, items);
}

function normalizeLabel(value) {
  return String(value ?? "").trim().toLowerCase();
}

function matchesRejectedDiagnosis(result, rejection) {
  if (normalizeLabel(result.issue_name) === normalizeLabel(rejection.rejected_issue_name)) return true;
  return (
    normalizeLabel(result.crop) === normalizeLabel(rejection.rejected_crop) &&
    normalizeLabel(result.issue_type) === normalizeLabel(rejection.rejected_issue_type)
  );
}

function findLocalNegativeMatches(queryVector, topK = 3) {
  const rows = readLocal(LS_REJECTIONS);
  const scored = rows
    .map((row) => ({ row, score: similarity(queryVector, row.image_vector) }))
    .filter((item) => item.score >= 0.75)
    .sort((a, b) => b.score - a.score)
    .slice(0, topK);
  return scored;
}

function guardLocalAgainstRejections(result, negativeMatches, communityMatch = null) {
  const hit = negativeMatches.find(
    (item) => item.score >= NEGATIVE_MATCH_THRESHOLD && matchesRejectedDiagnosis(result, item.row)
  );
  if (!hit) {
    if (negativeMatches.length) result.negative_match_score = negativeMatches[0].score;
    return result;
  }

  const avoided = {
    crop: hit.row.rejected_crop,
    issue_type: hit.row.rejected_issue_type,
    issue_name: hit.row.rejected_issue_name,
    match_score: hit.score,
  };

  if (
    communityMatch &&
    communityMatch.match_score >= MATCH_THRESHOLD &&
    !matchesRejectedDiagnosis(communityMatch, hit.row)
  ) {
    return {
      ...communityMatch,
      source: `${communityMatch.source}（已避開已知錯誤）`,
      avoided_mistake: avoided,
    };
  }

  return {
    ...result,
    blocked_diagnosis: {
      crop: result.crop,
      issue_type: result.issue_type,
      issue_name: result.issue_name,
    },
    avoided_mistake: avoided,
    confidence: Math.min(result.confidence ?? 0.5, 0.42),
    issue_name: "待確認（與過往誤判案例相似）",
    issue_type: "待確認",
    treatment: "此影像與已知錯誤案例相似，系統已抑制原判斷。請手動更正或補充預防訓練樣本。",
    prevention: "建議重新拍攝清晰特寫，並在成果驗收提供正確標籤以協助系統學習。",
    source: "錯誤抑制（群眾驗收）",
    review_required: true,
  };
}

async function syncLocalRejected(record) {
  const vector = await imageVectorFromDataUrl(record.image_url);
  const items = readLocal(LS_REJECTIONS).filter((item) => item.source_id !== record.id);
  items.unshift({
    source_type: "verified_reject",
    source_id: record.id,
    image_url: record.image_url,
    image_vector: vector,
    rejected_crop: record.crop,
    rejected_issue_type: record.issue_type,
    rejected_issue_name: record.issue_name,
  });
  writeLocal(LS_REJECTIONS, items);
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
  const negativeMatches = findLocalNegativeMatches(queryVector);
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
    const communityResult = guardLocalAgainstRejections(
      {
        crop: best.crop,
        issue_type: best.issue_type,
        issue_name: best.issue_name,
        treatment: best.treatment,
        prevention: best.prevention,
        confidence: Math.min(0.99, 0.7 + bestScore * 0.29),
        source: communitySourceLabel(best.source_type),
        match_score: bestScore,
      },
      negativeMatches,
      {
        crop: best.crop,
        issue_type: best.issue_type,
        issue_name: best.issue_name,
        treatment: best.treatment,
        prevention: best.prevention,
        match_score: bestScore,
        source: communitySourceLabel(best.source_type),
      }
    );
    return communityResult;
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
  return guardLocalAgainstRejections(
    { ...item, confidence: 0.52, source: "內建知識庫（低信心）" },
    negativeMatches
  );
}

const LS_ADVANCED = "agri_advanced_mode";
const COMMON_CROPS = ["番茄", "水稻", "蘋果", "柑橘", "黃瓜", "玉米", "草莓", "香蕉"];

function farmerHeadline(data) {
  const crop = data.crop || "這株植物";
  if (data.issue_type === "健康" || data.issue_name === "健康") {
    return `您的 <strong>${escapeHtml(crop)}</strong> 看起來<strong>很健康</strong>`;
  }
  if (String(data.issue_name || "").includes("待確認")) {
    return `這張照片需要<strong>再確認一下</strong>`;
  }
  return `您的 <strong>${escapeHtml(crop)}</strong> 可能是 <strong>${escapeHtml(data.issue_name)}</strong>`;
}

function farmerAdviceBlock(data) {
  const health = renderHealthNotice(data);
  const weather = renderWeatherContext(data);
  const ipm = renderIpmSections(data);
  if (ipm) return `${health}${weather}${ipm}`;
  const treat = data.treatment ? `<p><strong>建議處理：</strong>${escapeHtml(data.treatment)}</p>` : "";
  const prev = data.prevention ? `<p><strong>平常注意：</strong>${escapeHtml(data.prevention)}</p>` : "";
  return `${health}${weather}<div class="farmer-advice">${treat}${prev}</div>`;
}

function renderWeather7dCard(report) {
  if (!report?.summary_7d?.days?.length) return "";
  const s = report.summary_7d;
  const stress = (report.environmental_stress || [])
    .map(
      (item) =>
        `<div class="weather-stress-item stress-${String(item.severity).toLowerCase()}">
          <strong>${escapeHtml(item.label)}</strong>
          <p>${escapeHtml(item.description)}</p>
          <p class="weather-hint">${escapeHtml(item.management_advice)}</p>
        </div>`
    )
    .join("");
  return `
    <div class="weather-7d-card">
      <h4>🌦️ 您這裡過去7天天氣</h4>
      <div class="weather-7d-stats">
        <div class="stat-box"><strong>${s.avg_temperature}°C</strong>平均溫度</div>
        <div class="stat-box"><strong>${s.avg_humidity}%</strong>平均濕度</div>
        <div class="stat-box"><strong>${s.total_precipitation_mm}mm</strong>總雨量</div>
      </div>
      <p class="muted weather-7d-flags">
        連續下雨 ${s.consecutive_rain_days} 天 · 連續高溫 ${s.consecutive_hot_days} 天 · 偏乾燥 ${s.consecutive_dry_days} 天
      </p>
      ${stress ? `<div class="weather-stress-list">${stress}</div>` : "<p class='muted'>目前環境壓力不大。</p>"}
    </div>`;
}

function renderWeatherContext(data) {
  const report = data.agri_weather_ai_proactive_warning;
  if (!report) return "";
  const card = renderWeather7dCard(report);
  const risks = (report.risk_assessments || [])
    .filter((item) => item.risk_level === "HIGH" || item.risk_level === "MEDIUM")
    .map(
      (item) =>
        `<div class="weather-risk-item weather-medium">
          <strong>病害風險：${escapeHtml(item.disease_name)}</strong>
          <p>${escapeHtml(item.trigger_reason)}</p>
        </div>`
    )
    .join("");
  return `${card}${risks ? `<div class="weather-warning-section">${risks}</div>` : ""}`;
}

function renderTechnicalDetails(data) {
  const organBlock = renderOrganAnalysis(data.organ_analysis);
  const reasoning = data.expert_reasoning
    ? `<p><strong>專家說明：</strong>${escapeHtml(data.expert_reasoning)}</p>`
    : "";
  const photoFeedback = data.photo_feedback
    ? `<p class="muted">${escapeHtml(data.photo_feedback)}</p>`
    : "";
  const extras = [
    data.source ? `<p class="muted">來源：${escapeHtml(data.source)}</p>` : "",
    data.community_match_score
      ? `<p class="muted">參考相似度：${Math.round(data.community_match_score * 100)}%</p>`
      : "",
    data.avoided_mistake
      ? `<p class="warning-text">已避開過往誤判：${escapeHtml(data.avoided_mistake.issue_name)}</p>`
      : "",
    data.scientific_name ? `<p class="muted">學名：${escapeHtml(data.scientific_name)}</p>` : "",
    organBlock,
    reasoning,
    photoFeedback,
  ]
    .filter(Boolean)
    .join("");
  if (!extras) return "";
  return `<details class="fold-details technical-details"><summary>看詳細說明</summary>${extras}</details>`;
}

function renderFeedbackSection(data, state) {
  if (!data.id) return "";
  if (state === "corrected") {
    return `<p class="verify-thanks">✅ 已記住正確答案，下次會更準，謝謝！</p>`;
  }
  if (state === "ok") {
    return `<p class="verify-thanks">✅ 已記住，謝謝！會幫大家越辨越準。</p>`;
  }
  if (state === "wrong") {
    return `<div id="correction-slot">${renderCorrectionForm(data)}</div>`;
  }
  return `
    <div class="farmer-feedback">
      <p class="farmer-feedback-prompt">這樣判斷對嗎？</p>
      <div class="farmer-actions">
        <button type="button" id="btn-verify-ok" class="btn btn-farmer-ok">✅ 正確</button>
        <button type="button" id="btn-verify-wrong" class="btn btn-farmer-bad">❌ 不對，改一下</button>
      </div>
      <div id="correction-slot"></div>
    </div>`;
}

function feedbackState(data, corrected) {
  if (corrected) return "corrected";
  if (data._feedback === "ok") return "ok";
  if (data._feedback === "wrong") return "wrong";
  return "pending";
}

function renderIpmSections(data) {
  const treatment = data.treatment_strategies;
  const prevention = data.prevention_strategies;
  if (!treatment && !prevention) return "";

  const listItems = (items) =>
    items?.length ? `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : "<p class='muted'>無</p>";

  const treatmentBlock = treatment
    ? `<div class="ipm-block ipm-treatment">
        <h4>🔴 治療方式（緊急處置）</h4>
        <p class="ipm-subtitle">生物/天然資材</p>${listItems(treatment.biological_control)}
        <p class="ipm-subtitle">安全化學防治</p>${listItems(treatment.chemical_control)}
      </div>`
    : "";

  const preventionBlock = prevention
    ? `<div class="ipm-block ipm-prevention">
        <h4>🟢 預防方式（平日保養）</h4>
        <p class="ipm-subtitle">栽培管理</p>${listItems(prevention.cultural_control)}
        <p class="ipm-subtitle">物理防治</p>${listItems(prevention.physical_control)}
      </div>`
    : "";

  const links =
    data.extension_links?.length
      ? `<div class="ipm-links"><strong>延伸資訊：</strong>${data.extension_links
          .map((raw) => {
            const href = safeExternalUrl(raw);
            if (!href) return `<span class="muted">${escapeHtml(raw)}</span>`;
            return `<a class="ext-link" href="${href}" target="_blank" rel="noopener noreferrer">${escapeHtml(href)}</a>`;
          })
          .join(" · ")}</div>`
      : "";

  const matchInfo = data.management_match?.matched
    ? `<p class="muted">IPM 知識庫命中：${escapeHtml(data.management_match.target_id)}（${Math.round((data.management_match.match_score || 0) * 100)}%）</p>`
    : "";

  const disclaimer = data.ipm_disclaimer
    ? `<p class="ipm-disclaimer">${escapeHtml(data.ipm_disclaimer)}</p>`
    : `<p class="ipm-disclaimer">本系統之藥劑推薦僅供參考，實際施藥請遵循台灣農業部最新公告之植物保護資訊系統規範，並嚴格遵守安全採收期。</p>`;

  return `<div class="ipm-section">${matchInfo}${treatmentBlock}${preventionBlock}${links}${disclaimer}</div>`;
}

function renderWeatherWarning(data) {
  const report = data.agri_weather_ai_proactive_warning;
  if (!report?.risk_assessments?.length) return "";

  const w = report.current_weather || {};
  const weatherMeta = `
    <p class="muted weather-meta">
      微氣象：${escapeHtml(w.temperature ?? "—")}°C · 濕度 ${escapeHtml(w.humidity ?? "—")}% ·
      24h 雨量 ${escapeHtml(w.rainfall_24h ?? "—")} mm · 葉面濕潤 ${escapeHtml(w.leaf_wetness_hours ?? "—")} 小時
    </p>`;

  const items = report.risk_assessments
    .map((item) => {
      const level = String(item.risk_level || "").toUpperCase();
      const cls = level === "HIGH" ? "weather-high" : level === "MEDIUM" ? "weather-medium" : "weather-low";
      const label = item.risk_level_label || item.risk_level;
      return `<div class="weather-risk-item ${cls}">
        <strong>${escapeHtml(item.disease_name)}</strong>
        <span class="weather-risk-badge">${escapeHtml(label)}</span>
        <p>${escapeHtml(item.trigger_reason)}</p>
        <p class="weather-hint">${escapeHtml(item.prevention_hint)}</p>
      </div>`;
    })
    .join("");

  return `<div class="weather-warning-section">
    <h4>🌦️ 微氣象預警（Agri-Weather AI）</h4>
    ${weatherMeta}
    ${items}
  </div>`;
}

function renderResultCard(data, corrected = false) {
  const state = feedbackState(data, corrected);
  const correctedTag = corrected ? `<div class="corrected-badge">已更新正確答案</div>` : "";
  const reviewNotice = data.review_required
    ? `<p class="warning-text">請按「不對，改一下」告訴我們正確答案。</p>`
    : "";

  return `
    <div class="result-card farmer-result">
      <h2 class="farmer-headline">${farmerHeadline(data)}</h2>
      <p class="farmer-meta"><span class="badge ${badgeClass(data.issue_type)}">${escapeHtml(data.issue_type)}</span></p>
      ${reviewNotice}
      ${farmerAdviceBlock(data)}
      ${renderTechnicalDetails(data)}
      ${correctedTag}
      ${renderFeedbackSection(data, state)}
    </div>`;
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function safeExternalUrl(url) {
  try {
    const parsed = new URL(String(url).trim());
    if (parsed.protocol === "http:" || parsed.protocol === "https:") return parsed.href;
  } catch {
    /* ignore */
  }
  return null;
}

function renderCorrectionForm(data) {
  const chips = COMMON_CROPS.map(
    (crop) =>
      `<button type="button" class="crop-chip" data-crop="${escapeHtml(crop)}">${escapeHtml(crop)}</button>`
  ).join("");
  return `
    <div class="correction-panel" id="correction-panel">
      <h4>請告訴我們正確答案</h4>
      <p class="muted">填好後系統會記住，下次大家拍照會更準。</p>
      <form id="correction-form">
        <label for="corr-crop">是什麼作物？</label>
        <div class="crop-chips">${chips}</div>
        <input id="corr-crop" class="input-large" name="crop" value="${escapeHtml(data.crop)}" required placeholder="點選上方或自行輸入" />

        <label for="corr-issue-type">問題類型</label>
        <select id="corr-issue-type" class="input-large" name="issue_type">
          <option value="病害" ${data.issue_type === "病害" ? "selected" : ""}>病害</option>
          <option value="蟲害" ${data.issue_type === "蟲害" ? "selected" : ""}>蟲害</option>
          <option value="健康" ${data.issue_type === "健康" ? "selected" : ""}>健康（沒問題）</option>
          <option value="生理障礙" ${data.issue_type === "生理障礙" ? "selected" : ""}>生理障礙</option>
        </select>

        <label for="corr-issue-name">什麼問題？</label>
        <input id="corr-issue-name" class="input-large" name="issue_name" value="${escapeHtml(data.issue_name === "待確認（與過往誤判案例相似）" ? "" : data.issue_name)}" required placeholder="例如：晚疫病、健康" />

        <details class="fold-details">
          <summary>治療／預防（可不填）</summary>
          <textarea id="corr-treatment" name="treatment" placeholder="留空由系統自動補充">${escapeHtml(data.treatment)}</textarea>
          <textarea id="corr-prevention" name="prevention" placeholder="留空由系統自動補充">${escapeHtml(data.prevention)}</textarea>
        </details>

        <button type="submit" class="btn btn-primary btn-large">儲存正確答案</button>
        <button type="button" id="cancel-correction" class="btn btn-secondary">取消</button>
        <div id="correction-error" class="error"></div>
      </form>
    </div>`;
}

function renderIdentifyPanel(data, corrected = false) {
  return renderResultCard(data, corrected);
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

  await syncLocalRejected(target);

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
    message: "已永久記錄：錯誤判斷已記住，正確答案已加入群眾知識庫（本機模式）",
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
  addLocalIndex(
    {
      source_type: "corrected",
      source_id: record.id,
      image_url: record.image_url,
      image_vector: vector,
      crop: record.crop,
      issue_type: record.issue_type,
      issue_name: record.issue_name,
      treatment: record.treatment,
      prevention: record.prevention,
    },
    true
  );
}

function bindCorrectionForm(recordId, slot, { onSuccess, onCancel } = {}) {
  slot.querySelectorAll(".crop-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const input = slot.querySelector("#corr-crop");
      if (input) input.value = chip.dataset.crop || "";
    });
  });

  slot.querySelector("#cancel-correction")?.addEventListener("click", () => {
    if (lastIdentifyData) lastIdentifyData._feedback = null;
    onCancel?.();
  });

  slot.querySelector("#correction-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = slot.querySelector("#correction-error");
    errEl.textContent = "";
    try {
      const formData = new FormData(e.target);
      const result = await submitCorrection(recordId, formData);
      alert(result.message || "已記住，謝謝！");
      onSuccess?.(result);
    } catch (err) {
      errEl.textContent = err.message;
    }
  });
}

function bindIdentifyPanelEvents() {
  if (!lastIdentifyData?.id) return;

  const okBtn = document.getElementById("btn-verify-ok");
  const wrongBtn = document.getElementById("btn-verify-wrong");

  okBtn?.addEventListener("click", async () => {
    okBtn.disabled = true;
    wrongBtn.disabled = true;
    await verifyRecord(lastIdentifyData.id, true);
    lastIdentifyData._feedback = "ok";
    showIdentifyResult(lastIdentifyData);
  });

  wrongBtn?.addEventListener("click", async () => {
    okBtn.disabled = true;
    wrongBtn.disabled = true;
    await verifyRecord(lastIdentifyData.id, false);
    lastIdentifyData._feedback = "wrong";
    showIdentifyResult(lastIdentifyData);
  });

  if (lastIdentifyData._feedback === "wrong") {
    const slot = document.getElementById("correction-slot");
    if (slot?.querySelector("#correction-form")) {
      bindCorrectionForm(lastIdentifyData.id, slot, {
        onSuccess: (result) => {
          lastIdentifyData = { ...lastIdentifyData, ...result, id: lastIdentifyData.id, _feedback: "corrected" };
          showIdentifyResult(lastIdentifyData, true);
        },
        onCancel: () => {
          lastIdentifyData._feedback = "pending";
          showIdentifyResult(lastIdentifyData);
        },
      });
    }
  }
}

function showIdentifyResult(data, corrected = false) {
  lastIdentifyData = data;
  identifyResult.innerHTML = renderIdentifyPanel(data, corrected);
  bindIdentifyPanelEvents();
  identifyResult.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

let farmLocation = null;

function formatCoordLabel(lat, lon) {
  const ns = lat >= 0 ? "N" : "S";
  const ew = lon >= 0 ? "E" : "W";
  return `GPS ${Math.abs(lat).toFixed(4)}°${ns}, ${Math.abs(lon).toFixed(4)}°${ew}`;
}

async function reverseGeocodeLabel(lat, lon) {
  try {
    const res = await fetch(
      `/api/geocode/reverse?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`,
      { cache: "no-store" }
    );
    if (!res.ok) return formatCoordLabel(lat, lon);
    const data = await res.json();
    return data.label || formatCoordLabel(lat, lon);
  } catch {
    return formatCoordLabel(lat, lon);
  }
}

function requestFarmLocation(forceRefresh = false) {
  return new Promise((resolve) => {
    if (farmLocation && !forceRefresh) {
      resolve(farmLocation);
      return;
    }
    if (!navigator.geolocation) {
      resolve(null);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const lat = pos.coords.latitude;
        const lon = pos.coords.longitude;
        const label = await reverseGeocodeLabel(lat, lon);
        farmLocation = { lat, lon, label };
        resolve(farmLocation);
      },
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 12000, maximumAge: forceRefresh ? 0 : 120000 }
    );
  });
}

async function loadWeatherSummary(cropName = "") {
  const box = document.getElementById("weather-7d-summary");
  if (!box || useLocal) return;
  const loc = await requestFarmLocation();
  if (!loc) {
    box.textContent = "請允許定位，才能顯示7天天氣";
    return;
  }
  box.innerHTML = "<p class='muted'>載入天氣中…</p>";
  try {
    const crop = cropName?.trim() || document.getElementById("user-crop")?.value?.trim() || "通用作物";
    const url = `/api/weather/summary?lat=${encodeURIComponent(loc.lat)}&lon=${encodeURIComponent(loc.lon)}&crop_name=${encodeURIComponent(crop)}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("天氣載入失敗");
    const data = await res.json();
    box.innerHTML = renderWeather7dCard(data);
  } catch (err) {
    box.textContent = err.message || "無法載入天氣";
  }
}

async function autoFillMonitorLocation(forceRefresh = false) {
  const input = document.getElementById("monitor-label");
  const statusEl = document.getElementById("monitor-gps-status");
  if (!input || useLocal) return;

  if (statusEl) statusEl.textContent = "正在讀取 GPS…";
  input.placeholder = "正在讀取 GPS 定位…";

  const loc = await requestFarmLocation(forceRefresh);
  if (!loc) {
    input.placeholder = "無法取得定位，請允許位置權限";
    if (statusEl) statusEl.textContent = "定位失敗";
    return;
  }

  input.value = loc.label || formatCoordLabel(loc.lat, loc.lon);
  input.placeholder = "";
  if (statusEl) {
    statusEl.textContent = `已定位 ${loc.lat.toFixed(4)}, ${loc.lon.toFixed(4)}`;
  }
  await loadWeatherSummary();
}

async function identifyPhotos(organFiles, userCrop) {
  if (!useLocal) {
    const form = new FormData();
    const fieldMap = {
      leaves: "file_leaves",
      flowers: "file_flowers",
      stems_trunk: "file_stems",
    };
    for (const [organ, file] of Object.entries(organFiles)) {
      if (file) form.append(fieldMap[organ], file, file.name);
    }
    if (userCrop?.trim()) form.append("user_provided_crop", userCrop.trim());
    const loc = await requestFarmLocation();
    if (loc) {
      form.append("latitude", String(loc.lat));
      form.append("longitude", String(loc.lon));
    }
    const res = await fetch("/api/identify", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "辨識失敗");
    return data;
  }

  const firstFile = Object.values(organFiles).find(Boolean);
  if (!firstFile) throw new Error("請至少提供一張照片");
  const image_url = await fileToDataUrl(firstFile);
  const pred = await localPredict(firstFile);
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
  if (target && !isCorrect) await syncLocalRejected(target);
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
  if (type === "生理障礙") return "badge-physio";
  if (type === "健康") return "badge-ok";
  return "badge-unknown";
}

function renderOrganAnalysis(organAnalysis) {
  if (!organAnalysis) return "";
  const organs = [
    ["leaves", "葉子"],
    ["flowers", "花朵"],
    ["stems_trunk", "枝條/樹幹"],
  ];
  const rows = organs
    .map(([key, label]) => {
      const item = organAnalysis[key];
      if (!item) return "";
      return `<div class="organ-result"><strong>${label}</strong>：${escapeHtml(item.observed_symptoms)}<br><span class="muted">疑似：${escapeHtml(item.suspected_issue)}</span></div>`;
    })
    .join("");
  return rows ? `<div class="organ-results">${rows}</div>` : "";
}

function renderHealthNotice(data) {
  const status = data.health_status || "";
  if (status === "健康") {
    return `<div class="health-light health-light-green">🟢 安全燈：植株<strong>健康</strong>，以下為平日保養建議。</div>`;
  }
  if (status === "疑似生理障礙") {
    return `<div class="health-light health-light-yellow">🟡 注意燈：疑似<strong>生理障礙</strong>，請先檢視灌溉、施肥與環境，而非立即用藥。</div>`;
  }
  if (status === "受病害侵襲" || status === "受蟲害危害") {
    return `<div class="health-light health-light-red">🔴 警報燈：已確診<strong>${escapeHtml(status)}</strong>，請優先執行下方緊急治療方式。</div>`;
  }
  return "";
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

const identifyOrganFiles = { leaves: null, flowers: null, stems_trunk: null };
const identifyBtn = document.getElementById("identify-btn");
const identifyResetBtn = document.getElementById("identify-reset-btn");
const identifyError = document.getElementById("identify-error");
const identifyResult = document.getElementById("identify-result");
const userCropInput = document.getElementById("user-crop");
let stopCropVoiceListening = null;
let identifyInProgress = false;
let identifyCompleted = false;

function setOrganInputsDisabled(disabled) {
  document.querySelectorAll(".organ-slot").forEach((slot) => {
    slot.querySelector(".organ-camera-input").disabled = disabled;
    slot.querySelector(".organ-upload-input").disabled = disabled;
    slot.querySelector(".organ-upload-btn").disabled = disabled;
    slot.querySelector('[data-role="dropzone"]').style.pointerEvents = disabled ? "none" : "";
    slot.style.opacity = disabled ? "0.65" : "";
  });
  if (userCropInput) userCropInput.disabled = disabled;
  const micBtn = document.getElementById("user-crop-mic");
  micBtn?.toggleAttribute("disabled", disabled);
  if (disabled) stopCropVoiceListening?.();
}

function updateIdentifyButtonState() {
  if (identifyInProgress || identifyCompleted) {
    identifyBtn.disabled = true;
    return;
  }
  const hasAny = Object.values(identifyOrganFiles).some(Boolean);
  identifyBtn.disabled = !hasAny;
}

function setIdentifyCompletedMode(completed) {
  identifyCompleted = completed;
  identifyResetBtn.classList.toggle("hidden", !completed);
  identifyBtn.classList.toggle("hidden", completed);
  setOrganInputsDisabled(completed);
  updateIdentifyButtonState();
}

function resetIdentifyPanel() {
  Object.keys(identifyOrganFiles).forEach((key) => {
    identifyOrganFiles[key] = null;
  });
  document.querySelectorAll(".organ-slot").forEach((slot) => {
    const preview = slot.querySelector(".organ-preview");
    preview.src = "";
    preview.classList.add("hidden");
    slot.querySelector('[data-role="dropzone"]').textContent = "點擊拍照";
    slot.classList.remove("has-photo");
  });
  if (userCropInput) userCropInput.value = "";
  stopCropVoiceListening?.();
  identifyResult.innerHTML = "";
  identifyError.textContent = "";
  lastIdentifyData = null;
  identifyInProgress = false;
  identifyBtn.textContent = "開始辨識";
  setIdentifyCompletedMode(false);
  setOrganInputsDisabled(false);
}

function setOrganFile(organ, file, slotEl) {
  identifyOrganFiles[organ] = file;
  const preview = slotEl.querySelector(".organ-preview");
  const dropzone = slotEl.querySelector('[data-role="dropzone"]');
  preview.src = URL.createObjectURL(file);
  preview.classList.remove("hidden");
  dropzone.textContent = "已選擇，點擊重拍";
  slotEl.classList.add("has-photo");
  identifyError.textContent = "";
  updateIdentifyButtonState();
}

function setupOrganSlot(slotEl) {
  const organ = slotEl.dataset.organ;
  const cameraInput = slotEl.querySelector(".organ-camera-input");
  const uploadInput = slotEl.querySelector(".organ-upload-input");
  const dropzone = slotEl.querySelector('[data-role="dropzone"]');
  const uploadBtn = slotEl.querySelector(".organ-upload-btn");

  dropzone.addEventListener("click", () => cameraInput.click());
  uploadBtn.addEventListener("click", () => uploadInput.click());
  cameraInput.addEventListener("change", () => {
    if (cameraInput.files[0]) setOrganFile(organ, cameraInput.files[0], slotEl);
    cameraInput.value = "";
  });
  uploadInput.addEventListener("change", () => {
    if (uploadInput.files[0]) setOrganFile(organ, uploadInput.files[0], slotEl);
    uploadInput.value = "";
  });
}

document.querySelectorAll(".organ-slot").forEach(setupOrganSlot);

identifyBtn.addEventListener("click", async () => {
  if (identifyBtn.disabled || identifyInProgress || identifyCompleted) return;

  const offlineMode =
    (window.OfflineSync && OfflineSync.isBrowserOffline()) || useLocal;

  identifyInProgress = true;
  identifyBtn.disabled = true;
  identifyBtn.textContent = offlineMode ? "保存中…" : "辨識中…";
  setOrganInputsDisabled(true);
  identifyError.textContent = "";

  if (offlineMode && window.OfflineSync) {
    identifyResult.innerHTML = "<p class='muted'>離線模式：鎖存照片與 GPS…</p>";
    try {
      const crop = userCropInput?.value?.trim();
      if (!crop) throw new Error("離線模式請填寫作物提示（例如：番茄）");
      const selfCheck = OfflineSync.collectSelfCheckFromForm();
      const loc = await requestFarmLocation();
      const task = await OfflineSync.saveOfflineDiagnosticTask({
        cropName: crop,
        latitude: loc?.lat ?? 0,
        longitude: loc?.lon ?? 0,
        organFiles: identifyOrganFiles,
        selfCheck,
      });
      identifyResult.innerHTML = OfflineSync.renderOfflineRuleCard(task.offline_rule_hint);
      identifyError.textContent = `已鎖存任務 ${task.task_id.slice(0, 8)}…，連網後將自動上傳 AI 診斷。`;
      setIdentifyCompletedMode(true);
      OfflineSync.updateOfflineBanner();
    } catch (err) {
      identifyError.textContent = err.message;
      identifyResult.innerHTML = "";
      identifyInProgress = false;
      identifyBtn.textContent = "保存紀錄並進行離線自檢";
      setOrganInputsDisabled(false);
      updateIdentifyButtonState();
    }
    return;
  }

  identifyResult.innerHTML = "<p class='muted'>AI 多部位分析中...</p>";
  try {
    const data = await identifyPhotos(identifyOrganFiles, userCropInput?.value || "");
    showIdentifyResult(data);
    setIdentifyCompletedMode(true);
  } catch (err) {
    identifyError.textContent = err.message;
    identifyResult.innerHTML = "";
    identifyInProgress = false;
    identifyBtn.textContent = "開始辨識";
    setOrganInputsDisabled(false);
    updateIdentifyButtonState();
  }
});

identifyResetBtn.addEventListener("click", resetIdentifyPanel);

const registerMonitorBtn = document.getElementById("register-monitor-btn");
const monitorLabelInput = document.getElementById("monitor-label");
const monitorListEl = document.getElementById("monitor-list");
const monitorErrorEl = document.getElementById("monitor-error");

async function loadWeatherMonitors() {
  if (!monitorListEl || useLocal) return;
  try {
    const res = await fetch("/api/weather/monitors");
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "載入失敗");
    const items = data.items || [];
    if (!items.length) {
      monitorListEl.innerHTML = "<p class='muted'>尚未訂閱任何監測點</p>";
      return;
    }
    const pushHint = data.push_configured
      ? ""
      : "<p class='muted'>伺服器尚未設定 LINE_NOTIFY_TOKEN 或 PUSH_WEBHOOK_URL，高風險僅記錄不推播。</p>";
    monitorListEl.innerHTML =
      pushHint +
      items
        .map(
          (item) => `
        <div class="monitor-item" data-id="${item.id}">
          <div class="monitor-item-meta">
            <strong>${escapeHtml(item.label || item.crop_name)}</strong>
            <div class="muted">${escapeHtml(item.crop_name)} · ${Number(item.latitude).toFixed(4)}, ${Number(item.longitude).toFixed(4)}</div>
            ${item.last_alert_at ? `<div class="muted">上次預警：${escapeHtml(item.last_high_disease || "")} · ${escapeHtml(item.last_alert_at)}</div>` : ""}
          </div>
          <button type="button" class="monitor-delete-btn" data-id="${item.id}">移除</button>
        </div>`
        )
        .join("");
    monitorListEl.querySelectorAll(".monitor-delete-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.dataset.id;
        const delRes = await fetch(`/api/weather/monitors/${id}`, { method: "DELETE" });
        if (!delRes.ok) {
          const err = await delRes.json();
          monitorErrorEl.textContent = err.detail || "移除失敗";
          return;
        }
        monitorErrorEl.textContent = "";
        loadWeatherMonitors();
      });
    });
  } catch (err) {
    monitorListEl.innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
  }
}

registerMonitorBtn?.addEventListener("click", async () => {
  if (useLocal) {
    monitorErrorEl.textContent = "本機模式無法訂閱伺服器預警";
    return;
  }
  const crop = userCropInput?.value?.trim();
  if (!crop) {
    monitorErrorEl.textContent = "請先填寫作物提示（例如：番茄）";
    return;
  }
  monitorErrorEl.textContent = "";
  registerMonitorBtn.disabled = true;
  registerMonitorBtn.textContent = "定位中…";
  try {
    const loc = farmLocation || (await requestFarmLocation());
    if (!loc) {
      throw new Error("無法取得定位，請允許瀏覽器使用位置");
    }
    if (monitorLabelInput && !monitorLabelInput.value.trim()) {
      monitorLabelInput.value = loc.label || formatCoordLabel(loc.lat, loc.lon);
    }
    const form = new FormData();
    form.append("crop_name", crop);
    form.append("latitude", String(loc.lat));
    form.append("longitude", String(loc.lon));
    const label = monitorLabelInput?.value?.trim() || loc.label || formatCoordLabel(loc.lat, loc.lon);
    form.append("label", label);
    const res = await fetch("/api/weather/monitors", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "訂閱失敗");
    await loadWeatherMonitors();
    await autoFillMonitorLocation(true);
  } catch (err) {
    monitorErrorEl.textContent = err.message;
  } finally {
    registerMonitorBtn.disabled = false;
    registerMonitorBtn.textContent = "訂閱此位置預警";
  }
});

document.getElementById("refresh-monitor-gps-btn")?.addEventListener("click", () => {
  farmLocation = null;
  autoFillMonitorLocation(true);
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
  const entryCount =
    typeof knowledge.entries === "number"
      ? knowledge.entries
      : knowledge.items?.length ?? knowledge.entries_count ?? 0;
  const imageCount = knowledge.indexed_images ?? 0;

  document.getElementById("knowledge-summary").innerHTML = `
    <div class="stat-box"><strong>${entryCount}</strong>知識類別</div>
    <div class="stat-box"><strong>${imageCount}</strong>參考影像</div>
    <div class="stat-box"><strong>${knowledge.rejections ?? 0}</strong>錯誤記憶</div>`;

  const knowledgeList = document.getElementById("knowledge-list");
  const entries = knowledge.items || (Array.isArray(knowledge.entries) ? knowledge.entries : []);
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
    <div class="stat-box"><strong>${stats.indexed_images ?? 0}</strong>參考影像</div>
    <div class="stat-box"><strong>${stats.rejections ?? 0}</strong>錯誤記憶</div>`;

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
              ? "<span class='muted'>已標記：錯誤（已記入錯誤知識庫）</span>"
              : `<div class="actions">
                <button class="btn btn-ok" data-id="${item.id}" data-correct="true">正確</button>
                <button class="btn btn-danger" data-id="${item.id}" data-correct="false">錯誤</button>
              </div>`;
        const correctBtn =
          item.verified !== 1
            ? `<button class="btn btn-secondary btn-open-correct" data-id="${item.id}">提供正確答案</button>`
            : "";
        return `
        <div class="list-item verify-item" data-id="${item.id}">
          <img src="${item.image_url}" alt="${item.crop}" />
          <div>
            <strong>${item.crop}</strong>
            <span class="badge ${badgeClass(item.issue_type)}">${item.issue_type}</span>
            <div>${item.issue_name} · 信心度 ${Math.round(item.confidence * 100)}%</div>
            <div class="muted">${item.created_at}</div>
            <div class="verify-actions">${status} ${correctBtn}</div>
            <div class="correction-slot-verify"></div>
          </div>
        </div>`;
      })
      .join("");

    listEl.querySelectorAll("button[data-correct]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await verifyRecord(Number(btn.dataset.id), btn.dataset.correct === "true");
        loadVerifyPanel();
      });
    });

    listEl.querySelectorAll(".btn-open-correct").forEach((btn) => {
      btn.addEventListener("click", () => {
        const itemEl = btn.closest(".verify-item");
        const recordId = Number(btn.dataset.id);
        const record = items.find((item) => item.id === recordId);
        const slot = itemEl?.querySelector(".correction-slot-verify");
        if (!record || !slot) return;
        slot.innerHTML = renderCorrectionForm(record);
        bindCorrectionForm(recordId, slot, {
          onSuccess: () => loadVerifyPanel(),
          onCancel: () => loadVerifyPanel(),
        });
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
  initAdvancedMode();
  const notice = document.getElementById("identify-notice");
  if (useLocal) {
    notice.innerHTML +=
      " <strong>目前離線</strong>：連上網路後辨識會更準。";
    return;
  }
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    showStorageWarning(data.storage);
  } catch {
    /* ignore */
  }
  loadWeatherMonitors();
  autoFillMonitorLocation();
  document.getElementById("user-crop")?.addEventListener("change", () => loadWeatherSummary());
  initCropVoiceInput();
  window.useLocal = useLocal;
  window.OfflineSync?.updateOfflineBanner();
})();

function initCropVoiceInput() {
  const input = document.getElementById("user-crop");
  const micBtn = document.getElementById("user-crop-mic");
  if (!input || !micBtn) return;

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    micBtn.hidden = true;
    return;
  }

  let recognition = null;
  let listening = false;

  function stopListening() {
    if (!listening) return;
    listening = false;
    micBtn.classList.remove("is-listening");
    micBtn.setAttribute("aria-pressed", "false");
    try {
      recognition?.stop();
    } catch {
      /* ignore */
    }
  }

  function startListening() {
    if (micBtn.disabled || listening) return;
    recognition = new SpeechRecognition();
    recognition.lang = "zh-TW";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.continuous = false;

    recognition.onstart = () => {
      listening = true;
      micBtn.classList.add("is-listening");
      micBtn.setAttribute("aria-pressed", "true");
    };

    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript?.trim();
      if (transcript) {
        input.value = transcript;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
    };

    recognition.onerror = (event) => {
      stopListening();
      if (event.error === "aborted" || event.error === "no-speech") return;
      const msg =
        event.error === "not-allowed"
          ? "請允許麥克風權限才能用語音輸入"
          : "語音辨識失敗，請改用手動輸入";
      if (identifyError) identifyError.textContent = msg;
    };

    recognition.onend = () => stopListening();

    try {
      recognition.start();
    } catch {
      stopListening();
    }
  }

  micBtn.addEventListener("click", () => {
    if (listening) stopListening();
    else startListening();
  });

  stopCropVoiceListening = stopListening;
}

function initAdvancedMode() {
  const toggle = document.getElementById("toggle-advanced");
  if (!toggle) return;
  const on = localStorage.getItem(LS_ADVANCED) === "1";
  document.querySelectorAll(".tab-advanced").forEach((el) => el.classList.toggle("hidden", !on));
  toggle.textContent = on ? "隱藏進階功能" : "進階（農會人員）";
  toggle.addEventListener("click", () => {
    localStorage.setItem(LS_ADVANCED, on ? "0" : "1");
    location.reload();
  });
}
