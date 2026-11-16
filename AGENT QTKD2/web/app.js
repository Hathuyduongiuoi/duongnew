/* AI301 AI Agent - Đề 04 (Hà Thuỳ Dương) - Connected to Real Backend API */

const SAMPLE_BY_NUM = {
  1: { id: "case1_thong_thuong", label: "Mẫu 1 (Chuẩn)" },
  2: { id: "case2_thieu_mau_thuan", label: "Mẫu 2 (Thiếu / Lệch)" },
  3: { id: "case3_ranh_gioi_quy_tac", label: "Mẫu 3 (Ranh giới)" },
};

const state = {
  files: [],
  selectedSampleId: "case1_thong_thuong",
  stagedId: "",
  tableOverrides: {},
  columnOverrides: {},
  canonicalTables: [],
  preferredOutput: "dashboard",
  currentScene: 0,
  lastResult: null,
};

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function esc(val) {
  if (val === null || val === undefined) return "";
  return String(val)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function linkifyCitations(escapedHtml) {
  return escapedHtml.replace(/\b(CIT-\d{3})\b/g, (m, cid) => {
    return `<button type="button" class="cit-chip" onclick="openCitationModal('${cid}')">${cid}</button>`;
  });
}

const SPARKLE_GLYPHS = ["✦", "✨", "✧", "✿", "⋆", "♡"];
const SPARKLE_COLORS = ["#f472b6", "#fb7185", "#fdba74", "#f9a8d4", "#fda4af", "#fde047"];

function spawnLiquidBubbles(x, y, count = 8) {
  if (typeof x !== "number" || typeof y !== "number") return;
  for (let i = 0; i < count; i++) {
    const b = document.createElement("span");
    b.className = "liquid-bubble";
    const size = 9 + Math.round(Math.random() * 16);
    b.style.width = `${size}px`;
    b.style.height = `${size}px`;
    b.style.left = `${x}px`;
    b.style.top = `${y}px`;
    const angle = (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.65;
    const dist = 28 + Math.random() * 54;
    b.style.setProperty("--tx", `${Math.cos(angle) * dist}px`);
    b.style.setProperty("--ty", `${Math.sin(angle) * dist - 22}px`);
    b.style.setProperty("--sc", (0.9 + Math.random() * 0.7).toFixed(2));
    b.style.setProperty("--dur", `${580 + Math.round(Math.random() * 340)}ms`);
    document.body.appendChild(b);
    setTimeout(() => b.remove(), 950);
  }
}

function spawnSparkles(x, y, count = 10) {
  if (typeof x !== "number" || typeof y !== "number") return;
  const ring = document.createElement("span");
  ring.className = "sparkle-ring";
  ring.style.left = `${x}px`;
  ring.style.top = `${y}px`;
  document.body.appendChild(ring);
  setTimeout(() => ring.remove(), 580);

  spawnLiquidBubbles(x, y, Math.max(5, Math.floor(count * 0.7)));

  for (let i = 0; i < count; i++) {
    const el = document.createElement("span");
    el.className = "sparkle-particle";
    el.textContent = SPARKLE_GLYPHS[i % SPARKLE_GLYPHS.length];
    el.style.left = `${x}px`;
    el.style.top = `${y}px`;
    el.style.color = SPARKLE_COLORS[Math.floor(Math.random() * SPARKLE_COLORS.length)];
    el.style.fontSize = `${10 + Math.random() * 9}px`;
    const angle = (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.5;
    const dist = 24 + Math.random() * 44;
    el.style.setProperty("--tx", `${Math.cos(angle) * dist}px`);
    el.style.setProperty("--ty", `${Math.sin(angle) * dist - 10}px`);
    el.style.setProperty("--rot", `${Math.round((Math.random() - 0.5) * 260)}deg`);
    el.style.setProperty("--sc", (0.85 + Math.random() * 0.6).toFixed(2));
    el.style.setProperty("--dur", `${520 + Math.round(Math.random() * 260)}ms`);
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 820);
  }
}

document.addEventListener("click", (e) => {
  const trigger = e.target.closest("button, summary, label, .cute-btn, .ios-bubble-icon, .cit-chip, .step-dot");
  if (trigger && e.clientX > 0 && e.clientY > 0) {
    spawnSparkles(e.clientX, e.clientY, trigger.id === "btnRunAgent" ? 16 : 9);
  }
});

function showToast(msg, isError = false) {
  const toast = document.createElement("div");
  toast.className = `fixed bottom-5 right-5 ${
    isError
      ? "bg-rose-100/95 text-rose-800 border-2 border-rose-300"
      : "bg-emerald-100/95 text-emerald-800 border-2 border-emerald-200"
  } shadow-xl px-4 py-2.5 rounded-2xl text-xs z-50 flex items-center space-x-2 backdrop-blur-xl`;
  toast.innerHTML = `<i class="fa-solid ${
    isError ? "fa-circle-exclamation text-rose-500" : "fa-sparkles text-pink-500"
  } text-sm"></i><span class="font-bold">${esc(msg)}</span>`;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3200);
}

function showErrorBanner(summary, detail = "") {
  const el = $("errorBanner");
  const sumEl = $("errorBannerSummary");
  const wrap = $("errorBannerDetailsWrap");
  const detEl = $("errorBannerDetail");
  if (!el) return;
  if (!summary) {
    el.classList.add("hidden");
    if (sumEl) sumEl.textContent = "";
    if (detEl) detEl.textContent = "";
    if (wrap) wrap.classList.add("hidden");
    return;
  }
  if (sumEl) sumEl.textContent = summary;
  if (detEl) detEl.textContent = detail || "";
  if (wrap) wrap.classList.toggle("hidden", !detail);
  el.classList.remove("hidden");
}

function goToScene(idx, directionHint = "", opts = {}) {
  const target = Math.max(0, Math.min(3, Number(idx)));
  const prev = state.currentScene;
  state.currentScene = target;

  let animCls = directionHint;
  if (!animCls) {
    if (target === 2) animCls = "dive";
    else if (target === 3) animCls = "unfold";
    else if (target < prev) animCls = "left";
    else animCls = "right";
  }
  const animMap = {
    right: "anim-dim-right",
    left: "anim-dim-left",
    dive: "anim-dim-dive",
    unfold: "anim-dim-unfold",
  };

  for (let i = 0; i <= 3; i++) {
    const sec = $(`scene${i}`);
    if (!sec) continue;
    sec.classList.remove("scene-active", "anim-dim-right", "anim-dim-left", "anim-dim-dive", "anim-dim-unfold");
    if (i === target) {
      sec.classList.add("scene-active", animMap[animCls] || "anim-dim-right");
    }
  }

  // Site shell (breadcrumb, menu highlight, URL, title, scroll, page sweep) lives in site.js
  if (typeof window.onSceneChanged === "function") window.onSceneChanged(target, prev, opts);
}

function swipePrevScene() {
  if (state.currentScene > 0) goToScene(state.currentScene - 1, "left");
}

function swipeNextScene() {
  const cur = state.currentScene;
  if (cur === 0) goToScene(1);
  else if (cur < 3 && state.lastResult) goToScene(cur + 1);
}

async function quickDemoSample1() {
  goToScene(1, "right");
  await sleep(260);
  await loadSampleDataset(1);
}

function openAuditDrawerFromSettings() {
  closeSettingsModal();
  goToScene(3, "unfold");
  switchTab("tabTools");
}

function switchTab(tabId) {
  document.querySelectorAll(".tab-content").forEach((el) => el.classList.remove("active"));
  const target = $(tabId);
  if (target) target.classList.add("active");

  ["tabRank", "tabProposal", "tabNorm"].forEach((id) => {
    const btn = $("btn" + id.charAt(0).toUpperCase() + id.slice(1));
    if (!btn) return;
    if (id === tabId) {
      btn.className =
        "cute-btn px-4 py-2 bg-gradient-to-r from-pink-400 via-rose-400 to-orange-300 text-white border border-white/60 rounded-2xl font-extrabold text-xs whitespace-nowrap";
    } else {
      btn.className =
        "cute-btn px-4 py-2 bg-white/65 text-slate-600 border border-white rounded-2xl font-bold text-xs whitespace-nowrap";
    }
  });
}

function toggleExportMenu(e) {
  if (e) e.stopPropagation();
  const menu = $("exportMenu");
  if (menu) menu.classList.toggle("hidden");
}

function closeExportMenu() {
  const menu = $("exportMenu");
  if (menu) menu.classList.add("hidden");
}

function openSettingsModal() {
  const m = $("settingsModal");
  if (!m) return;
  m.classList.remove("hidden");
  m.classList.add("flex");
}

function closeSettingsModal() {
  const m = $("settingsModal");
  if (!m) return;
  m.classList.remove("flex");
  m.classList.add("hidden");
}

async function applySettingsAndRun() {
  closeSettingsModal();
  await runAIAgentWorkflow();
}

function switchInputSource(src) {
  const mode = src || "file";
  $("inputPaneFile")?.classList.toggle("hidden", mode !== "file");
  $("inputPaneGsheet")?.classList.toggle("hidden", mode !== "gsheet");
  $("inputPaneLark")?.classList.toggle("hidden", mode !== "lark");

  const map = { file: "btnSrcFile", gsheet: "btnSrcGsheet", lark: "btnSrcLark" };
  Object.entries(map).forEach(([k, id]) => {
    const btn = $(id);
    if (!btn) return;
    btn.className =
      k === mode
        ? "cute-btn py-2 rounded-xl bg-white/95 text-pink-700"
        : "cute-btn py-2 rounded-xl text-slate-500";
  });
}

function toggleQuickSupplement() {
  const area = $("hitl1SupplementArea");
  const btn = $("btnToggleSup");
  if (!area || !btn) return;
  const hidden = area.classList.toggle("hidden");
  btn.textContent = hidden ? "+ Bổ sung nhanh ▾" : "- Ẩn khung bổ sung ▴";
}

function toggleLocationDetails() {
  const wrap = $("locationDetailWrapper");
  const btn = $("btnToggleLocDetails");
  if (!wrap || !btn) return;
  const hidden = wrap.classList.toggle("hidden");
  btn.innerHTML = hidden
    ? `<i class="fa-solid fa-eye"></i><span>Xem chi tiết các địa bàn ▾</span>`
    : `<i class="fa-solid fa-eye-slash"></i><span>Thu gọn chi tiết ▴</span>`;
}

function switchProposalView(view) {
  const isSurvey = view === "survey";
  $("surveyPlanView")?.classList.toggle("hidden", !isSurvey);
  $("proposalMarkdownView")?.classList.toggle("hidden", isSurvey);
  const bs = $("btnPropSurvey");
  const bm = $("btnPropMd");
  if (bs && bm) {
    bs.className = isSurvey
      ? "cute-btn px-4 py-2 rounded-2xl bg-gradient-to-r from-pink-400 via-rose-400 to-orange-300 text-white border border-white/60 text-xs font-extrabold"
      : "cute-btn px-4 py-2 rounded-2xl bg-white/65 text-slate-600 border border-white text-xs font-bold";
    bm.className = !isSurvey
      ? "cute-btn px-4 py-2 rounded-2xl bg-gradient-to-r from-pink-400 via-rose-400 to-orange-300 text-white border border-white/60 text-xs font-extrabold"
      : "cute-btn px-4 py-2 rounded-2xl bg-white/65 text-slate-600 border border-white text-xs font-bold";
  }
}

function switchAuditView(view) {
  const isTools = view === "tools";
  $("auditToolsView")?.classList.toggle("hidden", !isTools);
  $("auditRulesView")?.classList.toggle("hidden", isTools);
  const bt = $("btnAuditTools");
  const br = $("btnAuditRules");
  if (bt && br) {
    bt.className = isTools
      ? "cute-btn px-4 py-2 rounded-2xl bg-gradient-to-r from-pink-400 via-rose-400 to-orange-300 text-white border border-white/60 text-xs font-extrabold"
      : "cute-btn px-4 py-2 rounded-2xl bg-white/65 text-slate-600 border border-white text-xs font-bold";
    br.className = !isTools
      ? "cute-btn px-4 py-2 rounded-2xl bg-gradient-to-r from-pink-400 via-rose-400 to-orange-300 text-white border border-white/60 text-xs font-extrabold"
      : "cute-btn px-4 py-2 rounded-2xl bg-white/65 text-slate-600 border border-white text-xs font-bold";
  }
}

function onAgentModeChange() {
  const mode = $("agentMode").value;
  const credWrap = $("apiCredentialsWrap");
  credWrap.classList.toggle("hidden", mode === "local");
  if (mode === "gemini") $("llmModel").value = "gemini-2.5-flash";
  if (mode === "openai") $("llmModel").value = "gpt-4o-mini";
}

function setCrystalStatus(pct, kind, headline, subtitle) {
  const orb = $("crystalOrbWrap");
  const icon = $("crystalOrbIcon");
  const bar = $("crystalProgressBar");
  if (orb) {
    orb.classList.remove("is-error", "is-done");
    if (kind === "error") orb.classList.add("is-error");
    else if (kind === "done") orb.classList.add("is-done");
  }
  if (icon) {
    if (kind === "error") icon.className = "fa-solid fa-circle-exclamation text-3xl text-rose-500";
    else if (kind === "done") icon.className = "fa-solid fa-circle-check text-3xl text-emerald-500";
    else if (kind === "clean") icon.className = "fa-solid fa-broom text-3xl text-orange-500 fa-beat";
    else icon.className = "fa-solid fa-wand-magic-sparkles text-3xl text-pink-600";
  }
  if (bar && typeof pct === "number") {
    bar.style.width = `${Math.max(8, Math.min(100, pct))}%`;
    bar.className =
      kind === "error"
        ? "h-full rounded-full bg-gradient-to-r from-rose-400 to-pink-500 transition-all duration-500"
        : kind === "done"
        ? "h-full rounded-full bg-gradient-to-r from-emerald-400 to-pink-400 transition-all duration-500"
        : "h-full rounded-full bg-gradient-to-r from-pink-400 via-rose-400 to-orange-300 transition-all duration-500";
  }
  if ($("scene2Headline") && headline) $("scene2Headline").textContent = headline;
  if ($("scene2ProgressText") && subtitle) $("scene2ProgressText").textContent = subtitle;
}

function resetWorkflowUI() {
  const badge = $("workflowStatusBadge");
  if (badge) {
    badge.className = "px-3 py-1 bg-white/85 text-pink-700 rounded-full text-[11px] font-extrabold border border-white";
    badge.innerText = "Chưa chạy";
  }
  setCrystalStatus(18, "idle", "Sẵn sàng tiếp nhận dữ liệu...", "Hệ thống sẽ tự động kiểm tra và làm sạch dữ liệu.");
  $("btnScene2Next")?.classList.add("hidden");
  hideResubmitCard();
  $("outputReadyBanner")?.classList.add("hidden");
  $("statsDeepSection")?.classList.add("hidden");
}

function setPreferredOutput(mode) {
  state.preferredOutput = mode || "dashboard";
  const map = {
    dashboard: "btnOutDashboard",
    report: "btnOutReport",
    html: "btnOutHtml",
  };
  Object.entries(map).forEach(([k, btnId]) => {
    const b = $(btnId);
    if (!b) return;
    if (k === state.preferredOutput) {
      b.className =
        "cute-btn py-2 rounded-xl bg-gradient-to-r from-pink-400 to-rose-400 text-white border border-white/60";
    } else {
      b.className = "cute-btn py-2 rounded-xl bg-white/75 text-slate-600 border border-white";
    }
  });
}

function openPreferredOutput(mode, autoTriggered = false) {
  const chosen = mode || state.preferredOutput || "dashboard";
  if (state.currentScene !== 3) {
    goToScene(3, "unfold");
  }
  if (chosen === "report") {
    switchTab("tabProposal");
    switchProposalView("markdown");
    if (!autoTriggered) showToast("Đã mở Báo cáo (BC) chi tiết!");
  } else if (chosen === "html") {
    if (state.lastResult?.run_id) {
      exportHTML();
    } else if (!autoTriggered) {
      showToast("Vui lòng chạy dữ liệu xong trước khi xuất HTML!", true);
    }
  } else {
    switchTab("tabRank");
    if (!autoTriggered) showToast("Đang hiển thị Dashboard đánh giá!");
  }
}

function showResubmitCard(title, reason) {
  const card = $("resubmitCard");
  if (!card) return;
  if ($("resubmitTitle")) {
    $("resubmitTitle").innerHTML = `<i class="fa-solid fa-circle-exclamation text-rose-600"></i><span>${esc(title)}</span>`;
  }
  if ($("resubmitReason")) {
    $("resubmitReason").textContent = reason || "Dữ liệu chưa hợp lệ. Vui lòng gửi lại file CSV/XLSX hoặc link Google Sheet mới.";
  }
  if ($("resubmitFileInput")) $("resubmitFileInput").value = "";
  card.classList.remove("hidden");
}

function hideResubmitCard() {
  $("resubmitCard")?.classList.add("hidden");
}

function handleInlineResubmitFiles(event) {
  const files = Array.from(event.target.files || []);
  if (!files.length) return;
  state.files = files;
  state.selectedSampleId = "";
  state.stagedId = "";
  state.tableOverrides = {};
  state.columnOverrides = {};
  if ($("gsheetsUrl")) $("gsheetsUrl").value = "";
  if ($("larkBaseUrl")) $("larkBaseUrl").value = "";
  if ($("resubmitGsheetInput")) $("resubmitGsheetInput").value = "";
  renderUploadedFiles();
  updateSampleButtonStyles(0);
  $("activeDatasetLabel").innerText = `Gửi lại ${files.length} file mới`;
  showToast(`Đã chọn ${files.length} file mới! Đang gửi lại xử lý...`);
  runAIAgentWorkflow();
}

async function submitInlineResubmit() {
  const linkVal = ($("resubmitGsheetInput")?.value || "").trim();
  const inlineFiles = $("resubmitFileInput")?.files;
  if (inlineFiles && inlineFiles.length) {
    handleInlineResubmitFiles({ target: { files: inlineFiles } });
    return;
  }
  if (linkVal) {
    state.files = [];
    renderUploadedFiles();
    if (/larksuite\.com|feishu\.cn|\/base\//i.test(linkVal)) {
      if ($("larkBaseUrl")) $("larkBaseUrl").value = linkVal;
      switchInputSource("lark");
      await importLarkBase();
    } else {
      if ($("gsheetsUrl")) $("gsheetsUrl").value = linkVal;
      switchInputSource("gsheet");
      await importGoogleSheets();
    }
    return;
  }
  showToast("Vui lòng chọn file mới hoặc dán link Google Sheet / Lark Base ở trên!", true);
}

function handleQuickReupload(event) {
  const files = Array.from(event.target.files || []);
  if (!files.length) return;
  state.files = files;
  state.selectedSampleId = "";
  state.stagedId = "";
  state.tableOverrides = {};
  state.columnOverrides = {};
  if ($("gsheetsUrl")) $("gsheetsUrl").value = "";
  if ($("larkBaseUrl")) $("larkBaseUrl").value = "";
  renderUploadedFiles();
  updateSampleButtonStyles(0);
  $("activeDatasetLabel").innerText = `Đang gửi lại ${files.length} file mới`;
  event.target.value = "";
  showToast(`Đã nhận ${files.length} file mới! Đang xử lý...`);
  runAIAgentWorkflow();
}

function requestResubmitInput() {
  clearAllInputs();
  goToScene(1, "left");
  const dz = $("dropZone");
  if (dz) {
    dz.classList.add("ring-2", "ring-pink-400");
    setTimeout(() => dz.classList.remove("ring-2", "ring-pink-400"), 1800);
  }
  showToast("Mời bạn gửi lại File CSV/XLSX hoặc Google Sheet mới!");
}

function updateSampleButtonStyles(activeNum) {
  [1, 2, 3].forEach((n) => {
    const b = $(`btnSample${n}`);
    if (!b) return;
    if (n === activeNum) {
      b.classList.add("ring-2", "ring-offset-1", "ring-pink-400");
    } else {
      b.classList.remove("ring-2", "ring-offset-1", "ring-pink-400");
    }
  });
}

function fileKey(f) {
  return `${f.name}|${f.size}|${f.lastModified}`;
}

function renderUploadedFiles() {
  const ul = $("uploadedFileList");
  if (!ul) return;
  ul.innerHTML = state.files
    .map((f, idx) => {
      const rep = (state.fileReports || {})[fileKey(f)] || { status: "pending", text: "" };
      const cls =
        rep.status === "ok"
          ? "bg-emerald-50 border-emerald-200 text-emerald-700"
          : rep.status === "error"
          ? "bg-rose-50 border-rose-200 text-rose-700"
          : "bg-pink-50 border-pink-200 text-pink-700";
      const icon =
        rep.status === "ok"
          ? `<i class="fa-solid fa-circle-check"></i>`
          : rep.status === "error"
          ? `<i class="fa-solid fa-circle-exclamation"></i>`
          : `<i class="fa-solid fa-spinner fa-spin"></i>`;
      const text = rep.text || (rep.status === "pending" ? "AI đang đọc file..." : "");
      return `
      <li class="rounded-xl border px-2.5 py-1.5 ${cls}">
        <div class="flex items-center justify-between">
          <span class="truncate pr-2 font-bold text-slate-700">${esc(f.name)}</span>
          <button type="button" onclick="removeUploadedFile(${idx})" class="text-pink-500 hover:text-pink-700 font-extrabold">✕</button>
        </div>
        <div class="text-[10.5px] font-semibold mt-0.5 flex items-start gap-1.5">${icon}<span class="leading-snug">${esc(text)}</span></div>
      </li>`;
    })
    .join("");
}

async function inspectUploadedFiles(files) {
  state.fileReports = state.fileReports || {};
  files.forEach((f) => {
    state.fileReports[fileKey(f)] = { status: "pending", text: "" };
  });
  renderUploadedFiles();
  const cfg = { api_key: ($("apiKeyInput")?.value || "").trim(), model: ($("llmModel")?.value || "gemini-2.5-flash").trim() };
  for (const f of files) {
    const fd = new FormData();
    fd.append("files", f, f.name);
    fd.append("payload", JSON.stringify({ config: cfg }));
    try {
      const resp = await fetch("/api/inspect-inputs", { method: "POST", body: fd });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || "AI không đọc được file này.");
      const tables = (data.sheet_assignments || []).length;
      const rows = (data.sheet_assignments || []).reduce((s, a) => s + (a.row_count || 0), 0);
      const docs = Object.keys(data.document_texts || {}).length;
      const parts = [];
      if (tables) parts.push(`${tables} bảng · ${rows} dòng`);
      if (docs) parts.push(`${docs} văn bản`);
      state.fileReports[fileKey(f)] = { status: "ok", text: `AI đọc được: ${parts.join(" · ") || "nội dung hợp lệ"}` };
    } catch (err) {
      state.fileReports[fileKey(f)] = { status: "error", text: `${err.message} — hãy xóa và gửi lại file khác.` };
    }
    renderUploadedFiles();
  }
  const bad = files.filter((f) => state.fileReports[fileKey(f)]?.status === "error").length;
  if (bad) showToast(`${bad} file AI chưa đọc được. Vui lòng gửi lại file hợp lệ.`, true);
}

