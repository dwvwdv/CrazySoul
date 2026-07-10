"use strict";

// ---- API 小工具 ----
async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(path, opts);
  let data = null;
  try { data = await resp.json(); } catch (_) {}
  if (!resp.ok) {
    const detail = (data && data.detail) || resp.statusText;
    const err = new Error(detail);
    err.status = resp.status;
    throw err;
  }
  return data;
}

// 輪詢一個非同步任務直到完成
async function pollJob(jid, onTick) {
  while (true) {
    const j = await api("GET", `/api/jobs/${jid}`);
    if (onTick) onTick(j);
    if (j.status === "done") return j.result || {};
    if (j.status === "error") throw new Error(j.error || "任務失敗");
    await new Promise((r) => setTimeout(r, 800));
  }
}

const $ = (id) => document.getElementById(id);
let currentPid = null;
let currentProject = null;  // 最近一次載入的專案(給分鏡渲染角色清單用)

// ---- 啟動 ----
async function init() {
  const me = await api("GET", "/api/me");
  $("mode-tag").textContent = me.dry_run ? "DRY-RUN" : "LIVE";
  if (me.authed) {
    enterApp(me);
  } else {
    $("login-view").classList.remove("hidden");
    $("app-view").classList.add("hidden");
  }
}

function enterApp(me) {
  $("login-view").classList.add("hidden");
  $("app-view").classList.remove("hidden");
  $("logout-btn").classList.remove("hidden");
  $("warn-banner").classList.toggle("hidden", !me.default_password);
  $("dry-banner").classList.toggle("hidden", !me.dry_run);
}

// ---- 登入 / 登出 ----
$("login-btn").addEventListener("click", async () => {
  $("login-error").textContent = "";
  try {
    await api("POST", "/api/login", { password: $("pw").value });
    const me = await api("GET", "/api/me");
    enterApp(me);
  } catch (e) {
    $("login-error").textContent = e.message;
  }
});
$("pw").addEventListener("keydown", (e) => { if (e.key === "Enter") $("login-btn").click(); });
$("logout-btn").addEventListener("click", async () => {
  await api("POST", "/api/logout");
  location.reload();
});

// ---- 建立專案 → 產生分鏡 ----
$("create-btn").addEventListener("click", async () => {
  const prompt = $("prompt").value.trim();
  if (!prompt) { $("create-status").textContent = "請先輸入主題。"; return; }
  const shots = parseInt($("shots").value, 10) || 3;
  const pct = parseInt($("dynamic-ratio").value, 10);
  const dynamic_ratio = Number.isFinite(pct) ? Math.min(1, Math.max(0, pct / 100)) : 1;
  const btn = $("create-btn");
  btn.disabled = true;
  $("create-status").textContent = "產生分鏡中…";
  try {
    const { pid, job } = await api("POST", "/api/projects", { prompt, shots, dynamic_ratio });
    currentPid = pid;
    await pollJob(job);
    $("create-status").textContent = "";
    await loadProject();
  } catch (e) {
    $("create-status").innerHTML = `<span class="error">${e.message}</span>`;
  } finally {
    btn.disabled = false;
  }
});

// ---- 載入並渲染專案 ----
async function loadProject() {
  if (!currentPid) return;
  const p = await api("GET", `/api/projects/${currentPid}`);
  renderProject(p);
}

function renderProject(p) {
  currentProject = p;
  $("project").classList.remove("hidden");
  $("project-title").textContent = p.title || p.prompt;
  const dynPct = Math.round((p.dynamic_ratio ?? 1) * 100);
  const dynCount = p.shots.filter((s) => s.route === "video").length;
  $("project-meta").textContent =
    `${p.shots.length} 個分鏡 · 動態上限 ${dynPct}%(${dynCount} 動態 / ${p.shots.length - dynCount} 靜態）· 估算成本 $${p.total_cost_usd}`;

  renderCharacters(p.characters || []);

  const container = $("shots-container");
  container.innerHTML = "";
  for (const s of p.shots) container.appendChild(renderShot(s));

  // 全部分鏡選完影片 → 顯示合成區
  $("finalize").classList.toggle("hidden", !p.all_done);
  if (p.final_video) {
    $("final-block").classList.remove("hidden");
    $("final-video").src = p.final_video;
  }
  $("save-status").textContent = p.saved_to_pcloud ? "已保存至 pCloud ✓" : "";
}