function removeUploadedFile(idx) {
  state.files.splice(idx, 1);
  state.stagedId = "";
  renderUploadedFiles();
  const hasLark = Boolean(($("larkBaseUrl")?.value || "").trim());
  const hasGs = Boolean(($("gsheetsUrl")?.value || "").trim());
  if (!state.files.length && !hasGs && !hasLark && !state.selectedSampleId) {
    $("activeDatasetLabel").innerText = "Chưa chọn dữ liệu";
  }
}

function clearAllInputs() {
  state.files = [];
  state.selectedSampleId = "";
  state.stagedId = "";
  state.tableOverrides = {};
  state.columnOverrides = {};
  if ($("gsheetsUrl")) $("gsheetsUrl").value = "";
  if ($("larkBaseUrl")) $("larkBaseUrl").value = "";
  if ($("fileUploadInput")) $("fileUploadInput").value = "";
  renderUploadedFiles();
  updateSampleButtonStyles(0);
  $("activeDatasetLabel").innerText = "Chưa chọn dữ liệu";
  showErrorBanner("");
  resetWorkflowUI();
  renderHitlStage3State({ conflict_gap: { hitl_required: false } });
  renderHitlBoundaryState({ evaluation: { hitl_boundary_review_recommended: false } });
}

async function loadSampleDataset(num) {
  const info = SAMPLE_BY_NUM[num];
  if (!info) return;
  state.files = [];
  renderUploadedFiles();
  if ($("gsheetsUrl")) $("gsheetsUrl").value = "";
  if ($("larkBaseUrl")) $("larkBaseUrl").value = "";
  state.selectedSampleId = info.id;
  state.stagedId = "";
  state.tableOverrides = {};
  state.columnOverrides = {};
  updateSampleButtonStyles(num);
  $("activeDatasetLabel").innerText = `Đang dùng: ${info.label}`;
  showErrorBanner("");
  await runAIAgentWorkflow();
}

function handleFileUpload(event) {
  const files = Array.from(event.target.files || []);
  if (!files.length) return;
  state.files.push(...files);
  state.selectedSampleId = "";
  state.stagedId = "";
  updateSampleButtonStyles(0);
  renderUploadedFiles();
  $("activeDatasetLabel").innerText = `Đã nạp ${state.files.length} file`;
  showToast(`Đã thêm ${files.length} file! AI đang đọc thử, sau đó bấm "Gửi dữ liệu lên xử lý".`);
  event.target.value = "";
  inspectUploadedFiles(files);
}

async function importGoogleSheets() {
  const url = ($("gsheetsUrl").value || "").trim();
  if (!url) {
    showToast("Vui lòng dán link Google Sheets hợp lệ!", true);
    return;
  }
  state.selectedSampleId = "";
  state.stagedId = "";
  updateSampleButtonStyles(0);
  $("activeDatasetLabel").innerText = "Đang tải Google Sheets...";
  showErrorBanner("");

  try {
    const fd = buildFormData();
    const resp = await fetch("/api/inspect-inputs", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) {
      resetWorkflowUI();
      goToScene(2, "dive");
      setCrystalStatus(
        35,
        "error",
        "⚠️ AI không nhận được Google Sheet",
        "Dữ liệu chưa đọc được. Vui lòng gửi lại File hoặc Link khác."
      );
      showResubmitCard(
        "AI báo lỗi khi nhận dữ liệu · Vui lòng gửi lại",
        data.error || "Không thể đọc Google Sheets."
      );
      throw new Error(data.error || "Không thể tải Google Sheets.");
    }
    hideResubmitCard();
    state.stagedId = data.staged_id;
    const sheetCount = (data.sheet_assignments || []).length;
    $("activeDatasetLabel").innerText = `Google Sheets (${sheetCount} tab)`;
    showToast(`Đã tải Google Sheets (${sheetCount} tab). Đang xử lý...`);
    await runAIAgentWorkflow();
  } catch (err) {
    showErrorBanner("Lỗi tải Google Sheets", err.message);
    showToast(err.message, true);
    $("activeDatasetLabel").innerText = "Lỗi tải Google Sheets";
  }
}

async function importLarkBase() {
  const url = ($("larkBaseUrl")?.value || "").trim();
  if (!url) {
    showToast("Vui lòng dán link Lark Base hợp lệ!", true);
    return;
  }
  state.selectedSampleId = "";
  state.stagedId = "";
  updateSampleButtonStyles(0);
  $("activeDatasetLabel").innerText = "Đang tải Lark Base...";
  showErrorBanner("");

  try {
    const fd = buildFormData();
    const resp = await fetch("/api/inspect-inputs", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) {
      resetWorkflowUI();
      goToScene(2, "dive");
      setCrystalStatus(
        35,
        "error",
        "⚠️ AI không nhận được Lark Base",
        "Không đọc được bảng Lark Base (kiểm tra App ID / Secret hoặc xuất JSON/CSV)."
      );
      showResubmitCard(
        "AI báo lỗi khi nhận Lark Base · Vui lòng kiểm tra quyền hoặc gửi File",
        data.error || "Không thể đọc Lark Base."
      );
      throw new Error(data.error || "Không thể tải Lark Base.");
    }
    hideResubmitCard();
    state.stagedId = data.staged_id;
    const sheetCount = (data.sheet_assignments || []).length;
    $("activeDatasetLabel").innerText = `Lark Base (${sheetCount} bảng)`;
    showToast(`Đã tải Lark Base (${sheetCount} bảng). Đang xử lý...`);
    await runAIAgentWorkflow();
  } catch (err) {
    showErrorBanner("Lỗi tải Lark Base", err.message);
    showToast(err.message, true);
    $("activeDatasetLabel").innerText = "Lỗi tải Lark Base";
  }
}

function toggleClarifyScope() {
  const body = $("clarifyScopeBody");
  const btn = $("btnToggleClarify");
  if (!body || !btn) return;
  const hidden = body.classList.toggle("hidden");
  btn.textContent = hidden ? "Xem lại phạm vi ▾" : "Thu gọn phạm vi ▴";
}

function updateAiClarifyPreview() {
  const el = $("aiUnderstandText");
  if (!el) return;
  const biz = ($("bizTypeInput")?.value || "").trim();
  const q = ($("userPromptInput")?.value || "").trim();
  if (biz && q) {
    el.textContent = `Bạn muốn phân tích cho mô hình "${biz}" với trọng tâm: "${q}".`;
  } else if (q) {
    el.textContent = `Trọng tâm phân tích bạn đặt ra là "${q}".`;
  } else if (biz) {
    el.textContent = `Phân tích tổng quan số liệu cho doanh nghiệp "${biz}", làm sạch và đề xuất hành động.`;
  } else {
    el.textContent = "Phân tích tổng quan dữ liệu, làm sạch và đề xuất hành động theo mục tiêu bạn chọn.";
  }
}

function collectConfig() {
  const weights = {};
  const wM = $("wMarket").value.trim();
  const wF = $("wFit").value.trim();
  const wC = $("wCap").value.trim();
  const wP = $("wComp").value.trim();
  if (wM !== "") weights.market_size = Number(wM);
  if (wF !== "") weights.product_fit = Number(wF);
  if (wC !== "") weights.deployment_capability = Number(wC);
  if (wP !== "") weights.competition = Number(wP);

  return {
    agent_mode: $("agentMode").value,
    model: ($("llmModel").value || "gemini-2.5-flash").trim(),
    api_key: ($("apiKeyInput").value || "").trim(),
    allow_local_fallback: $("allowFallback").checked,
    weights,
    min_fit_threshold: Number($("thresholdFit").value || 6.0),
    min_capability_threshold: Number($("thresholdOnsite").value || 6.0),
    conflict_variance_pct: 20.0,
    tie_margin: 0.2,
    analysis_goal: $("analysisGoalSelect")?.value || "auto",
    user_prompt: ($("userPromptInput")?.value || "").trim(),
    language: $("langSelect")?.value || "vi",
    cleaning_rules: {
      trim_whitespace: $("ruleTrim") ? $("ruleTrim").checked : true,
      drop_empty_rows: $("ruleDropEmpty") ? $("ruleDropEmpty").checked : true,
      drop_duplicates: $("ruleDropDup") ? $("ruleDropDup").checked : true,
      drop_missing_rows: $("ruleDropMissing") ? $("ruleDropMissing").checked : false,
    },
    business_context: {
      business_type: ($("bizTypeInput")?.value || "").trim(),
      extra_info: ($("bizExtraInput")?.value || "").trim(),
      clarifying_answers: {
        period: ($("clarifyPeriod")?.value || "").trim(),
        decision: ($("clarifyDecision")?.value || "").trim(),
        compare: ($("clarifyCompare")?.value || "").trim(),
        join_key: ($("clarifyJoin")?.value || "").trim(),
      },
    },
  };
}

function buildFormData(extraPayload = {}) {
  const fd = new FormData();
  state.files.forEach((f) => fd.append("files", f, f.name));
  const urls = ($("gsheetsUrl")?.value || "")
    .split(/\r?\n|,/)
    .map((u) => u.trim())
    .filter(Boolean);
  const larkUrls = ($("larkBaseUrl")?.value || "")
    .split(/\r?\n|,/)
    .map((u) => u.trim())
    .filter(Boolean);

  const payload = {
    sample_id: state.selectedSampleId,
    google_sheet_urls: urls,
    fetch_all_tabs: Boolean($("fetchAllTabs")?.checked),
    lark_base_urls: larkUrls,
    lark_app_id: ($("larkAppId")?.value || "").trim(),
    lark_app_secret: ($("larkAppSecret")?.value || "").trim(),
    lark_token: ($("larkToken")?.value || "").trim(),
    staged_id: state.stagedId,
    table_overrides: state.tableOverrides,
    column_overrides: state.columnOverrides,
    ...extraPayload,
  };
  fd.append("payload", JSON.stringify(payload));
  return fd;
}

function askUserConfirm({
  title = "❓ Xác nhận thao tác",
  message = "Bạn có muốn thực hiện thao tác này không?",
  steps = [],
  confirmText = "Đồng ý thực hiện ✓",
  cancelText = "Không, hủy",
} = {}) {
  return new Promise((resolve) => {
    const modal = $("confirmActionModal");
    const titleEl = $("confirmModalTitle");
    const msgEl = $("confirmModalMessage");
    const stepsEl = $("confirmModalSteps");
    const btnOk = $("btnConfirmOk");
    const btnCancel = $("btnConfirmCancel");
    const btnClose = $("btnConfirmClose");

    if (!modal || !btnOk || !btnCancel) {
      resolve(window.confirm(message));
      return;
    }

    if (titleEl) titleEl.textContent = title;
    if (msgEl) msgEl.textContent = message;
    if (stepsEl) {
      if (steps && steps.length) {
        stepsEl.innerHTML = steps
          .map((st, idx) => `<div class="flex items-start gap-2"><span class="px-1.5 py-0.5 rounded-full bg-pink-500 text-white font-black text-[10px] shrink-0">${idx + 1}</span><span>${escapeHtml(st)}</span></div>`)
          .join("");
        stepsEl.classList.remove("hidden");
      } else {
        stepsEl.innerHTML = "";
        stepsEl.classList.add("hidden");
      }
    }
    btnOk.textContent = confirmText;
    btnCancel.textContent = cancelText;

    const cleanup = (ans) => {
      modal.classList.add("hidden");
      modal.classList.remove("flex");
      btnOk.onclick = null;
      btnCancel.onclick = null;
      if (btnClose) btnClose.onclick = null;
      modal.onclick = null;
      resolve(ans);
    };

    btnOk.onclick = () => cleanup(true);
    btnCancel.onclick = () => cleanup(false);
    if (btnClose) btnClose.onclick = () => cleanup(false);
    modal.onclick = (e) => {
      if (e.target === modal) cleanup(false);
    };

    modal.classList.remove("hidden");
    modal.classList.add("flex");
  });
}
window.askUserConfirm = askUserConfirm;