// ---- Phase 2:角色庫 ----
function renderCharacters(chars) {
  const list = $("characters-list");
  list.innerHTML = "";
  if (!chars.length) {
    list.innerHTML = `<span class="muted" style="font-size:13px">尚無角色。新增後可在各分鏡標記出場,生圖會自動帶入一致性。</span>`;
    return;
  }
  for (const c of chars) {
    const chip = document.createElement("div");
    chip.className = "char-chip";
    const thumb = c.ref_image ? `<img src="${c.ref_image}" alt="${c.name}" />` : "";
    const bits = [c.style_tag, c.seed != null ? `seed ${c.seed}` : ""].filter(Boolean).join(" · ");
    chip.innerHTML = `${thumb}<span class="char-name">${c.name}</span>${bits ? `<span class="muted char-meta">${bits}</span>` : ""}`;
    list.appendChild(chip);
  }
}

$("add-char-btn").addEventListener("click", async () => {
  const name = $("char-name").value.trim();
  if (!name) { $("char-status").textContent = "請先輸入角色名。"; return; }
  const fd = new FormData();
  fd.append("name", name);
  fd.append("style_tag", $("char-style").value.trim());
  fd.append("seed", $("char-seed").value.trim());
  const f = $("char-file").files[0];
  if (f) fd.append("file", f);
  $("char-status").textContent = "新增中…";
  try {
    const resp = await fetch(`/api/projects/${currentPid}/characters`, { method: "POST", body: fd });
    if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).detail || resp.statusText);
    $("char-name").value = ""; $("char-style").value = ""; $("char-seed").value = ""; $("char-file").value = "";
    $("char-status").textContent = "已新增 ✓";
    await loadProject();
  } catch (e) {
    $("char-status").innerHTML = `<span class="error">${e.message}</span>`;
  }
});

// 分鏡的出場角色勾選(多選)
function shotCharacterPicker(s) {
  const chars = (currentProject && currentProject.characters) || [];
  const box = document.createElement("div");
  box.className = "shot-chars";
  if (!chars.length) return box;  // 沒有角色就不顯示
  const assigned = new Set(s.characters || []);
  const chips = chars
    .map(
      (c) =>
        `<label class="char-check"><input type="checkbox" data-act="toggle-char" data-idx="${s.index}" data-name="${c.name}" ${assigned.has(c.name) ? "checked" : ""}/> ${c.name}</label>`
    )
    .join("");
  box.innerHTML = `<span class="muted" style="font-size:12px">出場角色:</span>${chips}`;
  return box;
}

function renderShot(s) {
  const wrap = document.createElement("div");
  wrap.className = "shot";
  const stageLabel = {
    need_images: "待生成圖片",
    awaiting_image_pick: "待挑選圖片",
    need_videos: "待生成影片",
    awaiting_video_pick: "待挑選影片",
    done: "已完成",
  }[s.stage] || s.stage;

  // Phase 1:分流路徑徽章 + 手動覆寫(video=動態付費 / motion=靜態省成本)
  const isVideo = s.route === "video";
  const routeLabel = isVideo ? "動態 · Video" : "靜態 · Motion";
  const otherRoute = isVideo ? "motion" : "video";
  const switchLabel = isVideo ? "改走靜態" : "改走動態";
  // 已開始生成影片後就鎖定路徑,避免與既有候選不一致
  const routeLocked = ["awaiting_video_pick", "done"].includes(s.stage);

  wrap.innerHTML = `
    <div class="shot-head">
      <span class="idx">分鏡 ${s.index + 1}</span>
      <span class="idx">${s.shot_type}</span>
      <span class="route ${isVideo ? "video" : "motion"}" title="needs_motion=${s.needs_motion}">${routeLabel}</span>
      ${routeLocked ? "" : `<button class="ghost route-switch" data-act="set-route" data-idx="${s.index}" data-route="${otherRoute}">${switchLabel}</button>`}
      <span class="stage ${s.stage === "done" ? "done" : ""}">${stageLabel}</span>
    </div>
    <div class="desc">${s.description}</div>
  `;

  // Phase 2:出場角色勾選(影響下一次生圖)
  wrap.appendChild(shotCharacterPicker(s));

  // 圖片區
  if (s.stage === "need_images") {
    wrap.appendChild(genControls("圖片", s.index, "gen-images", 4));
  } else {
    wrap.appendChild(candWall(s.image_candidates, "image", s.index, "pick-image", s.selected_image));
    if (s.stage === "awaiting_image_pick") {
      wrap.appendChild(genControls("圖片(重生)", s.index, "gen-images", 4, "secondary"));
    }
  }

  // 影片區(需先選好圖)
  if (["need_videos", "awaiting_video_pick", "done"].includes(s.stage)) {
    if (s.stage === "need_videos") {
      wrap.appendChild(genControls("影片", s.index, "gen-videos", 3));
    } else {
      wrap.appendChild(candWall(s.video_candidates, "video", s.index, "pick-video", s.selected_video));
      if (s.stage === "awaiting_video_pick") {
        wrap.appendChild(genControls("影片(重生)", s.index, "gen-videos", 3, "secondary"));
      }
    }
  }
  return wrap;
}