async function runAIAgentWorkflow() {
  const urls = ($("gsheetsUrl")?.value || "").trim();
  const larkUrls = ($("larkBaseUrl")?.value || "").trim();
  if (!state.files.length && !urls && !larkUrls && !state.selectedSampleId && !state.stagedId) {
    showToast("Vui lòng chọn File (Excel/Word/JSON), dán link Google Sheets / Lark Base hoặc chọn Mẫu!", true);
    return;
  }

  const sourcesDesc = [];
  if (state.files.length) sourcesDesc.push(`${state.files.length} tệp tin tải lên`);
  if (urls) sourcesDesc.push("Link Google Sheets");
  if (larkUrls) sourcesDesc.push("Link Lark Base");
  if (state.selectedSampleId) sourcesDesc.push(`Bộ dữ liệu mẫu (${state.selectedSampleId})`);

  const okReceive = await askUserConfirm({
    title: "📥 Bước 1: Xác nhận tiếp nhận dữ liệu",
    message: `Bạn có muốn AI tiếp nhận và kiểm tra nguồn dữ liệu (${sourcesDesc.join(", ") || "đã chọn"}) không?`,
    steps: [
      "Kiểm tra định dạng File / Google Sheets / Lark Base",
      "Đọc danh sách bảng và các cột dữ liệu trước khi làm sạch",
    ],
    confirmText: "Có, tiếp nhận dữ liệu ✓",
    cancelText: "Không, để sau",
  });
  if (!okReceive) {
    showToast("Đã hủy thao tác theo yêu cầu của bạn.", false);
    return;
  }

  showErrorBanner("");
  hideResubmitCard();
  $("outputReadyBanner")?.classList.add("hidden");
  $("btnScene2Next")?.classList.add("hidden");
  goToScene(2, "dive");
  setCrystalStatus(35, "idle", "AI đang tiếp nhận dữ liệu...", "Đang kiểm tra định dạng File / Sheet bạn vừa gửi...");

  const btn = $("btnRunAgent");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i><span>Đang tiếp nhận...</span>`;
  }

  const badge = $("workflowStatusBadge");
  if (badge) {
    badge.className = "px-3 py-1 bg-pink-100 text-pink-700 rounded-full text-[11px] font-extrabold border border-pink-200";
    badge.innerText = "Đang tiếp nhận";
  }

  try {
    const fdInspect = buildFormData({ config: collectConfig() });
    const inspResp = await fetch("/api/inspect-inputs", { method: "POST", body: fdInspect });
    const inspData = await inspResp.json();
    if (!inspResp.ok) {
      setCrystalStatus(35, "error", "⚠️ Không nhận được dữ liệu hợp lệ!", "Vui lòng gửi lại File hoặc Link hợp lệ bên dưới.");
      showResubmitCard("AI báo lỗi khi nhận dữ liệu · Vui lòng gửi lại File", inspData.error);
      throw new Error(inspData.error || "Lỗi tiếp nhận dữ liệu.");
    }

    const tblCount = (inspData.tables || []).length;
    const totalRows = (inspData.tables || []).reduce((acc, t) => acc + (t.row_count || 0), 0);
    const okClean = await askUserConfirm({
      title: "🧹 Bước 2: Xác nhận làm sạch & phân tích",
      message: `Đã tiếp nhận ${tblCount} bảng dữ liệu (${totalRows} dòng). Bạn có muốn AI bắt đầu làm sạch các bước dưới đây và phân tích kết quả không?`,
      steps: [
        "Chuẩn hóa tên cột, định dạng ngày tháng và số liệu",
        "Khử trùng lặp bản ghi và phát hiện ô thiếu / bất thường",
        "Phân tích đa chiều, tính KPI và xuất Dashboard / Excel / Word",
      ],
      confirmText: "Đồng ý, làm sạch & phân tích ✓",
      cancelText: "Không, dừng lại",
    });
    if (!okClean) {
      setCrystalStatus(35, "idle", "⏸ Đã dừng theo xác nhận của bạn", "Dữ liệu chưa được làm sạch. Bạn có thể bấm chạy lại bất kỳ lúc nào.");
      if (badge) badge.innerText = "Chờ xác nhận";
      showToast("Đã dừng trước bước làm sạch theo yêu cầu của bạn.", false);
      return;
    }

    if (btn) btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i><span>Đang làm sạch & phân tích...</span>`;
    const fd = buildFormData({ config: collectConfig() });
    const [resp] = await Promise.all([fetch("/api/run", { method: "POST", body: fd }), sleep(80)]);
    const data = await resp.json();
    if (!resp.ok) {
      setCrystalStatus(35, "error", "⚠️ Không nhận được dữ liệu hợp lệ!", "Vui lòng gửi lại File hoặc Link hợp lệ bên dưới.");
      showResubmitCard("AI báo lỗi khi nhận dữ liệu · Vui lòng gửi lại File", data.error);
      throw new Error(data.error || "Lỗi thực thi dữ liệu.");
    }

    // Internal Gate 1: Nhận được OK?
    if (data.workflow_status === "FAILED_RECEIVE_DATA" || data.gate_status?.gate_failed === "RECEIVE_DATA") {
      setCrystalStatus(35, "error", "⚠️ Nhận dữ liệu chưa đạt!", "Vui lòng gửi lại File hoặc Google Sheet bên dưới.");
      await applyAgentResult(data);
      return;
    }

    if (badge) badge.innerText = "Đang làm sạch";
    setCrystalStatus(72, "clean", "🧹 Đang làm sạch & chuẩn hóa dữ liệu...", "Khử trùng bản ghi và kiểm tra độ đầy đủ...");
    await sleep(80);

    // Internal Gate 2: Làm sạch thành công?
    if (data.workflow_status === "FAILED_CLEAN_DATA" || data.gate_status?.gate_failed === "CLEAN_DATA") {
      setCrystalStatus(72, "error", "⚠️ Làm sạch dữ liệu không thành công!", "Dữ liệu lỗi hoặc thiếu cột bắt buộc. Vui lòng gửi lại File.");
      await applyAgentResult(data);
      return;
    }

    setCrystalStatus(100, "done", "✅ Đã xử lý dữ liệu thành công!", "Đang mở kết quả cho bạn...");
    $("btnScene2Next")?.classList.remove("hidden");
    const orbEl = $("crystalOrbWrap");
    if (orbEl) {
      const r = orbEl.getBoundingClientRect();
      if (r.width > 0) spawnSparkles(r.left + r.width / 2, r.top + r.height / 2, 16);
    }
    await sleep(100);
    await applyAgentResult(data);
  } catch (err) {
    if (badge) {
      badge.className = "px-3 py-1 bg-rose-100 text-rose-700 rounded-full text-[11px] font-extrabold border border-rose-200";
      badge.innerText = "Lỗi · Cần gửi lại";
    }
    showErrorBanner("Không thể xử lý dữ liệu", err.message);
    showToast(err.message, true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<i class="fa-solid fa-sparkles"></i><span>Gửi dữ liệu lên xử lý →</span>`;
    }
  }
}

async function applyAgentResult(res) {
  state.lastResult = res;

  if ($("runIdBadge")) $("runIdBadge").textContent = res.run_id || "";
  if ($("engineBadge")) $("engineBadge").textContent = res.engine_used || "";

  if (res.llm_error) {
    showErrorBanner("Đã chuyển sang chế độ xử lý nội bộ", res.llm_error);
  }

  const badge = $("workflowStatusBadge");
  const gStat = res.gate_status || {};

  // Gate 1: Nhận được OK? = Không -> Yêu cầu gửi lại
  if (res.workflow_status === "FAILED_RECEIVE_DATA" || gStat.gate_failed === "RECEIVE_DATA") {
    if (badge) {
      badge.className = "px-3 py-1 bg-rose-100 text-rose-700 rounded-full text-[11px] font-extrabold border border-rose-200";
      badge.innerText = "Lỗi nhận · Gửi lại";
    }
    showResubmitCard("AI báo lỗi khi nhận dữ liệu · Vui lòng gửi lại File", gStat.gate_error_message);
    $("outputReadyBanner")?.classList.add("hidden");
    renderAuditTab(res);
    showToast("Nhận dữ liệu thất bại! Vui lòng gửi lại File / Sheet mới.", true);
    return;
  }

  // Gate 2: Làm sạch thành công? = Không -> Báo lỗi & Yêu cầu gửi lại
  if (res.workflow_status === "FAILED_CLEAN_DATA" || gStat.gate_failed === "CLEAN_DATA") {
    if (badge) {
      badge.className = "px-3 py-1 bg-rose-100 text-rose-700 rounded-full text-[11px] font-extrabold border border-rose-200";
      badge.innerText = "Lỗi làm sạch · Gửi lại";
    }
    showResubmitCard("Làm sạch dữ liệu không thành công · Vui lòng gửi lại File", gStat.gate_error_message);
    $("outputReadyBanner")?.classList.add("hidden");
    renderQualityTab(res);
    renderAuditTab(res);
    showToast("Làm sạch dữ liệu thất bại! Vui lòng gửi lại dữ liệu.", true);
    return;
  }

  hideResubmitCard();

  if (res.workflow_status === "AWAITING_HUMAN_STAGE3") {
    $("outputReadyBanner")?.classList.add("hidden");
    if (badge) {
      badge.className = "px-3 py-1 bg-amber-100 text-amber-800 rounded-full text-[11px] font-extrabold border border-amber-200";
      badge.innerText = "Chờ xác nhận";
    }
    renderHitlStage3State(res);
    renderHitlBoundaryState({ evaluation: {} });
    renderQualityTab(res);
    renderAuditTab(res);
    renderInsufficientBanner(res);
    goToScene(3, "unfold");
    showToast("Cần bạn xác nhận phần dữ liệu thiếu / lệch ở cột bên trái!", true);
    return;
  }

  if (badge) {
    if (res.workflow_status === "COMPLETED_WITH_HITL_REVIEW") {
      badge.className = "px-3 py-1 bg-amber-100 text-amber-800 rounded-full text-[11px] font-extrabold border border-amber-200";
      badge.innerText = "Cần duyệt biên";
    } else {
      badge.className = "px-3 py-1 bg-emerald-100 text-emerald-700 rounded-full text-[11px] font-extrabold border border-emerald-200";
      badge.innerText = "Hoàn thành";
    }
  }

  $("outputReadyBanner")?.classList.remove("hidden");

  renderHitlStage3State(res);
  renderHitlBoundaryState(res);
  renderTab1Results(res);
  renderProposalAndSurvey(res);
  renderQualityTab(res);
  renderAuditTab(res);
  const topCard = $("top1Name")?.closest(".cute-glass-gradient-pink") || $("top1Name")?.closest(".cute-card");
  if (topCard) {
    const rect = topCard.getBoundingClientRect();
    if (rect.width > 0) spawnSparkles(rect.left + rect.width * 0.6, rect.top + rect.height * 0.45, 16);
  }
  openPreferredOutput(state.preferredOutput, true);
  showToast("Đã xử lý dữ liệu thành công!");
}

function syncHitlIdlePill() {
  const pill = $("hitlIdlePill");
  const c1 = $("hitlStage3Card");
  const c2 = $("hitlBoundaryCard");
  if (!pill || !c1 || !c2) return;
  const anyVisible = !c1.classList.contains("hidden") || !c2.classList.contains("hidden");
  pill.classList.toggle("hidden", anyVisible);
}

function renderHitlStage3State(res) {
  const cg = res.conflict_gap || {};
  const card = $("hitlStage3Card");
  const conflictsArea = $("hitl1ConflictsArea");
  const supArea = $("hitl1SupplementArea");

  if (!cg.hitl_required) {
    card.classList.add("hidden");
    conflictsArea.classList.add("hidden");
    conflictsArea.innerHTML = "";
    supArea.classList.add("hidden");
    syncHitlIdlePill();
    return;
  }

  card.classList.remove("hidden");
  $("hitl1Desc").innerText = cg.gate_reason || "Phát hiện thiếu dữ liệu hoặc mâu thuẫn nguồn.";
  $("btnHitl1Fix").disabled = false;
  $("btnHitl1Ignore").disabled = false;
  syncHitlIdlePill();

  const highIssues = (cg.issues || []).filter((it) => it.severity === "HIGH");
  conflictsArea.classList.remove("hidden");
  const hasMissing = highIssues.some((it) => it.issue_type === "MISSING_DATA");
  supArea.classList.toggle("hidden", !hasMissing);
  if ($("btnToggleSup")) {
    $("btnToggleSup").textContent = hasMissing ? "- Ẩn khung bổ sung ▴" : "+ Bổ sung dữ liệu thiếu ▾";
  }

  conflictsArea.innerHTML = highIssues
    .map((it) => {
      let candHtml = "";
      if (it.issue_type === "CONFLICT" && (it.candidates || []).length) {
        candHtml = it.candidates
          .map(
            (c, i) => `
            <label class="flex items-start space-x-1.5 bg-white p-1.5 rounded-xl border border-amber-200 mt-1 cursor-pointer">
              <input type="radio" name="conflict_${esc(it.issue_id)}" value="${esc(c.record_id)}" ${i === 0 ? "checked" : ""} class="mt-0.5 accent-amber-500" />
              <span><strong>[${esc(c.record_id)}]</strong> ${esc(c.value)} ${esc(c.unit || "")} — <em>${esc(c.source_name || "")}</em></span>
            </label>`
          )
          .join("");
      }
      return `
        <div class="bg-white/95 p-2.5 rounded-2xl border border-amber-200">
          <div class="font-bold text-amber-800">[${esc(it.location)}] ${esc(it.issue_type)}</div>
          <div class="text-slate-600 mt-0.5">${esc(it.description)}</div>
          ${candHtml}
        </div>`;
    })
    .join("");
}

async function resolveHITL1(action) {
  if (!state.lastResult || state.lastResult.workflow_status !== "AWAITING_HUMAN_STAGE3") {
    showToast("Hiện không có cảnh báo HITL #1 nào đang chờ.");
    return;
  }

  const acknowledgeIncomplete = action === "ignore";
  const conflictChoices = {};
  const supplemental = [];

  if (!acknowledgeIncomplete) {
    const conflicts = (state.lastResult.conflict_gap?.issues || []).filter(
      (it) => it.issue_type === "CONFLICT" && (it.candidates || []).length
    );
    conflicts.forEach((it) => {
      const picked = document.querySelector(`input[name="conflict_${it.issue_id}"]:checked`);
      if (picked) {
        conflictChoices[it.issue_id] = {
          selected_record_id: picked.value,
          rejected_record_ids: it.candidates.map((c) => c.record_id).filter((id) => id !== picked.value),
          note: "Người dùng chọn nguồn tại HITL #1",
        };
      }
    });

    const supLoc = ($("supLoc").value || "").trim();
    const supFeat = ($("supFeatures").value || "").trim();
    const supReq = ($("supOnsiteReq").value || "").trim();
    const supCap = ($("supMaxCap").value || "").trim();
    if (supLoc) {
      if (supFeat || supReq !== "") {
        supplemental.push({
          location: supLoc,
          table_name: "customer_feedback",
          required_features: supFeat
            .split(/[;|,]+/)
            .map((x) => x.trim())
            .filter(Boolean),
          onsite_support_required_score: supReq !== "" ? Number(supReq) : null,
          source_name: "Bổ sung HITL #1",
        });
      }
      if (supCap !== "") {
        supplemental.push({
          location: supLoc,
          table_name: "deployment_capability",
          max_onsite_capacity: Number(supCap),
          source_name: "Bổ sung HITL #1",
        });
      }
    }
  }

  try {
    const resp = await fetch("/api/hitl/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_id: state.lastResult.run_id,
        human_resolutions: {
          conflict_choices: conflictChoices,
          supplemental_data: supplemental,
          acknowledge_incomplete: acknowledgeIncomplete,
        },
      }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Lỗi xử lý HITL #1.");
    await applyAgentResult(data);
  } catch (err) {
    showErrorBanner(err.message);
    showToast(err.message, true);
  }
}

function renderHitlBoundaryState(res) {
  const ev = res.evaluation || {};
  const card = $("hitlBoundaryCard");
  const noteInput = $("hitl2Note");

  if (!ev.hitl_boundary_review_recommended) {
    card.classList.add("hidden");
    noteInput.classList.add("hidden");
    syncHitlIdlePill();
    return;
  }

  card.classList.remove("hidden");
  syncHitlIdlePill();
  const msgs = [];
  if (ev.near_tie_alert) msgs.push(ev.near_tie_alert);
  (ev.evaluations || []).forEach((item) => {
    if ((item.boundary_flags || []).length && !ev.near_tie_alert) msgs.push(...item.boundary_flags);
  });
  if (!msgs.length && (ev.conditions_to_supplement || []).length) msgs.push(...ev.conditions_to_supplement);

  $("hitl2Desc").innerText = msgs.join(" | ");
  noteInput.classList.remove("hidden");
  $("btnHitl2Approve").disabled = false;
  $("btnHitl2Override").disabled = false;
}

async function resolveHITL2(action) {
  if (!state.lastResult || !state.lastResult.evaluation?.hitl_boundary_review_recommended) {
    showToast("Không có cảnh báo ranh giới nào đang chờ duyệt.");
    return;
  }
  const decision = action === "approve" ? "APPROVED_AGENT_TOP_2" : "OVERRIDE_STRATEGIC_CHOICE";
  const note = ($("hitl2Note").value || "").trim() || (action === "approve" ? "Trưởng phòng phê duyệt Top 2" : "Trưởng phòng điều chỉnh lựa chọn");
  try {
    const resp = await fetch("/api/hitl/boundary-signoff", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_id: state.lastResult.run_id,
        decision,
        note,
      }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Không thể lưu phê duyệt.");
    state.lastResult = data;
    if ($("workflowStatusBadge")) {
      $("workflowStatusBadge").className = "px-3 py-1 bg-emerald-100 text-emerald-700 rounded-full text-[11px] font-bold border border-emerald-200";
      $("workflowStatusBadge").innerText = "Đã duyệt";
    }
    $("hitlBoundaryCard")?.classList.add("hidden");
    syncHitlIdlePill();
    renderAuditTab(data);
    showToast("Đã ghi nhận quyết định phê duyệt!");
  } catch (err) {
    showToast(err.message, true);
  }
}

function renderInsufficientBanner(res) {
  $("top1Name").innerText = "Chờ xác nhận";
  $("top1Score").innerText = "Tạm dừng";
  $("top1Reason").innerText = res.conflict_gap?.gate_reason || "Cần xác nhận dữ liệu thiếu / lệch.";

  $("top2Name").innerText = "Chưa xếp hạng";
  $("top2Score").innerText = "--/10";
  $("top2Reason").innerText = "Chọn nguồn đúng hoặc bổ sung dữ liệu ở cột trái.";

  const chipsBox = $("agentAlertChips");
  const issues = (res.conflict_gap?.issues || []).filter((i) => i.severity === "HIGH");
  chipsBox.innerHTML = issues
    .map(
      (i) =>
        `<span class="px-2.5 py-0.5 bg-amber-100 text-amber-800 border border-amber-200 rounded-full text-[10px] font-bold">⚠️ ${esc(i.location)}: ${esc(i.issue_type)}</span>`
    )
    .join("");
  $("dataConfidence").innerText = "Chờ duyệt";
  $("citationCountLabel").innerText = `${res.audit?.summary?.total_citations || 0} nguồn`;

  $("comparisonTableBody").innerHTML = `<tr><td colspan="7" class="p-8 text-center text-amber-800 font-semibold bg-amber-50/70">Vui lòng xác nhận trong khung <strong>Xác nhận dữ liệu thiếu / lệch</strong> ở cột trái (hoặc gửi lại file mới).</td></tr>`;
  $("locationDetailCards").innerHTML = "";
}

function fmtNumStat(val) {
  if (val === null || val === undefined || val === "") return "-";
  const num = Number(val);
  if (Number.isNaN(num)) return esc(String(val));
  return Math.abs(num - Math.round(num)) < 1e-6
    ? Math.round(num).toLocaleString("vi-VN")
    : num.toLocaleString("vi-VN", { maximumFractionDigits: 2 });
}

function renderCompanyStatisticsDashboard(res) {
  const cs = res.company_stats || {};
  const numStats = cs.numeric_highlights || [];
  const catStats = cs.category_highlights || [];
  const tableSummaries = cs.table_summaries || [];
  const kvTables = tableSummaries.filter((t) => t.is_kv);
  const docTexts = cs.document_texts || [];
  const totalTables = cs.total_tables || tableSummaries.length || 0;
  const totalRows = cs.total_rows_clean || 0;
  const compPct = cs.completeness_pct !== undefined ? cs.completeness_pct : 100;

  $("top1Name").innerText = `${fmtNumStat(totalRows)} dòng sạch`;
  $("top1Score").innerText = `${compPct}% đủ`;
  $("top1Reason").innerText =
    `${totalTables} bảng thống kê · ${docTexts.length} tài liệu Word · đã loại ${cs.dedup_dropped_count || 0} bản ghi trùng.`;

  if (numStats[0]) {
    $("top2Name").innerText = numStats[0].column;
    $("top2Score").innerText = `Σ ${fmtNumStat(numStats[0].sum)}`;
    $("top2Reason").innerText = `TB: ${fmtNumStat(numStats[0].avg)} · Trung vị ${fmtNumStat(numStats[0].median)} · Min ${fmtNumStat(numStats[0].min)} → Max ${fmtNumStat(numStats[0].max)} (${numStats[0].table})`;
  } else if (catStats[0] && (catStats[0].top_values || [])[0]) {
    const tv = catStats[0].top_values[0];
    $("top2Name").innerText = tv.value;
    $("top2Score").innerText = `${tv.pct}%`;
    $("top2Reason").innerText = `Nhóm nổi bật trong "${catStats[0].column}" (${tv.count} bản ghi · ${catStats[0].table})`;
  } else if (kvTables[0] && (kvTables[0].kv_metrics || [])[0]) {
    const km = kvTables[0].kv_metrics[0];
    $("top2Name").innerText = km.label;
    $("top2Score").innerText = km.value;
    $("top2Reason").innerText = `Chỉ tiêu trích từ văn bản: ${kvTables[0].source_file}`;
  } else if (docTexts[0]) {
    $("top2Name").innerText = docTexts[0].source_file || "Tài liệu văn bản";
    $("top2Score").innerText = `${docTexts[0].paragraph_count || 0} đoạn`;
    $("top2Reason").innerText = (docTexts[0].paragraphs || ["Đã trích xuất nội dung văn bản."])[0];
  } else {
    $("top2Name").innerText = "Thống kê tổng hợp";
    $("top2Score").innerText = `${totalTables} bảng`;
    $("top2Reason").innerText = "Sẵn sàng xem bảng chỉ số và báo cáo chi tiết.";
  }

  // Override KPI #1/#2 smartly if Financial or Project KPI summary dominates
  if (cs.financial_summary && cs.financial_summary.total_revenue !== null) {
    const fs = cs.financial_summary;
    $("top1Name").innerText = `Thu: ${fmtNumStat(fs.total_revenue)}`;
    $("top1Score").innerText = fs.margin_pct !== null ? `Biên ${fs.margin_pct}%` : `${totalTables} bảng`;
    $("top1Reason").innerText = fs.net_profit !== null
      ? `Lợi nhuận ròng: ${fmtNumStat(fs.net_profit)} · Tổng chi: ${fmtNumStat(fs.total_cost)} (${compPct}% đủ liệu).`
      : `${cs.domain_label || "Thống kê tài chính"} (${totalRows} dòng sạch).`;
  } else if (cs.project_summary) {
    const ps = cs.project_summary;
    $("top1Name").innerText = `${ps.total_projects} dự án / KPI`;
    $("top1Score").innerText = ps.avg_progress_pct !== null ? `${ps.avg_progress_pct}%` : `${ps.completed_count} xong`;
    $("top1Reason").innerText = `Hoàn thành: ${ps.completed_count} · Đúng hạn: ${ps.on_track_count} · Rủi ro/Chậm: ${ps.at_risk_count}.`;
  }

  // Deep KPI / MG Tree + Priority Classifiers Section
  $("statsDeepSection")?.classList.remove("hidden");
  if ($("domainDetectedPill")) $("domainDetectedPill").innerText = cs.domain_label || "Đa chiều";

  const insightsCard = $("llmInsightsCard");
  const insightsText = $("llmInsightsText");
  const promptHits = (cs.prompt_matches || [])
    .slice(0, 6)
    .map((m) => `• ${m.row_label} (${m.table}): ${m.reason}`)
    .join("\n");
  const combinedInsight = [cs.llm_narrative, cs.prompt_note, promptHits].filter(Boolean).join("\n");
  if (insightsCard && insightsText) {
    if (combinedInsight) {
      insightsCard.classList.remove("hidden");
      insightsText.innerText = combinedInsight;
    } else {
      insightsCard.classList.add("hidden");
    }
  }

  const kt = cs.kpi_tree || {};
  if ($("kpiTreeGoal")) $("kpiTreeGoal").innerText = kt.goal_name || cs.domain_label || "Cây KPI / MG";
  if ($("kpiTreeBranches")) {
    const branches = kt.branches || [];
    $("kpiTreeBranches").innerHTML = branches.length
      ? branches
          .map((br) => {
            const stCls =
              br.status === "RISK"
                ? "bg-rose-100 text-rose-700 border-rose-200"
                : br.status === "WATCH"
                ? "bg-amber-100 text-amber-800 border-amber-200"
                : "bg-emerald-100 text-emerald-700 border-emerald-200";
            const stLbl = br.status === "RISK" ? "Rủi ro" : br.status === "WATCH" ? "Theo dõi" : "Đạt tốt";
            const chHtml = (br.children || [])
              .map(
                (ch) => `
              <li class="flex items-center justify-between gap-2 text-[11px] bg-white/70 px-2.5 py-1.5 rounded-xl border border-white">
                <span class="text-slate-700 font-semibold truncate">${esc(ch.label)}</span>
                <span class="font-extrabold text-pink-700 shrink-0">${esc(String(ch.value))}</span>
              </li>`
              )
              .join("");
            return `
              <div class="p-3.5 rounded-2xl bg-white/70 border border-white shadow-sm space-y-2">
                <div class="flex items-center justify-between gap-2">
                  <div>
                    <div class="text-xs font-extrabold text-slate-800">${esc(br.name)}</div>
                    <div class="text-[10px] font-bold text-slate-500">${esc(br.owner || "")} · ${esc(br.summary || "")}</div>
                  </div>
                  <span class="px-2 py-0.5 border rounded-full text-[10px] font-extrabold shrink-0 ${stCls}">${stLbl}</span>
                </div>
                <ul class="space-y-1">${chHtml}</ul>
              </div>`;
          })
          .join("")
      : `<div class="col-span-2 text-xs text-slate-500 font-semibold">Chưa có nhánh KPI số lượng cho tài liệu này.</div>`;
  }

  if ($("priorityEntitiesGrid")) {
    const pes = cs.priority_entities || [];
    $("priorityEntitiesGrid").innerHTML = pes.length
      ? pes
          .slice(0, 12)
          .map((pe) => {
            const tierCls = pe.tier.includes("Nhóm A")
              ? "bg-pink-100 text-pink-800 border-pink-200"
              : pe.tier.includes("Nhóm B")
              ? "bg-orange-100 text-orange-800 border-orange-200"
              : "bg-slate-100 text-slate-600 border-slate-200";
            return `
              <div class="flex items-center justify-between gap-2 p-2.5 rounded-2xl bg-white/75 border border-white text-xs">
                <div class="flex items-center space-x-2 min-w-0">
                  <span class="w-6 h-6 rounded-full bg-pink-200 text-pink-800 font-extrabold text-[10px] flex items-center justify-center shrink-0">#${pe.rank}</span>
                  <div class="min-w-0">
                    <div class="font-extrabold text-slate-800 truncate">${esc(pe.name)}</div>
                    <div class="text-[10px] text-slate-500 font-semibold truncate">${esc(pe.metric_label)}: ${fmtNumStat(pe.value)} (${pe.share_pct}%)${pe.group_label ? " · " + esc(pe.group_label) : ""}</div>
                  </div>
                </div>
                <span class="px-2 py-0.5 rounded-full border text-[10px] font-extrabold shrink-0 ${tierCls}">${esc(pe.tier)}</span>
              </div>`;
          })
          .join("")
      : `<div class="text-xs text-slate-500 font-semibold p-2">Không có cột đối tượng + số liệu để xếp hạng ưu tiên ABC.</div>`;
  }

  if ($("classifiersGrid")) {
    const cls = cs.classifiers || [];
    $("classifiersGrid").innerHTML = cls.length
      ? cls
          .map((cl) => {
            const pills = (cl.groups || [])
              .map(
                (g) =>
                  `<span class="px-2.5 py-1 rounded-xl bg-white/85 border border-pink-100 text-[11px] font-bold text-slate-700">${esc(g.label)}: <strong class="text-pink-700">${g.count}</strong> (${g.share_pct}%)</span>`
              )
              .join("");
            return `
              <div class="p-3 rounded-2xl bg-white/65 border border-white space-y-1.5">
                <div class="flex justify-between items-center text-xs">
                  <strong class="text-slate-800">${esc(cl.group_name)}</strong>
                  <span class="text-[10px] font-bold text-orange-700">${cl.total_items} mục</span>
                </div>
                <div class="flex flex-wrap gap-1.5">${pills}</div>
              </div>`;
          })
          .join("")
      : `<div class="text-xs text-slate-500 font-semibold p-2">Chưa có chiều phân nhóm danh mục trong dữ liệu.</div>`;
  }

  renderDashboardKpiView(res);
  renderPerDatasetBreakdown(cs);
  renderBIPipelineStages(cs.bi_pipeline);

  const chips = [
    `<span class="px-2.5 py-0.5 bg-pink-100 text-pink-800 border border-pink-200 rounded-full text-[10px] font-bold">📊 ${totalTables} bảng</span>`,
    `<span class="px-2.5 py-0.5 bg-orange-100 text-orange-800 border border-orange-200 rounded-full text-[10px] font-bold">🔢 ${numStats.length} chỉ số số học</span>`,
  ];
  if (docTexts.length) {
    chips.push(`<span class="px-2.5 py-0.5 bg-rose-100 text-rose-800 border border-rose-200 rounded-full text-[10px] font-bold">📝 ${docTexts.length} Word</span>`);
  }
  if ((cs.dedup_dropped_count || 0) > 0) {
    chips.push(`<span class="px-2.5 py-0.5 bg-amber-100 text-amber-800 border border-amber-200 rounded-full text-[10px] font-bold">🧹 -${cs.dedup_dropped_count} trùng</span>`);
  }
  $("agentAlertChips").innerHTML = chips.join("");
  $("dataConfidence").innerText = `${compPct}% (${totalRows}/${cs.total_rows_raw || totalRows} dòng)`;
  $("citationCountLabel").innerText = `${res.audit?.summary?.total_citations || 0} nguồn`;

  if ($("mainTableTitle")) $("mainTableTitle").innerText = "Thống kê & Chỉ số Dữ liệu Công ty";
  if ($("mainTableSubtitle")) $("mainTableSubtitle").innerText = "Tự động phân tích Excel · Word · Lark Base · JSON";
  if ($("comparisonTableHead")) {
    $("comparisonTableHead").innerHTML = `<tr><th class="p-3">Bảng · Chỉ số</th><th class="p-3">Tổng / Nhóm đầu</th><th class="p-3">Trung bình</th><th class="p-3">Trung vị</th><th class="p-3">Min → Max</th><th class="p-3">Bản ghi · Thiếu</th><th class="p-3">Ghi chú</th></tr>`;
  }

  const statRows = [];
  numStats.slice(0, 14).forEach((s) => {
    const outlierBadge = s.outlier_count
      ? `<span class="px-2 py-0.5 bg-amber-100 text-amber-800 border border-amber-200 rounded-full text-[10px] font-extrabold" title="Giá trị bất thường: ${esc((s.outliers || []).join(", "))}">⚠ ${s.outlier_count} ngoại lai</span>`
      : `<span class="px-2 py-0.5 bg-pink-100 text-pink-800 border border-pink-200 rounded-full text-[10px] font-extrabold">Ổn định</span>`;
    const unitBadge = s.unit_note ? `<div class="text-[10px] font-semibold text-orange-700 mt-0.5">${esc(s.unit_note)}</div>` : "";
    statRows.push(`
      <tr class="hover:bg-pink-50/40 transition">
        <td class="p-3.5"><div class="font-extrabold text-slate-800">${esc(s.column)}</div><div class="text-[10px] font-semibold text-slate-500">${esc(s.table)}</div></td>
        <td class="p-3.5 font-extrabold text-slate-900">${fmtNumStat(s.sum)}</td>
        <td class="p-3.5 font-semibold text-orange-700">${fmtNumStat(s.avg)}</td>
        <td class="p-3.5 font-semibold text-slate-700">${fmtNumStat(s.median)}<div class="text-[10px] font-medium text-slate-400">σ ${fmtNumStat(s.std)}</div></td>
        <td class="p-3.5 text-slate-600 font-semibold">${fmtNumStat(s.min)} → ${fmtNumStat(s.max)}</td>
        <td class="p-3.5 font-bold text-slate-700">${fmtNumStat(s.count)}${s.missing_count ? ` · <span class="text-rose-600">thiếu ${s.missing_count}</span>` : ""}</td>
        <td class="p-3.5">${outlierBadge}${unitBadge}</td>
      </tr>`);
  });
  catStats.filter((c) => c.groupable !== false).slice(0, 8).forEach((c) => {
    const top = (c.top_values || [])[0];
    const topText = top ? `${esc(top.value)} <span class="text-slate-500 font-semibold">(${top.count} · ${top.pct}%)</span>` : "--";
    statRows.push(`
      <tr class="hover:bg-orange-50/35 transition">
        <td class="p-3.5"><div class="font-extrabold text-slate-800">${esc(c.column)}</div><div class="text-[10px] font-semibold text-slate-500">${esc(c.table)}</div></td>
        <td class="p-3.5 font-bold text-slate-800" colspan="3">${topText}</td>
        <td class="p-3.5 text-slate-500 font-semibold">${c.unique_count || 0} nhóm</td>
        <td class="p-3.5 font-bold text-slate-700">${fmtNumStat(c.non_empty)}</td>
        <td class="p-3.5"><span class="px-2 py-0.5 bg-orange-100 text-orange-800 border border-orange-200 rounded-full text-[10px] font-extrabold">Phân loại</span></td>
      </tr>`);
  });
  kvTables.forEach((t) => {
    (t.kv_metrics || []).slice(0, 10).forEach((m) => {
      statRows.push(`
        <tr class="hover:bg-pink-50/40 transition">
          <td class="p-3.5"><div class="font-extrabold text-slate-800">${esc(m.label)}</div><div class="text-[10px] font-semibold text-slate-500">${esc(t.source_file)}</div></td>
          <td class="p-3.5 font-extrabold text-slate-900" colspan="3">${esc(m.value)}</td>
          <td class="p-3.5 text-slate-400">—</td>
          <td class="p-3.5 text-slate-400">—</td>
          <td class="p-3.5"><span class="px-2 py-0.5 bg-rose-100 text-rose-800 border border-rose-200 rounded-full text-[10px] font-extrabold">Từ văn bản</span></td>
        </tr>`);
    });
  });

  if (!statRows.length && docTexts.length) {
    docTexts.forEach((d) => {
      statRows.push(`
        <tr class="hover:bg-pink-50/40 transition">
          <td class="p-3.5 font-extrabold text-slate-800">${esc(d.source_file)}</td>
          <td class="p-3.5 text-slate-700" colspan="4">${esc((d.paragraphs || [])[0] || "Đã đọc văn bản")}</td>
          <td class="p-3.5 font-bold text-slate-700">${d.paragraph_count || 0} đoạn</td>
          <td class="p-3.5"><span class="px-2 py-0.5 bg-rose-100 text-rose-800 border border-rose-200 rounded-full text-[10px] font-extrabold">Văn bản</span></td>
        </tr>`);
    });
  }

  $("comparisonTableBody").innerHTML = statRows.length
    ? statRows.join("")
    : `<tr><td colspan="7" class="p-6 text-center text-slate-500 font-semibold">Đã tiếp nhận dữ liệu — mở tab Báo cáo (BC) để xem chi tiết.</td></tr>`;

  const btnDet = $("btnToggleLocDetails");
  const detHidden = $("locationDetailWrapper")?.classList.contains("hidden");
  if (btnDet) {
    btnDet.innerHTML = detHidden
      ? `<i class="fa-solid fa-eye"></i><span>Xem chi tiết các bảng &amp; tài liệu (${tableSummaries.length + docTexts.length}) ▾</span>`
      : `<i class="fa-solid fa-eye-slash"></i><span>Thu gọn chi tiết ▴</span>`;
  }

  const cards = [];
  tableSummaries.forEach((t) => {
    const colHtml = (t.numeric_stats || []).slice(0, 4).map((ns) => `<li><strong>${esc(ns.column)}:</strong> Tổng ${fmtNumStat(ns.sum)}, TB ${fmtNumStat(ns.avg)} (${ns.count} dòng)</li>`).join("");
    const previewHdrs = (t.headers || []).slice(0, 5);
    const previewHtml = (t.preview_rows || [])
      .slice(0, 3)
      .map((r) => `<li>${previewHdrs.map((h) => `<span class="mr-2"><strong>${esc(h)}:</strong> ${esc(r[h] ?? "")}</span>`).join(" · ")}</li>`)
      .join("");
    cards.push(`
      <div class="cute-card p-4 rounded-3xl space-y-2.5">
        <div class="flex justify-between items-center gap-2">
          <h4 class="font-extrabold text-slate-800 text-sm">📊 ${esc(t.sheet_name)}</h4>
          <span class="px-2.5 py-0.5 bg-pink-100 text-pink-700 rounded-full text-[11px] font-extrabold">${t.row_count} dòng · ${t.column_count} cột</span>
        </div>
        <p class="text-[11px] font-semibold text-slate-500">Nguồn: ${esc(t.source_file || t.sheet_name)}</p>
        ${colHtml ? `<ul class="list-disc pl-4 text-xs text-slate-700 space-y-0.5">${colHtml}</ul>` : ""}
        ${previewHtml ? `<details class="bg-white/55 p-3 rounded-2xl border border-white/85 text-xs"><summary class="cursor-pointer font-bold text-pink-800">🔍 Xem mẫu dòng (${(t.preview_rows || []).length})</summary><ul class="list-disc pl-4 mt-1.5 space-y-1 text-slate-600">${previewHtml}</ul></details>` : ""}
      </div>`);
  });
  docTexts.forEach((d) => {
    const pHtml = (d.paragraphs || []).slice(0, 6).map((p) => `<li>${esc(p)}</li>`).join("");
    cards.push(`
      <div class="cute-card p-4 rounded-3xl space-y-2">
        <div class="flex justify-between items-center gap-2">
          <h4 class="font-extrabold text-slate-800 text-sm">📝 ${esc(d.source_file)}</h4>
          <span class="px-2.5 py-0.5 bg-rose-100 text-rose-700 rounded-full text-[11px] font-extrabold">${d.paragraph_count || 0} đoạn</span>
        </div>
        <ul class="list-disc pl-4 text-xs text-slate-700 space-y-1">${pHtml || `<li class="italic text-slate-400">Không có đoạn văn rời (chỉ chứa bảng).</li>`}</ul>
      </div>`);
  });
  $("locationDetailCards").innerHTML = cards.join("");
}

function renderSvgChartVisual(ch) {
  const pts = ch.data_points || [];
  if (!pts.length) return `<div class="text-xs text-slate-400 italic p-3">Chưa đủ điểm dữ liệu vẽ biểu đồ.</div>`;
  const type = ch.chart_type;

  if (type === "bar") {
    return `<div class="space-y-2 py-1">${pts
      .map(
        (p, idx) => `
      <div class="space-y-0.5">
        <div class="flex justify-between text-[11px] font-bold text-slate-700">
          <span class="truncate pr-2">#${idx + 1} · ${esc(p.label)}</span>
          <span class="text-pink-700 shrink-0">${fmtNumStat(p.value)} (${p.pct}%)</span>
        </div>
        <div class="w-full h-3 bg-pink-100/70 rounded-full overflow-hidden border border-white">
          <div class="h-full rounded-full bg-gradient-to-r from-pink-500 via-rose-400 to-orange-300" style="width:${Math.max(6, Math.min(100, Number(p.height_pct || p.pct || 15)))}%"></div>
        </div>
      </div>`
      )
      .join("")}</div>`;
  }

  if (type === "pie") {
    const colors = ["#ec4899", "#f43f5e", "#fb923c", "#f59e0b", "#10b981", "#ec4899"];
    let acc = 0;
    const stops = pts.map((p, i) => {
      const start = acc;
      acc = Math.min(100, acc + Number(p.pct || 0));
      return `${colors[i % colors.length]} ${start.toFixed(1)}% ${acc.toFixed(1)}%`;
    });
    if (acc < 100) stops.push(`#fce7f3 ${acc.toFixed(1)}% 100%`);
    const legend = pts
      .map(
        (p, i) => `
      <div class="flex items-center justify-between gap-2 text-[11px]">
        <span class="flex items-center gap-1.5 truncate"><span class="w-2.5 h-2.5 rounded-full shrink-0" style="background:${colors[i % colors.length]}"></span><span class="font-bold text-slate-700 truncate">${esc(p.label)}</span></span>
        <span class="font-extrabold text-slate-800 shrink-0">${p.pct}%</span>
      </div>`
      )
      .join("");
    return `
      <div class="flex items-center gap-4 py-2">
        <div class="w-28 h-28 rounded-full shrink-0 shadow-inner border-4 border-white relative flex items-center justify-center" style="background: conic-gradient(${stops.join(", ")});">
          <div class="w-14 h-14 rounded-full bg-white/95 flex items-center justify-center text-[10px] font-extrabold text-pink-700 shadow-sm">100%</div>
        </div>
        <div class="flex-1 min-w-0 space-y-1">${legend}</div>
      </div>`;
  }

  if (type === "line") {
    const w = 360;
    const h = 125;
    const padX = 24;
    const padY = 18;
    const maxV = Math.max(...pts.map((p) => Math.abs(Number(p.value) || 0)), 1);
    const coords = pts.map((p, i) => {
      const x = pts.length === 1 ? w / 2 : padX + (i * (w - padX * 2)) / (pts.length - 1);
      const y = h - padY - (Math.abs(Number(p.value) || 0) / maxV) * (h - padY * 2);
      return { x: Math.round(x), y: Math.round(y), label: p.label, val: p.value };
    });
    const poly = coords.map((c) => `${c.x},${c.y}`).join(" ");
    const area = `${coords[0].x},${h - padY} ${poly} ${coords[coords.length - 1].x},${h - padY}`;
    const circles = coords
      .map(
        (c) =>
          `<circle cx="${c.x}" cy="${c.y}" r="3.5" fill="#db2777" stroke="#fff" stroke-width="1.5"><title>${esc(c.label)}: ${fmtNumStat(c.val)}</title></circle>`
      )
      .join("");
    const labels = coords
      .filter((_, i) => i === 0 || i === coords.length - 1 || i === Math.floor(coords.length / 2))
      .map((c) => `<text x="${c.x}" y="${h - 3}" text-anchor="middle" font-size="9" fill="#64748b" font-weight="700">${esc(String(c.label).slice(0, 10))}</text>`)
      .join("");
    return `
      <svg viewBox="0 0 ${w} ${h}" class="w-full h-32 overflow-visible">
        <polygon points="${area}" fill="rgba(236, 72, 153, 0.14)" />
        <polyline fill="none" stroke="#db2777" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" points="${poly}" />
        ${circles}
        ${labels}
      </svg>`;
  }

  // Default: Column, Pareto, Histogram, Combo
  const w = 360;
  const h = 135;
  const padB = 24;
  const padT = 14;
  const plotH = h - padB - padT;
  const n = pts.length;
  const slotW = w / Math.max(n, 1);
  const barW = Math.min(34, Math.max(12, slotW * 0.62));
  const bars = pts
    .map((p, i) => {
      const hp = Math.max(6, Math.min(100, Number(p.height_pct || p.pct || 15)));
      const bh = Math.round((hp / 100) * plotH);
      const x = Math.round(i * slotW + (slotW - barW) / 2);
      const y = padT + (plotH - bh);
      const fill = type === "histogram" ? "#fb923c" : "#ec4899";
      return `
        <g>
          <rect x="${x}" y="${y}" width="${barW}" height="${bh}" rx="4" fill="${fill}" fill-opacity="0.85">
            <title>${esc(p.label)}: ${fmtNumStat(p.value)} (${p.pct}%)</title>
          </rect>
          <text x="${x + barW / 2}" y="${h - 7}" text-anchor="middle" font-size="8.5" fill="#475569" font-weight="700">${esc(String(p.label).slice(0, 8))}</text>
        </g>`;
    })
    .join("");

  let overlayLine = "";
  if (type === "pareto" || type === "combo") {
    const linePts = pts.map((p, i) => {
      const x = Math.round(i * slotW + slotW / 2);
      const lp = type === "pareto" ? Number(p.cumulative_pct || p.pct || 50) : Number(p.line_pct || p.pct || 50);
      const y = Math.round(padT + plotH - (Math.min(100, Math.max(0, lp)) / 100) * plotH);
      return `${x},${y}`;
    });
    overlayLine = `<polyline fill="none" stroke="#ea580c" stroke-width="2.2" stroke-dasharray="${type === "pareto" ? "3,2" : "none"}" points="${linePts.join(" ")}" />`;
  }

  return `<svg viewBox="0 0 ${w} ${h}" class="w-full h-36 overflow-visible">${bars}${overlayLine}</svg>`;
}

function renderBIPipelineStages(bi) {
  if (!bi) return;

  // Stage 1: Data Intake, Sheet Inventory & Field Dictionary
  const s1 = bi.stage1_intake || {};
  if ($("biStage1Badge")) {
    $("biStage1Badge").innerText = `${s1.total_sheets || 0} Sheet · ${(s1.field_dictionary || []).length} Trường`;
  }
  if ($("biStage1Content")) {
    const shHtml = (s1.sheets_inventory || [])
      .map(
        (sh) => `
      <div class="p-2.5 rounded-2xl bg-white/80 border border-white flex flex-wrap items-center justify-between gap-2">
        <div>
          <strong class="text-slate-800">📑 ${esc(sh.sheet_name)}</strong>
          <span class="text-slate-500 ml-1">(${sh.row_count} dòng × ${sh.column_count} cột)</span>
          <div class="text-[11px] text-slate-600 mt-0.5">${esc(sh.meaning)}</div>
        </div>
        <div class="flex flex-wrap gap-1">
          ${(sh.key_fields || []).slice(0, 4).map((kf) => `<span class="px-2 py-0.5 bg-pink-50 text-pink-700 border border-pink-200 rounded-full text-[10px] font-bold">${esc(kf)}</span>`).join("")}
        </div>
      </div>`
      )
      .join("");

    const dictRows = (s1.field_dictionary || [])
      .slice(0, 18)
      .map(
        (fd) => `
      <tr class="border-b border-pink-50 hover:bg-pink-50/40">
        <td class="p-2 font-bold text-slate-700">${esc(fd.sheet_name)}</td>
        <td class="p-2 font-extrabold text-pink-800">${esc(fd.column)}</td>
        <td class="p-2 text-slate-600">${esc(fd.data_type)}</td>
        <td class="p-2"><span class="px-2 py-0.5 bg-orange-50 text-orange-800 rounded-lg font-bold text-[10px]">${esc(fd.semantic_role)}</span></td>
        <td class="p-2 text-slate-600">Đủ ${fd.non_empty_count} · Thiếu ${fd.missing_count} (${fd.missing_pct}%)</td>
        <td class="p-2 text-slate-500">${esc(fd.meaning)}</td>
      </tr>`
      )
      .join("");

    $("biStage1Content").innerHTML = `
      <div class="p-3 rounded-2xl bg-pink-50/70 border border-pink-100 text-slate-700 font-semibold">
        <strong>Nhận xét ban đầu về chất lượng dữ liệu:</strong> ${esc(s1.initial_quality_assessment || "")}
      </div>
      <div class="space-y-2">${shHtml}</div>
      <details class="bg-white/75 rounded-2xl border border-white p-3">
        <summary class="cursor-pointer font-extrabold text-pink-800">📖 Xem Từ điển Trường Dữ liệu (${(s1.field_dictionary || []).length} cột) ▾</summary>
        <div class="overflow-x-auto mt-2">
          <table class="w-full text-left border-collapse text-[11px]">
            <thead class="bg-pink-50 text-pink-900 font-extrabold">
              <tr><th class="p-2">Sheet</th><th class="p-2">Cột</th><th class="p-2">Kiểu</th><th class="p-2">Vai trò</th><th class="p-2">Đầy đủ / Thiếu</th><th class="p-2">Ý nghĩa</th></tr>
            </thead>
            <tbody>${dictRows}</tbody>
          </table>
        </div>
      </details>`;
  }

  // Stage 4: Charts
  if ($("biChartsGrid")) {
    const charts = bi.stage4_charts || [];
    $("biChartsGrid").innerHTML = charts.length
      ? charts
          .map(
            (ch) => `
          <div class="p-4 rounded-3xl bg-white/80 border border-white shadow-sm space-y-2.5 flex flex-col justify-between">
            <div class="space-y-1">
              <div class="flex items-center justify-between gap-2">
                <span class="px-2.5 py-0.5 bg-pink-100 text-pink-800 rounded-full text-[10px] font-extrabold">${esc(ch.chart_type_label)}</span>
                <span class="text-[10px] font-bold text-slate-400">Trục X: ${esc(ch.x_axis_label)} · Trục Y: ${esc(ch.y_axis_label)}</span>
              </div>
              <h4 class="text-xs font-extrabold text-slate-800">${esc(ch.title)}</h4>
              <div class="text-[10px] font-semibold text-orange-700">Chú giải: ${esc(ch.legend || "")}</div>
            </div>
            <div class="bg-white/90 rounded-2xl p-3 border border-pink-100/80">${renderSvgChartVisual(ch)}</div>
            <div class="space-y-1 pt-1 border-t border-pink-100 text-[11px]">
              <div class="text-slate-700"><strong class="text-pink-800">Nhận xét:</strong> ${esc(ch.commentary)}</div>
              <div class="text-slate-600"><strong class="text-orange-800">Ý nghĩa kinh doanh:</strong> ${esc(ch.business_meaning)}</div>
            </div>
          </div>`
          )
          .join("")
      : `<div class="col-span-2 text-xs text-slate-500 p-3">Chưa có biểu đồ định lượng.</div>`;
  }

  // Stage 5: Insights (DATA -> INFORMATION -> INSIGHT -> DECISION)
  if ($("biInsightsList")) {
    const insights = bi.stage5_insights || [];
    $("biInsightsList").innerHTML = insights
      .map((ins) => {
        const d = ins.diid_chain || {};
        return `
        <div class="p-4 rounded-3xl bg-white/80 border border-white shadow-sm space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h4 class="text-xs font-extrabold text-pink-900">💡 ${esc(ins.id)} · ${esc(ins.title)}</h4>
            <span class="px-2.5 py-0.5 bg-orange-100 text-orange-800 rounded-full text-[10px] font-extrabold">${esc(ins.category)}</span>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-4 gap-2 text-[11px]">
            <div class="p-2.5 rounded-2xl bg-slate-50 border border-slate-200"><div class="font-extrabold text-slate-700 text-[10px]">1. DATA (Dữ liệu gốc)</div><div class="text-slate-600 mt-0.5">${esc(d.data || "")}</div></div>
            <div class="p-2.5 rounded-2xl bg-pink-50/80 border border-pink-200"><div class="font-extrabold text-pink-800 text-[10px]">2. INFORMATION (Thông tin)</div><div class="text-slate-700 mt-0.5">${esc(d.information || "")}</div></div>
            <div class="p-2.5 rounded-2xl bg-orange-50/80 border border-orange-200"><div class="font-extrabold text-orange-800 text-[10px]">3. INSIGHT (Nguyên nhân)</div><div class="text-slate-700 mt-0.5">${esc(d.insight || "")}</div></div>
            <div class="p-2.5 rounded-2xl bg-emerald-50/80 border border-emerald-200"><div class="font-extrabold text-emerald-800 text-[10px]">4. DECISION (Quyết định)</div><div class="text-slate-700 mt-0.5">${esc(d.decision || "")}</div></div>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px] pt-1">
            <div><strong class="text-slate-800">• Phát hiện điều gì?</strong> ${esc(ins.finding)}</div>
            <div><strong class="text-slate-800">• Số liệu chứng minh:</strong> ${esc(ins.evidence)}</div>
            <div><strong class="text-emerald-800">• Nguyên nhân (Đã chứng minh):</strong> ${esc(ins.causes_proven)}</div>
            <div><strong class="text-amber-800">• Giả thuyết (Cần kiểm chứng):</strong> ${esc(ins.causes_hypothesis)}</div>
            <div><strong class="text-rose-800">• Tác động doanh nghiệp:</strong> ${esc(ins.business_impact)}</div>
            <div><strong class="text-pink-800">• Doanh nghiệp nên làm gì?</strong> ${esc(ins.recommended_action)}</div>
          </div>
        </div>`;
      })
      .join("");
  }

  // Stage 6: Solutions Table
  if ($("biSolutionsTableBody")) {
    const sols = bi.stage6_solutions || [];
    $("biSolutionsTableBody").innerHTML = sols
      .map(
        (s) => `
      <tr class="hover:bg-pink-50/40 align-top">
        <td class="p-3 font-extrabold text-pink-800 whitespace-nowrap">${esc(s.priority_order)}</td>
        <td class="p-3 font-semibold text-slate-800">${esc(s.problem)}</td>
        <td class="p-3 text-slate-700 font-medium">${esc(s.solution)}</td>
        <td class="p-3 font-bold text-orange-800">${esc(s.department)}</td>
        <td class="p-3 font-bold text-emerald-800">${esc(s.kpi)}</td>
        <td class="p-3 text-slate-600">${esc(s.risks_and_conditions)}</td>
      </tr>`
      )
      .join("");
  }
}