function genControls(label, idx, act, defCount, btnClass = "") {
  const row = document.createElement("div");
  row.className = "row";
  row.style.marginTop = "10px";
  row.innerHTML = `
    <div>
      <label>${label} 張數</label>
      <input type="number" id="count-${act}-${idx}" value="${defCount}" min="1" max="8" />
    </div>
    <button class="${btnClass}" data-act="${act}" data-idx="${idx}">生成 ${label}</button>
    <span class="status-line" id="status-${act}-${idx}"></span>
  `;
  return row;
}

function candWall(cands, kind, idx, act, selected) {
  const wall = document.createElement("div");
  wall.className = "wall";
  cands.forEach((c, i) => {
    const b = document.createElement("button");
    b.className = "cand" + (c.cid === selected ? " selected" : "");
    b.dataset.act = act;
    b.dataset.idx = idx;
    b.dataset.cid = c.cid;
    const media = kind === "image"
      ? `<img src="${c.url}" alt="候選${i + 1}" />`
      : `<video src="${c.url}" muted loop autoplay playsinline></video>`;
    const hint = c.cid === selected ? "已選 ✓" : `候選 ${i + 1}`;
    b.innerHTML = `${media}<span class="pick-hint">${hint}</span>`;
    wall.appendChild(b);
  });
  return wall;
}

// ---- 分鏡區的事件委派 ----
$("shots-container").addEventListener("click", async (e) => {
  const t = e.target.closest("[data-act]");
  if (!t) return;
  const act = t.dataset.act;
  const idx = parseInt(t.dataset.idx, 10);

  try {
    if (act === "gen-images" || act === "gen-videos") {
      const count = parseInt($(`count-${act}-${idx}`).value, 10) || 3;
      const status = $(`status-${act}-${idx}`);
      status.textContent = "生成中…";
      t.disabled = true;
      const kind = act === "gen-images" ? "images" : "videos";
      const { job } = await api("POST", `/api/projects/${currentPid}/shots/${idx}/${kind}`, { count });
      await pollJob(job);
      await loadProject();
    } else if (act === "pick-image" || act === "pick-video") {
      const kind = act === "pick-image" ? "select_image" : "select_video";
      await api("POST", `/api/projects/${currentPid}/shots/${idx}/${kind}`, { cid: t.dataset.cid });
      await loadProject();
    } else if (act === "set-route") {
      await api("POST", `/api/projects/${currentPid}/shots/${idx}/route`, { route: t.dataset.route });
      await loadProject();
    }
  } catch (err) {
    alert(err.message);
    await loadProject();
  }
});

// 出場角色勾選(checkbox 用 change 事件)
$("shots-container").addEventListener("change", async (e) => {
  const t = e.target.closest("[data-act='toggle-char']");
  if (!t) return;
  const idx = parseInt(t.dataset.idx, 10);
  // 收集這個分鏡目前所有勾選的角色
  const boxes = t.closest(".shot-chars").querySelectorAll("input[type=checkbox]");
  const names = [...boxes].filter((b) => b.checked).map((b) => b.dataset.name);
  try {
    await api("POST", `/api/projects/${currentPid}/shots/${idx}/characters`, { names });
    await loadProject();
  } catch (err) {
    alert(err.message);
    await loadProject();
  }
});

// ---- 合成 / 保存 ----
$("compose-btn").addEventListener("click", async () => {
  const btn = $("compose-btn");
  btn.disabled = true;
  $("compose-status").textContent = "合成中…";
  try {
    const { job } = await api("POST", `/api/projects/${currentPid}/compose`);
    await pollJob(job);
    $("compose-status").textContent = "完成 ✓";
    await loadProject();
  } catch (e) {
    $("compose-status").innerHTML = `<span class="error">${e.message}</span>`;
  } finally {
    btn.disabled = false;
  }
});

$("save-btn").addEventListener("click", async () => {
  $("save-status").textContent = "保存中…";
  try {
    const r = await api("POST", `/api/projects/${currentPid}/save_pcloud`);
    $("save-status").textContent = `已保存至 pCloud ✓（${r.note}）`;
  } catch (e) {
    $("save-status").innerHTML = `<span class="error">${e.message}</span>`;
  }
});

init().catch((e) => {
  document.body.innerHTML = `<main><div class="card error">初始化失敗:${e.message}</div></main>`;
});