function renderDashboardKpiView(resInput) {
  const res = resInput || state.lastResult;
  const cs = res?.company_stats;
  if (!cs) return;
  const tables = (cs.table_summaries || []).filter((t) => !t.is_kv);
  const dsSel = $("dashDatasetSelect");
  const pSel = $("dashPeriodSelect");
  const bi = cs.bi_pipeline || {};
  const ts = bi.stage3_analysis?.time_analysis || {};
  const periods = ts.periods || [];

  if (dsSel && resInput) {
    dsSel.innerHTML = `<option value="__ALL__">Tất cả bộ dữ liệu (${tables.length})</option>` +
      tables.map((t, i) => `<option value="${i}">${esc(t.sheet_name)} (${fmtNumStat(t.row_count)} dòng)</option>`).join("");
  }
  if (pSel && resInput) {
    if (ts.available && periods.length) {
      pSel.classList.remove("hidden");
      pSel.innerHTML = `<option value="__ALL__">Toàn kỳ (${periods.length} kỳ)</option>` +
        periods.map((p) => `<option value="${esc(p.period)}">${esc(p.period)} (${fmtNumStat(p.count)} dòng)</option>`).reverse().join("");
    } else {
      pSel.classList.add("hidden");
    }
  }

  const chosenPeriod = pSel && !pSel.classList.contains("hidden") ? pSel.value : "__ALL__";
  const periodObj = chosenPeriod !== "__ALL__" ? periods.find((p) => p.period === chosenPeriod) : null;
  const fin = cs.financial_summary || {};
  const totalOrders = periodObj ? periodObj.count : cs.total_rows_clean || 0;
  const revVal = periodObj ? periodObj.sum : fin.total_revenue;
  const costVal = fin.total_cost;
  const profitVal = fin.net_profit;
  const momBadge = periodObj && periodObj.mom_growth_pct !== null && periodObj.mom_growth_pct !== undefined
    ? `<div class="text-[10px] font-extrabold mt-1 ${periodObj.mom_growth_pct >= 0 ? "text-emerald-600" : "text-rose-600"}">${periodObj.mom_growth_pct >= 0 ? "+" : ""}${periodObj.mom_growth_pct}% so với kỳ trước</div>`
    : "";

  if ($("dashSubtitle")) {
    $("dashSubtitle").textContent = periodObj
      ? `Kỳ ${periodObj.period} · ${fmtNumStat(periodObj.count)} dòng · ${esc(ts.sheet_name || "")}`
      : `${tables.length} bộ dữ liệu · ${fmtNumStat(cs.total_rows_clean || 0)} dòng sạch · Độ đầy đủ ${cs.completeness_pct || 100}%`;
  }

  if ($("dash4KpisGrid")) {
    const revCol = fin.revenue_col || (cs.numeric_highlights?.[0]?.column || "Chỉ số chính");
    const revDisplay = revVal !== null && revVal !== undefined ? fmtNumStat(revVal) : (cs.numeric_highlights?.[0] ? fmtNumStat(cs.numeric_highlights[0].sum) : "—");
    $("dash4KpisGrid").innerHTML = `
      <div class="p-3.5 rounded-2xl bg-white/85 border border-white shadow-sm">
        <div class="text-[11px] font-bold text-slate-500">Số đơn hàng / Bản ghi</div>
        <div class="text-xl font-extrabold text-slate-800 mt-1">${fmtNumStat(totalOrders)}</div>
        <div class="text-[10px] font-semibold text-slate-400 mt-1">${periodObj ? `Trong kỳ ${esc(periodObj.period)}` : "Tổng bản ghi sạch"}</div>
      </div>
      <div class="p-3.5 rounded-2xl bg-white/85 border border-white shadow-sm">
        <div class="text-[11px] font-bold text-slate-500">Doanh thu / Quy mô</div>
        <div class="text-xl font-extrabold text-pink-700 mt-1">${revDisplay}</div>
        <div class="text-[10px] font-semibold text-slate-400 mt-0.5">${esc(revCol)}</div>
        ${momBadge}
      </div>
      <div class="p-3.5 rounded-2xl bg-white/85 border border-white shadow-sm">
        <div class="text-[11px] font-bold text-slate-500">Lợi nhuận</div>
        <div class="text-xl font-extrabold text-emerald-700 mt-1">${profitVal !== null && profitVal !== undefined ? fmtNumStat(profitVal) : "—"}</div>
        <div class="text-[10px] font-semibold text-slate-400 mt-0.5">${fin.profit_col ? esc(fin.profit_col) : "Chưa có cột lợi nhuận riêng"}</div>
      </div>
      <div class="p-3.5 rounded-2xl bg-white/85 border border-white shadow-sm">
        <div class="text-[11px] font-bold text-slate-500">Chi phí</div>
        <div class="text-xl font-extrabold text-orange-700 mt-1">${costVal !== null && costVal !== undefined ? fmtNumStat(costVal) : "—"}</div>
        <div class="text-[10px] font-semibold text-slate-400 mt-0.5">${fin.cost_col ? esc(fin.cost_col) : "Chưa có cột chi phí riêng"}</div>
      </div>`;
  }

  if ($("dash2x2ChartsGrid")) {
    const charts = bi.stage4_charts || [];
    const lineCh = charts.find((c) => c.chart_type === "line");
    const pieCh = charts.find((c) => c.chart_type === "pie");
    const colCh = charts.find((c) => c.chart_type === "column") || charts.find((c) => c.chart_type === "bar");
    const drv = ts.period_drivers || {};
    const cards = [];

    if (lineCh) {
      const tblRows = periods.slice(-12).map((p) => `<tr class="border-t border-pink-50"><td class="py-1 px-2 font-bold">${esc(p.period)}</td><td class="py-1 px-2 text-right font-extrabold text-pink-700">${fmtNumStat(p.sum)}</td><td class="py-1 px-2 text-right">${p.mom_growth_pct !== null ? `${p.mom_growth_pct > 0 ? "+" : ""}${p.mom_growth_pct}%` : "—"}</td></tr>`).join("");
      cards.push(`
        <div class="p-4 rounded-2xl bg-white/85 border border-white space-y-2">
          <div class="font-extrabold text-xs text-slate-800">📈 ${esc(lineCh.title)}</div>
          <div class="text-[10px] text-slate-500 font-semibold">${esc(lineCh.x_axis_label)} · ${esc(lineCh.y_axis_label)}</div>
          ${renderSvgChartVisual(lineCh)}
          <details class="text-[11px] bg-pink-50/50 rounded-xl p-2"><summary class="cursor-pointer font-extrabold text-pink-800">▶ Số liệu theo tháng (${periods.length} kỳ)</summary><table class="w-full mt-1.5 text-[10px]"><thead><tr class="text-slate-500"><th class="text-left px-2">Kỳ</th><th class="text-right px-2">Tổng</th><th class="text-right px-2">Tăng trưởng</th></tr></thead><tbody>${tblRows}</tbody></table></details>
        </div>`);
    }
    if (pieCh) {
      cards.push(`
        <div class="p-4 rounded-2xl bg-white/85 border border-white space-y-2">
          <div class="font-extrabold text-xs text-slate-800">🍩 ${esc(pieCh.title)}</div>
          <div class="text-[10px] text-slate-500 font-semibold">${esc(pieCh.commentary)}</div>
          ${renderSvgChartVisual(pieCh)}
        </div>`);
    }
    if (colCh) {
      const barsHtml = (colCh.data_points || []).slice(0, 6).map((p) => `
        <div class="flex items-center gap-2 text-[11px]">
          <span class="w-28 truncate font-bold text-slate-700" title="${esc(p.label)}">${esc(p.label)}</span>
          <div class="flex-1 h-2.5 bg-pink-100/70 rounded-full overflow-hidden"><div class="h-full rounded-full bg-gradient-to-r from-emerald-400 to-pink-400" style="width:${Math.max(5, Math.min(100, Number(p.height_pct || p.pct || 10)))}%"></div></div>
          <span class="w-24 text-right font-extrabold text-slate-800">${fmtNumStat(p.value)}</span>
        </div>`).join("");
      cards.push(`
        <div class="p-4 rounded-2xl bg-white/85 border border-white space-y-2.5">
          <div class="font-extrabold text-xs text-slate-800">📊 Đóng góp theo nhóm (${esc(colCh.x_axis_label)})</div>
          <div class="space-y-2">${barsHtml}</div>
          <div class="text-[10px] font-semibold text-slate-500">${esc(colCh.commentary)}</div>
        </div>`);
    }
    if (drv.available && (drv.groups || []).length) {
      const maxAbs = Math.max(...drv.groups.map((g) => Math.abs(Number(g.delta) || 0)), 1);
      const drvHtml = drv.groups.map((g) => {
        const w = Math.max(6, Math.round((Math.abs(g.delta) * 100) / maxAbs));
        const pos = g.delta >= 0;
        return `
          <div class="flex items-center gap-2 text-[11px]">
            <span class="w-28 truncate font-bold text-slate-700" title="${esc(g.label)}">${esc(g.label)}</span>
            <div class="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden"><div class="h-full rounded-full ${pos ? "bg-emerald-400" : "bg-rose-400"}" style="width:${w}%"></div></div>
            <span class="w-24 text-right font-extrabold ${pos ? "text-emerald-700" : "text-rose-700"}">${pos ? "+" : ""}${fmtNumStat(g.delta)}</span>
          </div>`;
      }).join("");
      cards.push(`
        <div class="p-4 rounded-2xl bg-white/85 border border-white space-y-2.5">
          <div class="font-extrabold text-xs text-slate-800">🔀 Nhóm làm thay đổi (${esc(drv.prev_period)} → ${esc(drv.curr_period)})</div>
          <div class="text-[10px] font-semibold text-slate-500">Theo ${esc(drv.group_col)} · Chênh lệch tổng: <strong>${drv.total_delta >= 0 ? "+" : ""}${fmtNumStat(drv.total_delta)}</strong></div>
          <div class="space-y-2">${drvHtml}</div>
        </div>`);
    }
    $("dash2x2ChartsGrid").innerHTML = cards.join("") || `<div class="col-span-2 text-xs text-slate-500 p-2">Chưa có biểu đồ chuỗi thời gian hoặc phân nhóm.</div>`;
  }

  const mBar = $("dashProfitMarginBar");
  if (mBar) {
    if (fin.margin_pct !== null && fin.margin_pct !== undefined) {
      mBar.classList.remove("hidden");
      mBar.innerHTML = `<span>Tỷ lệ lợi nhuận trên doanh thu (Biên lợi nhuận ròng)</span><span class="text-base text-pink-700">${fin.margin_pct}%</span>`;
    } else {
      mBar.classList.add("hidden");
    }
  }
}

function renderPerDatasetBreakdown(cs) {
  const box = $("perDatasetBreakdownGrid");
  if (!box) return;
  const tables = (cs.table_summaries || []).filter((t) => !t.is_kv);
  const classifiers = cs.classifiers || [];
  if (!tables.length) {
    box.innerHTML = "";
    return;
  }
  box.innerHTML = tables.map((t, idx) => {
    const clf = classifiers.find((c) => c.sheet_name === t.sheet_name && !c.group_name.includes("ABC")) || classifiers.find((c) => c.sheet_name === t.sheet_name);
    const ns0 = (t.numeric_stats || [])[0];
    const bars = clf && (clf.groups || []).length
      ? clf.groups.slice(0, 5).map((g) => `
          <div class="flex items-center gap-2 text-[11px]">
            <span class="w-28 truncate font-bold text-slate-700">${esc(g.label)}</span>
            <div class="flex-1 h-2.5 bg-pink-100/70 rounded-full overflow-hidden"><div class="h-full rounded-full bg-gradient-to-r from-pink-500 to-orange-300" style="width:${Math.max(5, Math.min(100, Number(g.share_pct || 10)))}%"></div></div>
            <span class="w-28 text-right font-extrabold text-slate-800">${fmtNumStat(g.metric_sum ?? g.count)}</span>
          </div>`).join("")
      : `<div class="text-[11px] text-slate-500">Chưa có cột phân nhóm để vẽ thanh đóng góp.</div>`;
    const bullets = [];
    if (clf && clf.groups?.length) {
      const top = clf.groups[0];
      bullets.push(`<li>"${esc(top.label)}" có giá trị cao nhất (${fmtNumStat(top.metric_sum ?? top.count)}, chiếm ${top.share_pct}%).</li>`);
    }
    if (ns0) {
      bullets.push(`<li>"${esc(ns0.column)}" từ ${fmtNumStat(ns0.min)} đến ${fmtNumStat(ns0.max)}, trung bình ${fmtNumStat(ns0.avg)} (trung vị ${fmtNumStat(ns0.median)}).</li>`);
    }
    bullets.push(`<li>Còn ${fmtNumStat(t.row_count)} dòng sạch · loại ${fmtNumStat(t.dropped_row_count || 0)} dòng · ${fmtNumStat(t.missing_cells_count || 0)} ô trống.</li>`);

    const colRows = (t.numeric_stats || []).map((n) => `
      <tr class="border-t border-pink-50"><td class="p-2 font-bold">${esc(n.column)}</td><td class="p-2 text-right">${fmtNumStat(n.sum)}</td><td class="p-2 text-right">${fmtNumStat(n.avg)}</td><td class="p-2 text-right">${fmtNumStat(n.median)}</td><td class="p-2 text-right">${fmtNumStat(n.min)} → ${fmtNumStat(n.max)}</td><td class="p-2 text-right">${n.missing_count || 0}</td></tr>`).join("");

    return `
      <div class="cute-card rounded-3xl p-4 space-y-3">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h4 class="font-extrabold text-slate-800 text-sm">📁 Bộ ${idx + 1} — ${esc(t.sheet_name)}</h4>
            <div class="text-[11px] font-semibold text-slate-500">${fmtNumStat(t.row_count)} dòng · ${t.column_count} cột · ${t.dropped_row_count || 0} dòng đã loại · ${t.missing_cells_count || 0} ô còn trống</div>
          </div>
          <span class="px-2.5 py-0.5 bg-pink-100 text-pink-800 rounded-full text-[10px] font-extrabold">${esc(t.source_file || t.sheet_name)}</span>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div class="p-3 rounded-2xl bg-white/80 border border-white space-y-2">
            <div class="text-xs font-extrabold text-slate-800">${clf ? esc(clf.group_name) : "Tổng hợp nhóm"}</div>
            <div class="space-y-2">${bars}</div>
          </div>
          <div class="p-3 rounded-2xl bg-emerald-50/60 border border-white space-y-1.5">
            <div class="text-xs font-extrabold text-emerald-900">Phân bố và độ phủ</div>
            <ul class="list-disc pl-4 text-[11px] text-slate-700 space-y-1">${bullets.join("")}</ul>
          </div>
        </div>
        ${colRows ? `<details class="bg-white/75 rounded-2xl p-2.5 border border-white text-xs"><summary class="cursor-pointer font-extrabold text-pink-800">▶ Thống kê từng cột (${(t.numeric_stats || []).length} cột số)</summary><div class="overflow-x-auto mt-2"><table class="w-full text-[11px]"><thead class="bg-pink-50 text-pink-900"><tr><th class="p-2 text-left">Cột</th><th class="p-2 text-right">Tổng</th><th class="p-2 text-right">Trung bình</th><th class="p-2 text-right">Trung vị</th><th class="p-2 text-right">Min → Max</th><th class="p-2 text-right">Thiếu</th></tr></thead><tbody>${colRows}</tbody></table></div></details>` : ""}
      </div>`;
  }).join("");
}

function renderCleanPreviewTable(resInput) {
  const res = resInput || state.lastResult;
  const cs = res?.company_stats;
  const card = $("cleaningWorkspaceCard");
  if (!card) return;
  if (!cs || !(cs.table_summaries || []).length) {
    card.classList.add("hidden");
    return;
  }
  card.classList.remove("hidden");
  const tables = cs.table_summaries || [];
  const sel = $("cleanDatasetSelect");
  if (sel && resInput) {
    sel.innerHTML = tables.map((t, i) => `<option value="${i}">Bộ ${i + 1} — ${esc(t.sheet_name)} (${fmtNumStat(t.raw_row_count || t.row_count)} dòng nguồn)</option>`).join("");
  }
  const idx = Number(sel?.value || 0);
  const tbl = tables[idx] || tables[0];
  if ($("cleanRowsCount")) $("cleanRowsCount").textContent = fmtNumStat(tbl.row_count);
  if ($("cleanDroppedCount")) $("cleanDroppedCount").textContent = fmtNumStat(tbl.dropped_row_count ?? cs.total_rows_dropped ?? 0);
  if ($("cleanMissingCount")) $("cleanMissingCount").textContent = fmtNumStat(tbl.missing_cells_count ?? cs.empty_cells_count ?? 0);
  if ($("cleanPreviewMeta")) {
    $("cleanPreviewMeta").textContent = `Xem trước sau làm sạch: ${fmtNumStat(tbl.raw_row_count || tbl.row_count)} dòng nguồn · ${cs.empty_rows_dropped || 0} dòng trống · ${cs.dedup_dropped_count || 0} dòng trùng · ${cs.missing_rows_dropped || 0} dòng thiếu bị xóa · ${cs.trimmed_cells_count || 0} ô đã cắt khoảng trắng`;
  }
  const headers = tbl.headers || [];
  const rows = tbl.preview_rows || [];
  if ($("cleanedPreviewTableHead")) {
    $("cleanedPreviewTableHead").innerHTML = `<tr>${headers.map((h) => `<th class="p-2.5 whitespace-nowrap border-b border-pink-100">${esc(h)}</th>`).join("")}</tr>`;
  }
  if ($("cleanedPreviewTableBody")) {
    $("cleanedPreviewTableBody").innerHTML = rows.length
      ? rows.map((r) => `<tr class="hover:bg-pink-50/40">${headers.map((h) => `<td class="p-2 whitespace-nowrap text-slate-700">${esc(r[h] ?? "")}</td>`).join("")}</tr>`).join("")
      : `<tr><td colspan="${Math.max(1, headers.length)}" class="p-4 text-center text-slate-400">Không có dòng dữ liệu sạch.</td></tr>`;
  }
}

async function reRunWithCleaningRules() {
  showToast("Đang áp dụng quy tắc làm sạch mới...");
  await runAIAgentWorkflow();
}

function renderTab1Results(res) {
  if (res.analysis_mode === "company_statistics" || res.company_stats) {
    renderCompanyStatisticsDashboard(res);
    return;
  }

  $("statsDeepSection")?.classList.add("hidden");
  if ($("mainTableTitle")) $("mainTableTitle").innerText = "Bảng tổng hợp dữ liệu";
  if ($("mainTableSubtitle")) $("mainTableSubtitle").innerText = "Bấm mã nguồn để kiểm tra";
  if ($("comparisonTableHead")) {
    $("comparisonTableHead").innerHTML = `<tr><th class="p-3">Địa bàn</th><th class="p-3">Quy mô</th><th class="p-3">Fit</th><th class="p-3">Triển khai</th><th class="p-3">Cạnh tranh</th><th class="p-3">Điểm</th><th class="p-3">Kết quả &amp; Nguồn</th></tr>`;
  }
  const btnDet = $("btnToggleLocDetails");
  const detHidden = $("locationDetailWrapper")?.classList.contains("hidden");
  if (btnDet) {
    btnDet.innerHTML = detHidden
      ? `<i class="fa-solid fa-eye"></i><span>Xem chi tiết các địa bàn ▾</span>`
      : `<i class="fa-solid fa-eye-slash"></i><span>Thu gọn chi tiết ▴</span>`;
  }

  const ev = res.evaluation || {};
  const ing = res.ingestion || {};
  const evals = ev.evaluations || [];
  const selected = evals.filter((x) => x.overall_status === "SELECTED");

  // Top 1 card
  if (selected[0]) {
    $("top1Name").innerText = selected[0].location;
    $("top1Score").innerText = `${selected[0].total_weighted_score}/10`;
    $("top1Reason").innerText = selected[0].exclusion_or_selection_reason;
  } else {
    $("top1Name").innerText = "Chưa đủ căn cứ";
    $("top1Score").innerText = "--/10";
    $("top1Reason").innerText = (ev.conditions_to_supplement || ["Cần bổ sung dữ liệu."])[0];
  }

  // Top 2 card
  if (selected[1]) {
    $("top2Name").innerText = selected[1].location;
    $("top2Score").innerText = `${selected[1].total_weighted_score}/10`;
    $("top2Reason").innerText = selected[1].exclusion_or_selection_reason;
  } else {
    $("top2Name").innerText = "Chưa đủ #2";
    $("top2Score").innerText = "--/10";
    $("top2Reason").innerText = (ev.conditions_to_supplement || ["Thiếu dữ liệu địa bàn thứ 2."])[0];
  }

  // Agent alert chips
  const chips = [];
  (ing.dedup_log || []).forEach((d) =>
    chips.push(`<span class="px-2.5 py-0.5 bg-amber-100 text-amber-800 border border-amber-200 rounded-full text-[10px] font-bold">🧹 Trùng ${esc(d.dropped_record_id)}</span>`)
  );
  (ing.period_normalization_log || [])
    .filter((p) => p.normalization_note && p.normalization_note.includes("Quy đổi"))
    .forEach((p) =>
      chips.push(`<span class="px-2.5 py-0.5 bg-orange-100 text-orange-800 border border-orange-200 rounded-full text-[10px] font-bold">⏱️ Quy đổi ${esc(p.location)}</span>`)
    );
  evals
    .filter((x) => x.overall_status === "DISQUALIFIED" || x.overall_status === "INSUFFICIENT_DATA")
    .forEach((x) =>
      chips.push(`<span class="px-2.5 py-0.5 bg-rose-100 text-rose-700 border border-rose-200 rounded-full text-[10px] font-bold">❌ ${esc(x.location)}</span>`)
    );
  if (ev.near_tie_alert) {
    chips.push(`<span class="px-2.5 py-0.5 bg-pink-100 text-pink-800 border border-pink-200 rounded-full text-[10px] font-bold">⚖️ Sát điểm</span>`);
  }
  if (!chips.length) {
    chips.push(`<span class="px-2.5 py-0.5 bg-pink-50 text-pink-700 border border-pink-200 rounded-full text-[10px] font-bold">🌸 Sạch</span>`);
  }
  $("agentAlertChips").innerHTML = chips.join("");

  const sufficientCount = (res.conflict_gap?.sufficient_locations || []).length;
  $("dataConfidence").innerText = `${sufficientCount}/${evals.length} địa bàn`;
  $("citationCountLabel").innerText = `${res.audit?.summary?.total_citations || 0} CIT`;

  // Comparison Table
  const tbody = $("comparisonTableBody");
  const fmtScore = (cs, colorCls) => {
    if (!cs || cs.raw_score === null || cs.raw_score === undefined) {
      return `<span class="px-2 py-0.5 bg-slate-100 text-slate-500 rounded-xl font-bold">Thiếu</span>`;
    }
    let badge = "";
    if (cs.gate_status === "FAIL") badge = `<span class="ml-1 px-1.5 py-0.5 bg-rose-100 text-rose-700 rounded-lg text-[10px] font-extrabold">LOẠI</span>`;
    else if (cs.gate_status === "BOUNDARY_PASS") badge = `<span class="ml-1 px-1.5 py-0.5 bg-amber-100 text-amber-800 rounded-lg text-[10px] font-extrabold">BIÊN</span>`;
    return `<span class="px-2.5 py-0.5 ${colorCls} rounded-xl font-extrabold">${cs.raw_score}/10</span>${badge}`;
  };

  const statusPill = (st) => {
    if (st === "SELECTED") return `<span class="px-2.5 py-0.5 bg-pink-100 text-pink-800 border border-pink-200 rounded-full font-extrabold">🌸 Chọn</span>`;
    if (st === "ALTERNATIVE") return `<span class="px-2.5 py-0.5 bg-orange-50 text-orange-800 border border-orange-200 rounded-full font-extrabold">🧡 Dự phòng</span>`;
    if (st === "DISQUALIFIED") return `<span class="px-2.5 py-0.5 bg-rose-100 text-rose-700 rounded-full font-extrabold">❌ Loại</span>`;
    return `<span class="px-2.5 py-0.5 bg-amber-100 text-amber-800 rounded-full font-extrabold">⚠️ Thiếu</span>`;
  };

  tbody.innerHTML = evals
    .map((item) => {
      const byCat = Object.fromEntries((item.criterion_scores || []).map((c) => [c.category_key, c]));
      const rankBadge = item.rank === 1
        ? "bg-pink-200 text-pink-800 font-extrabold"
        : item.rank === 2
        ? "bg-orange-200 text-orange-800 font-extrabold"
        : "bg-rose-50 text-rose-600 font-bold";
      const cits = (item.citation_ids || []).slice(0, 3).map((c) => `<button type="button" onclick="openCitationModal('${c}')" class="cit-chip">${c}</button>`).join("");
      return `
        <tr class="hover:bg-pink-50/40 transition">
          <td class="p-3.5 font-extrabold text-slate-800 flex items-center space-x-2">
            <span class="w-6 h-6 rounded-full ${rankBadge} flex items-center justify-center text-[10px] shrink-0">${item.rank || "-"}</span>
            <span>${esc(item.location)}</span>
          </td>
          <td class="p-3.5">${fmtScore(byCat.market_size, "bg-amber-50 text-amber-800 border border-amber-200")}</td>
          <td class="p-3.5">${fmtScore(byCat.product_fit, "bg-pink-50 text-pink-700 border border-pink-200")}</td>
          <td class="p-3.5">${fmtScore(byCat.deployment_capability, "bg-orange-50 text-orange-700 border border-orange-200")}</td>
          <td class="p-3.5">${fmtScore(byCat.competition, "bg-rose-50 text-rose-700 border border-rose-200")}</td>
          <td class="p-3.5 font-extrabold text-pink-600">${item.total_weighted_score !== null ? item.total_weighted_score : "N/A"}</td>
          <td class="p-3.5">
            <div class="mb-1">${statusPill(item.overall_status)}</div>
            <div class="flex flex-wrap gap-1">${cits}</div>
          </td>
        </tr>`;
    })
    .join("");

  // Detailed Location Cards (collapsed behind button)
  $("locationDetailCards").innerHTML = evals
    .map((item) => {
      const factsHtml = (item.document_facts_summary || []).length
        ? item.document_facts_summary.map((f) => `<li>${linkifyCitations(esc(f))}</li>`).join("")
        : `<li class="italic text-slate-400">Không có đủ dữ liệu gốc.</li>`;
      const infHtml = (item.agent_inferences_summary || [])
        .map((inf) => `<li>${linkifyCitations(esc(inf))}</li>`)
        .join("");

      return `
        <div class="cute-card p-4 rounded-3xl space-y-2.5">
          <div class="flex justify-between items-center">
            <div class="flex items-center space-x-2">
              <h4 class="font-extrabold text-slate-800 text-sm">${item.rank ? `#${item.rank} · ` : ""}${esc(item.location)}</h4>
              ${statusPill(item.overall_status)}
            </div>
            <span class="px-3 py-0.5 bg-pink-100 text-pink-700 rounded-full text-xs font-extrabold">${
              item.total_weighted_score !== null ? item.total_weighted_score + "/10" : "N/A"
            }</span>
          </div>
          <p class="text-xs font-medium text-slate-600">${esc(item.exclusion_or_selection_reason)}</p>
          <details class="bg-white/55 backdrop-blur-md p-3 rounded-2xl border border-white/85 shadow-sm text-xs">
            <summary class="cursor-pointer font-bold text-pink-800">📄 Dữ liệu gốc (${(item.document_facts_summary || []).length})</summary>
            <ul class="list-disc pl-4 mt-2 space-y-1 text-slate-700">${factsHtml}</ul>
          </details>
          <details class="bg-white/55 backdrop-blur-md p-3 rounded-2xl border border-white/85 shadow-sm text-xs">
            <summary class="cursor-pointer font-bold text-orange-800">🤖 Suy luận Agent (${(item.agent_inferences_summary || []).length})</summary>
            <ul class="list-disc pl-4 mt-2 space-y-1 text-slate-700">${infHtml}</ul>
          </details>
        </div>`;
    })
    .join("");
}

function renderSimpleMarkdown(mdText) {
  const lines = String(mdText || "").split(/\r?\n/);
  const html = [];
  let inList = false;
  let inTable = false;

  const closeLists = () => {
    if (inList) {
      html.push("</ul>");
      inList = false;
    }
    if (inTable) {
      html.push("</tbody></table></div>");
      inTable = false;
    }
  };
  const inline = (t) =>
    linkifyCitations(
      esc(t)
        .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
        .replace(/`([^`]+)`/g, "<code>$1</code>")
    );

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      closeLists();
      continue;
    }
    if (line.startsWith("|")) {
      if (line.replace(/[\|\-:\s]/g, "") === "") continue;
      if (!inTable) {
        closeLists();
        const ths = line.split("|").slice(1, -1).map((c) => `<th>${esc(c.trim())}</th>`).join("");
        html.push(`<div class="overflow-x-auto"><table><thead><tr>${ths}</tr></thead><tbody>`);
        inTable = true;
      } else {
        const tds = line.split("|").slice(1, -1).map((c) => `<td>${inline(c.trim())}</td>`).join("");
        html.push(`<tr>${tds}</tr>`);
      }
      continue;
    }
    closeLists();
    if (line.startsWith("### ")) html.push(`<h3>${inline(line.slice(4))}</h3>`);
    else if (line.startsWith("## ")) html.push(`<h2>${inline(line.slice(3))}</h2>`);
    else if (line.startsWith("# ")) html.push(`<h1>${inline(line.slice(2))}</h1>`);
    else if (line.startsWith("- ")) {
      if (!inList) {
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${inline(line.slice(2))}</li>`);
    } else {
      html.push(`<p class="mt-1">${inline(line)}</p>`);
    }
  }
  closeLists();
  return html.join("\n");
}

function renderProposalAndSurvey(res) {
  const prop = res.proposal || {};
  $("proposalReportBox").innerHTML = renderSimpleMarkdown(prop.markdown_report || "");

  const plan = prop.survey_plan || [];
  $("surveyPlanTableBody").innerHTML = plan.length
    ? plan
        .map(
          (p) => `
        <tr class="hover:bg-pink-50/40">
          <td class="p-3 font-bold text-slate-800">
            <div>${esc(p.location)}</div>
            <span class="inline-block mt-1 px-2 py-0.5 bg-pink-100 text-pink-700 rounded-full text-[10px] font-bold">${esc(p.priority_tag)}</span>
          </td>
          <td class="p-3 text-slate-600 font-medium">${(p.target_customer_segments || []).map(esc).join("; ")}</td>
          <td class="p-3 text-slate-600"><ul class="list-disc pl-4 space-y-0.5">${(p.information_to_verify || []).map((v) => `<li>${linkifyCitations(esc(v))}</li>`).join("")}</ul></td>
          <td class="p-3"><span class="px-2.5 py-1 bg-orange-50 text-orange-800 border border-orange-200 rounded-xl font-bold text-[11px]">${esc(p.go_no_go_criteria)}</span></td>
          <td class="p-3 font-bold text-pink-700">${esc(p.owner)}<div class="text-[10px] text-slate-400 font-semibold mt-0.5">${esc(p.expected_timeline)}</div></td>
        </tr>`
        )
        .join("")
    : `<tr><td colspan="5" class="p-6 text-center text-slate-400">${res.analysis_mode === "company_statistics" ? "Chế độ Thống kê tổng hợp công ty — xem đầy đủ ở mục 📄 Báo cáo (BC)." : "Chưa có kế hoạch khảo sát."}</td></tr>`;

  if (res.analysis_mode === "company_statistics" || prop.decision_status === "COMPANY_STATISTICS") {
    // Statistics mode has no survey plan: open the report (BC) directly, hide the survey toggle.
    $("btnPropSurvey")?.classList.add("hidden");
    switchProposalView("markdown");
  } else {
    $("btnPropSurvey")?.classList.remove("hidden");
    switchProposalView("survey");
  }
}

function renderProcessSteps(res) {
  const card = $("processStepsCard");
  const list = $("processStepsList");
  if (!card || !list) return;
  const steps = res.company_stats?.process_steps || [];
  if (!steps.length) {
    card.classList.add("hidden");
    return;
  }
  card.classList.remove("hidden");
  list.innerHTML = steps
    .map(
      (st, i) => `
      <li class="flex items-start gap-3 p-3 rounded-2xl bg-white/70 border border-white shadow-sm">
        <span class="w-7 h-7 shrink-0 rounded-full bg-gradient-to-br from-pink-400 to-orange-300 text-white text-[11px] font-extrabold flex items-center justify-center">${i + 1}</span>
        <div class="min-w-0">
          <div class="text-xs font-extrabold text-slate-800">${esc(String(st.title || "").replace(/^\d+\s*·\s*/, ""))} <span class="ml-1 px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 border border-emerald-200 text-[10px] font-extrabold">Xong</span></div>
          <div class="text-[11px] font-medium text-slate-600 leading-snug mt-0.5">${esc(st.detail)}</div>
        </div>
      </li>`
    )
    .join("");
}

function statsQualityIssues(cs) {
  const out = [];
  (cs.numeric_highlights || []).forEach((n) => {
    if (n.outlier_count) {
      out.push({
        location: n.table,
        issue_type: `Ngoại lai · ${n.column}`,
        severity: "MEDIUM",
        description: `${n.outlier_count} giá trị bất thường (${(n.outliers || []).join(", ")}) so với trung vị ${n.median}. Nên kiểm tra lại số liệu gốc.`,
      });
    }
    if (n.missing_count) {
      out.push({
        location: n.table,
        issue_type: `Thiếu dữ liệu · ${n.column}`,
        severity: n.missing_count >= n.count ? "HIGH" : "MEDIUM",
        description: `${n.missing_count} ô trống trong cột này (có ${n.count} ô hợp lệ).`,
      });
    }
  });
  return out;
}

function renderQualityTab(res) {
  renderCleanPreviewTable(res);
  renderProcessSteps(res);
  const ing = res.ingestion || {};
  const cs = res.company_stats || {};
  const dedups = (ing.dedup_log && ing.dedup_log.length) ? ing.dedup_log : (cs.dedup_log || []);
  const pnorms = ing.period_normalization_log || [];
  const issues = res.analysis_mode === "company_statistics" ? statsQualityIssues(cs) : (res.conflict_gap?.issues || []);

  $("dedupLogList").innerHTML = dedups.length
    ? dedups.map((d) => `<p class="bg-white/60 backdrop-blur-md p-3 rounded-2xl border border-white shadow-sm transition hover:-translate-y-0.5"><i class="fa-solid fa-check text-pink-600 mr-1.5"></i><strong>[${esc(d.dropped_record_id || d.table || "Trùng")}]</strong> — ${linkifyCitations(esc(d.reason || d.detail || "Đã loại bản ghi trùng"))}</p>`).join("")
    : `<p class="text-pink-700 font-bold"><i class="fa-solid fa-check mr-1.5"></i>Không có bản ghi trùng.</p>`;

  $("periodLogList").innerHTML = pnorms.length
    ? pnorms.map((p) => `<p class="bg-white/60 backdrop-blur-md p-3 rounded-2xl border border-white shadow-sm transition hover:-translate-y-0.5"><i class="fa-solid fa-clock-rotate-left text-orange-600 mr-1.5"></i><strong>${esc(p.location)}:</strong> '${esc(p.raw_period)}' → <code>${esc(p.normalized_period)}</code> (${esc(p.normalization_note)}) ${linkifyCitations(esc(p.citation_id))}</p>`).join("")
    : `<p class="text-slate-500 font-bold">Các kỳ đã đồng nhất.</p>`;

  if (res.analysis_mode === "company_statistics") {
    const unitNotes = (cs.numeric_highlights || []).filter((n) => n.unit_note);
    $("periodLogList").innerHTML = unitNotes.length
      ? unitNotes
          .map((n) => `<p class="bg-white/60 backdrop-blur-md p-3 rounded-2xl border border-white shadow-sm"><i class="fa-solid fa-scale-balanced text-orange-600 mr-1.5"></i><strong>${esc(n.table)} · ${esc(n.column)}:</strong> ${esc(n.unit_note)}</p>`)
          .join("")
      : `<p class="text-slate-500 font-bold">Đơn vị số liệu đã đồng nhất, không cần quy đổi.</p>`;
  }

  $("conflictLogList").innerHTML = issues.length
    ? issues
        .map(
          (it) => `
          <div class="p-3 rounded-2xl backdrop-blur-md border shadow-sm transition hover:-translate-y-0.5 ${it.severity === "HIGH" ? "bg-rose-50/75 border-white" : "bg-amber-50/75 border-white"}">
            <div class="font-bold text-slate-800">[${esc(it.location)}] ${esc(it.issue_type)}</div>
            <div class="mt-0.5 text-slate-600">${esc(it.description)}</div>
          </div>`
        )
        .join("")
    : `<p class="text-pink-700 font-bold"><i class="fa-solid fa-check mr-1.5"></i>Không có thiếu hoặc lệch nguồn.</p>`;
}

function renderAuditTab(res) {
  const audit = res.audit || {};
  const events = audit.events || [];
  const rules = audit.rules_trace || [];

  const uniqueTools = Array.from(new Set(events.filter((e) => e.tool_name).map((e) => e.tool_name)));
  $("toolsBadgeBar").innerHTML = uniqueTools
    .map((t) => `<span class="px-2.5 py-1 bg-pink-100 text-pink-800 border border-pink-200 rounded-full text-[10px] font-bold">✨ ${esc(t)}</span>`)
    .join("");

  $("toolsAuditLogs").innerHTML = events
    .map((ev) => {
      const hasIo = ev.tool_args || ev.tool_result_summary;
      const ioBox = hasIo
        ? `<details class="mt-1.5"><summary class="cursor-pointer text-pink-600 font-bold font-sans text-[11px]">Xem Input / Output</summary><pre class="mt-1 p-2.5 bg-white/75 backdrop-blur-md rounded-2xl border border-white overflow-x-auto max-h-40 text-[10px] text-slate-700">${esc(
            JSON.stringify({ args: ev.tool_args, result: ev.tool_result_summary }, null, 2)
          )}</pre></details>`
        : "";
      return `
        <div class="p-3.5 bg-white/55 backdrop-blur-md rounded-2xl border border-white shadow-sm space-y-1 transition hover:-translate-y-0.5">
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-slate-400 font-bold">#${ev.seq}</span>
            <span class="px-2 py-0.5 bg-white/80 text-pink-800 border border-white rounded-full text-[10px] font-bold">${esc(ev.actor)}</span>
            <strong class="text-slate-800">${esc(ev.action)}</strong>
            ${ev.tool_name ? `<code class="px-2 py-0.5 bg-orange-100/80 text-orange-800 border border-white rounded-lg font-bold">${esc(ev.tool_name)}</code>` : ""}
          </div>
          <p class="text-slate-600 font-sans">${linkifyCitations(esc(ev.detail))}</p>
          ${ioBox}
        </div>`;
    })
    .join("");

  $("rulesTraceBox").innerHTML = rules.length
    ? rules
        .map(
          (r) => `
          <div class="p-3.5 rounded-2xl backdrop-blur-md border shadow-sm transition hover:-translate-y-0.5 ${r.outcome === "FAIL" ? "bg-rose-50/75 border-white" : "bg-white/60 border-white"}">
            <div class="flex justify-between items-center font-bold text-slate-800">
              <span>[${esc(r.rule_id)}] ${esc(r.location)}</span>
              <span class="px-2.5 py-0.5 rounded-full text-[10px] font-extrabold border border-white ${
                r.outcome === "PASS" ? "bg-pink-100/80 text-pink-700" : r.outcome === "FAIL" ? "bg-rose-100/80 text-rose-700" : "bg-orange-100/80 text-orange-800"
              }">${esc(r.outcome)}</span>
            </div>
            <div class="text-slate-700 font-semibold mt-1">${esc(r.rule_name)} · Ngưỡng: <code>${esc(r.threshold)}</code></div>
            <div class="text-slate-500 mt-0.5">${esc(r.explanation)}</div>
          </div>`
        )
        .join("")
    : `<p class="text-slate-500 italic">Chưa có quy tắc kiểm tra.</p>`;
}

// --- MODALS & EXPORTS ---
function openCitationModal(citCode) {
  const c = state.lastResult?.audit?.citations?.[citCode];
  if (!c) return;
  $("citationTitle").innerText = `Chi tiết Nguồn Gốc [${citCode}]`;
  $("citationContent").innerHTML = `
    <p><strong>Địa bàn:</strong> ${esc(c.location)}</p>
    <p><strong>Bảng:</strong> ${esc(c.table_name)} · <strong>File/Sheet:</strong> ${esc(c.source_file)} / ${esc(c.sheet_name)} (Dòng ${c.row_number})</p>
    <p><strong>Nguồn:</strong> ${esc(c.source_name)} (${esc(c.report_period)})</p>
    <p class="mt-1"><strong>Giá trị gốc:</strong></p>
    <pre class="p-2.5 bg-white rounded-2xl border border-pink-100 overflow-x-auto font-mono text-[11px]">${esc(JSON.stringify(c.raw_value, null, 2))}</pre>
    ${c.note ? `<p class="text-pink-600 font-bold mt-1">Ghi chú: ${esc(c.note)}</p>` : ""}`;
  $("citationModal").classList.remove("hidden");
  $("citationModal").classList.add("flex");
}

function closeCitationModal() {
  $("citationModal").classList.remove("flex");
  $("citationModal").classList.add("hidden");
}

async function openColumnMappingModal() {
  const urls = ($("gsheetsUrl")?.value || "").trim();
  const larkUrls = ($("larkBaseUrl")?.value || "").trim();
  if (!state.files.length && !urls && !larkUrls && !state.selectedSampleId && !state.stagedId) {
    showToast("Vui lòng chọn dữ liệu trước khi mở Map cột!", true);
    return;
  }
  try {
    const fd = buildFormData();
    const resp = await fetch("/api/inspect-inputs", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "Không thể đọc cấu trúc bảng.");
    state.stagedId = data.staged_id;
    renderMappingModalContent(data);
    $("columnMappingModal").classList.remove("hidden");
    $("columnMappingModal").classList.add("flex");
  } catch (err) {
    showToast(err.message, true);
  }
}

function renderMappingModalContent(data) {
  const container = $("mappingFieldsContainer");
  const rows = data.sheet_assignments || [];
  const colMaps = data.column_maps || {};

  const tableOpts = (sel) =>
    `<option value="">-- Bỏ qua --</option>` +
    state.canonicalTables
      .map((t) => `<option value="${esc(t.key)}" ${t.key === sel ? "selected" : ""}>${esc(t.label)}</option>`)
      .join("");

  container.innerHTML = rows
    .map((r) => {
      const tbl = state.tableOverrides[r.sheet_name] || r.assigned_table;
      const meta = state.canonicalTables.find((t) => t.key === tbl);
      const curCols = { ...(colMaps[tbl] || {}), ...(state.columnOverrides[tbl] || {}) };
      const hdrOpts = (s) =>
        `<option value="">-- Tự động --</option>` +
        (r.headers || []).map((h) => `<option value="${esc(h)}" ${h === s ? "selected" : ""}>${esc(h)}</option>`).join("");

      const colGrid = meta
        ? `<details class="mt-2"><summary class="cursor-pointer text-pink-600 font-bold">Tùy chỉnh cột (${meta.fields.length})</summary><div class="grid grid-cols-2 gap-2 mt-2">${meta.fields
            .map(
              (f) => `
            <div>
              <div class="text-[10px] font-mono text-slate-500 font-bold">${esc(f)}</div>
              <select class="cute-input w-full px-2 py-1 rounded-xl col-override-sel" data-table="${esc(tbl)}" data-field="${esc(f)}">${hdrOpts(curCols[f] || "")}</select>
            </div>`
            )
            .join("")}</div></details>`
        : "";

      return `
        <div class="p-3 bg-pink-50/50 rounded-2xl border border-pink-100">
          <div class="flex items-center justify-between gap-2">
            <div><strong class="text-slate-800">${esc(r.sheet_name)}</strong> <span class="text-slate-500 font-semibold">(${r.row_count} dòng)</span></div>
            <select class="cute-input px-2.5 py-1.5 rounded-xl text-xs font-bold table-override-sel" data-sheet="${esc(r.sheet_name)}">${tableOpts(tbl)}</select>
          </div>
          ${colGrid}
        </div>`;
    })
    .join("");

  container.querySelectorAll(".table-override-sel").forEach((sel) => {
    sel.addEventListener("change", () => {
      if (sel.value) state.tableOverrides[sel.dataset.sheet] = sel.value;
      else delete state.tableOverrides[sel.dataset.sheet];
      renderMappingModalContent(data);
    });
  });

  container.querySelectorAll(".col-override-sel").forEach((sel) => {
    sel.addEventListener("change", () => {
      const t = sel.dataset.table;
      const f = sel.dataset.field;
      if (!state.columnOverrides[t]) state.columnOverrides[t] = {};
      if (sel.value) state.columnOverrides[t][f] = sel.value;
      else delete state.columnOverrides[t][f];
    });
  });
}

function closeColumnMappingModal() {
  $("columnMappingModal").classList.remove("flex");
  $("columnMappingModal").classList.add("hidden");
}

async function saveColumnMapping() {
  closeColumnMappingModal();
  showToast("Đã cập nhật ánh xạ cột! Đang chạy lại Agent...");
  await runAIAgentWorkflow();
}

async function exportHTML() {
  if (!state.lastResult) {
    showToast("Vui lòng chạy Agent trước khi xuất HTML!", true);
    return;
  }
  const ok = await askUserConfirm({
    title: "🌐 Xác nhận xuất báo cáo HTML",
    message: "Bạn có muốn tải xuống báo cáo Dashboard tương tác (.html) không?",
    confirmText: "Có, tải xuống ✓",
  });
  if (ok) window.location.href = `/api/runs/${encodeURIComponent(state.lastResult.run_id)}/report.html`;
}

async function exportCleanedExcel() {
  if (!state.lastResult) {
    showToast("Vui lòng chạy phân tích trước khi tải Excel dữ liệu sạch!", true);
    return;
  }
  const ok = await askUserConfirm({
    title: "📗 Xác nhận tải Excel dữ liệu sạch",
    message: "Bạn có muốn tải xuống file Excel dữ liệu đã làm sạch (.xlsx) không?",
    confirmText: "Có, tải xuống ✓",
  });
  if (ok) window.location.href = `/api/runs/${encodeURIComponent(state.lastResult.run_id)}/cleaned.xlsx`;
}

async function exportAnalysisExcel() {
  if (!state.lastResult) {
    showToast("Vui lòng chạy phân tích trước khi tải Excel tổng hợp & biểu đồ!", true);
    return;
  }
  const ok = await askUserConfirm({
    title: "📊 Xác nhận tải Excel tổng hợp",
    message: "Bạn có muốn tải xuống file Excel phân tích & biểu đồ (.xlsx) không?",
    confirmText: "Có, tải xuống ✓",
  });
  if (ok) window.location.href = `/api/runs/${encodeURIComponent(state.lastResult.run_id)}/analysis.xlsx`;
}

async function exportReportDocx() {
  if (!state.lastResult) {
    showToast("Vui lòng chạy phân tích trước khi tải Báo cáo Word (.docx)!", true);
    return;
  }
  const ok = await askUserConfirm({
    title: "📘 Xác nhận tải Báo cáo Word",
    message: "Bạn có muốn tải xuống Báo cáo Word (.docx) không?",
    confirmText: "Có, tải xuống ✓",
  });
  if (ok) window.location.href = `/api/runs/${encodeURIComponent(state.lastResult.run_id)}/report.docx`;
}

async function exportMarkdown() {
  if (!state.lastResult) {
    showToast("Vui lòng chạy Agent trước khi xuất!", true);
    return;
  }
  const ok = await askUserConfirm({
    title: "📝 Xác nhận tải Markdown",
    message: "Bạn có muốn tải xuống file Báo cáo Markdown (.md) không?",
    confirmText: "Có, tải xuống ✓",
  });
  if (ok) window.location.href = `/api/runs/${encodeURIComponent(state.lastResult.run_id)}/report.md`;
}

async function exportAuditJSON() {
  if (!state.lastResult) {
    showToast("Vui lòng chạy Agent trước khi xuất!", true);
    return;
  }
  const ok = await askUserConfirm({
    title: "🧾 Xác nhận tải Audit Log JSON",
    message: "Bạn có muốn tải xuống nhật ký kiểm toán dữ liệu (.json) không?",
    confirmText: "Có, tải xuống ✓",
  });
  if (ok) window.location.href = `/api/runs/${encodeURIComponent(state.lastResult.run_id)}/audit`;
}

async function copyMarkdownReport() {
  const md = state.lastResult?.proposal?.markdown_report;
  if (!md) {
    showToast("Chưa có báo cáo Markdown để sao chép.", true);
    return;
  }
  try {
    await navigator.clipboard.writeText(md);
    showToast("Đã sao chép Báo cáo Markdown vào bộ nhớ tạm!");
  } catch {
    showToast("Không thể copy tự động; hãy dùng nút Xuất .MD.", true);
  }
}

document.addEventListener("click", (e) => {
  const menu = $("exportMenu");
  const btn = $("btnExportMenu");
  if (menu && btn && !menu.contains(e.target) && !btn.contains(e.target)) {
    menu.classList.add("hidden");
  }
});

document.addEventListener("DOMContentLoaded", async () => {
  const dz = $("dropZone");
  if (dz) {
    dz.addEventListener("dragover", (e) => {
      e.preventDefault();
      dz.classList.add("bg-pink-100/70", "border-pink-400");
    });
    dz.addEventListener("dragleave", () => dz.classList.remove("bg-pink-100/70", "border-pink-400"));
    dz.addEventListener("drop", (e) => {
      e.preventDefault();
      dz.classList.remove("bg-pink-100/70", "border-pink-400");
      handleFileUpload({ target: { files: e.dataTransfer.files } });
    });
  }

  const rdz = $("resubmitDropZone");
  if (rdz) {
    rdz.addEventListener("dragover", (e) => {
      e.preventDefault();
      rdz.classList.add("bg-rose-100/80", "border-rose-400");
    });
    rdz.addEventListener("dragleave", () => rdz.classList.remove("bg-rose-100/80", "border-rose-400"));
    rdz.addEventListener("drop", (e) => {
      e.preventDefault();
      rdz.classList.remove("bg-rose-100/80", "border-rose-400");
      handleInlineResubmitFiles({ target: { files: e.dataTransfer.files } });
    });
  }

  // iOS 27 Spatial Swipe (touch + pointer horizontal drag) & Keyboard Arrow Navigation
  const viewport = $("spatialViewport");
  if (viewport) {
    let startX = null;
    let startY = null;
    const isInteractiveEl = (target) =>
      Boolean(target && target.closest("input, textarea, select, button, summary, table, pre, a, .overflow-x-auto, [data-no-swipe], #chatPanel, #infoModal"));

    viewport.addEventListener(
      "touchstart",
      (e) => {
        if (e.touches.length !== 1 || isInteractiveEl(e.target)) {
          startX = null;
          return;
        }
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
      },
      { passive: true }
    );
    viewport.addEventListener(
      "touchend",
      (e) => {
        if (startX === null || e.changedTouches.length !== 1) return;
        const dx = e.changedTouches[0].clientX - startX;
        const dy = e.changedTouches[0].clientY - startY;
        startX = null;
        startY = null;
        if (Math.abs(dx) >= 75 && Math.abs(dx) > Math.abs(dy) * 1.4) {
          if (dx < 0) swipeNextScene();
          else swipePrevScene();
        }
      },
      { passive: true }
    );

    viewport.addEventListener("pointerdown", (e) => {
      if (e.pointerType !== "mouse" || e.button !== 0 || isInteractiveEl(e.target)) return;
      startX = e.clientX;
      startY = e.clientY;
    });
    viewport.addEventListener("pointerup", (e) => {
      if (e.pointerType !== "mouse" || startX === null) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      startX = null;
      startY = null;
      if (Math.abs(dx) >= 90 && Math.abs(dx) > Math.abs(dy) * 1.5) {
        if (dx < 0) swipeNextScene();
        else swipePrevScene();
      }
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    if (e.key === "Escape") {
      if (typeof window.closeInfoModal === "function") window.closeInfoModal();
      if (typeof window.closeChat === "function") window.closeChat();
      return;
    }
    if (state.currentScene === 0) {
      // On the home page the arrow keys drive the banner slider
      if (window.heroSlider && e.key === "ArrowRight") window.heroSlider.next(true);
      else if (window.heroSlider && e.key === "ArrowLeft") window.heroSlider.prev(true);
      return;
    }
    if (e.key === "ArrowRight") swipeNextScene();
    else if (e.key === "ArrowLeft") swipePrevScene();
  });

  goToScene(0, "", { silent: true });
  resetWorkflowUI();

  try {
    const resp = await fetch("/api/health");
    const data = await resp.json();
    state.canonicalTables = data.canonical_tables || [];
    if (data.has_gemini_key) {
      $("agentMode").value = data.default_agent_mode || "gemini";
      $("llmModel").value = data.default_gemini_model || "gemini-2.5-flash";
      onAgentModeChange();
      const notice = $("serverKeyNotice");
      if (notice) {
        notice.textContent =
          data.gemini_key_mode === "vertex_express"
            ? "✓ Đã tích hợp API Key trên server (Vertex AI Express)"
            : "✓ Đã tích hợp API Key trên server (Gemini API)";
        notice.classList.remove("hidden");
      }
    }
    updateSampleButtonStyles(1);
  } catch (err) {
    showErrorBanner("Không thể kết nối server", err.message);
  }
});
