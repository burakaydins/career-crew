"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};

let config = { agents: {}, mode: "mock", max_mb: 10 };
let runId = null;
let source = null;
let lastEventId = -1;
let iteration = 0;
let originalCv = "";
let latestCv = "";

const ACCEPTED = [".md", ".txt", ".pdf", ".docx", ".png", ".jpg", ".jpeg"];
const AGENT_LABEL = { cv_writer: "CV Yazarı", letter_writer: "Mektup Yazarı", interviewer: "Mülakatçı" };
const BADGES = { paused: "duraklatıldı", pending: "bekliyor", working: "çalışıyor", done: "tamam", waiting: "onay bekliyor", rejected: "ret", failed: "hata", issue: "sorun var" };

// ---- theme -----------------------------------------------------------------
function applyTheme(t) {
  if (t) document.documentElement.setAttribute("data-theme", t);
  else document.documentElement.removeAttribute("data-theme");
}
try { applyTheme(localStorage.getItem("theme")); } catch (_) { /* storage can be blocked */ }
$("#theme-btn").addEventListener("click", () => {
  const dark = document.documentElement.getAttribute("data-theme") === "dark" ||
    (!document.documentElement.getAttribute("data-theme") && matchMedia("(prefers-color-scheme: dark)").matches);
  const next = dark ? "light" : "dark";
  applyTheme(next);
  try { localStorage.setItem("theme", next); } catch (_) { /* ignore */ }
});

// ---- upload form -----------------------------------------------------------
const picked = { ilan: null, cv: null };

function fmtSize(n) { return n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB"; }

function validateFile(file) {
  const ext = "." + file.name.split(".").pop().toLowerCase();
  if (!ACCEPTED.includes(ext)) return `Desteklenmeyen dosya türü: ${file.name}`;
  if (file.size > config.max_mb * 1048576) return `${file.name} çok büyük (${fmtSize(file.size)}), sınır ${config.max_mb} MB`;
  if (file.size === 0) return `${file.name} boş`;
  return null;
}

function showError(msg) {
  const box = $("#form-error");
  box.textContent = msg || "";
  box.hidden = !msg;
}

function setPicked(card, kind, file) {
  const err = file ? validateFile(file) : null;
  if (err) { showError(err); return; }
  showError("");
  picked[kind] = file;
  const label = $(".dz-file", card);
  label.hidden = !file;
  label.textContent = file ? `${file.name} (${fmtSize(file.size)})` : "";
  $(".clear-file", card).hidden = !file;
}

document.querySelectorAll(".drop-card").forEach((card) => {
  const kind = card.dataset.kind;
  const zone = $(".dropzone", card);
  const input = $("input[type=file]", card);
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  input.addEventListener("change", () => { if (input.files[0]) setPicked(card, kind, input.files[0]); input.value = ""; });
  ["dragenter", "dragover"].forEach((t) => zone.addEventListener(t, (e) => { e.preventDefault(); zone.classList.add("over"); }));
  ["dragleave", "drop"].forEach((t) => zone.addEventListener(t, (e) => { e.preventDefault(); zone.classList.remove("over"); }));
  zone.addEventListener("drop", (e) => { const f = e.dataTransfer.files[0]; if (f) setPicked(card, kind, f); });
  $(".clear-file", card).addEventListener("click", () => setPicked(card, kind, null));
});
// A file dropped outside a zone would make the browser navigate away from the page.
["dragover", "drop"].forEach((t) => window.addEventListener(t, (e) => e.preventDefault()));

$("#form").addEventListener("submit", async (e) => {
  e.preventDefault();
  showError("");
  const fd = new FormData();
  for (const [kind, label] of [["ilan", "İlan"], ["cv", "CV"]]) {
    const text = $(`#${kind}-text`).value.trim();
    if (picked[kind]) fd.append(`${kind}_file`, picked[kind]);
    else if (text) fd.append(`${kind}_text`, text);
    else { showError(`${label} eksik: dosya yükle ya da metin yapıştır`); return; }
  }
  fd.append("lang", $("#lang").value);
  fd.append("auto_yes", $("#auto-yes").checked ? "1" : "0");
  fd.append("pdf", $("#pdf").checked ? "1" : "0");
  const btn = $("#go");
  btn.disabled = true;
  try {
    const res = await fetch("/api/runs", { method: "POST", body: fd });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `Sunucu hatası (${res.status})`);
    startRun(body.id);
  } catch (err) {
    showError(err.message);
  } finally {
    btn.disabled = false;
  }
});

// ---- steps -----------------------------------------------------------------
const STEPS = [
  { id: "read", label: "Dosyaları oku" },
  { id: "analyze", label: "İlanı analiz et", skill: "analyze_job" },
  { id: "gate", label: "İlan onayı" },
  { id: "tailor", label: "CV'yi uyarla", skill: "tailor_cv", loop: true },
  { id: "checks", label: "Kod kontrolleri", loop: true },
  { id: "verify", label: "Doğrulama", skill: "verify", loop: true },
  { id: "score", label: "Puanlama", skill: "score", loop: true },
  { id: "letter", label: "Ön yazı", skill: "write_letter" },
  { id: "interview", label: "Mülakat hazırlığı", skill: "prepare_interview" },
  { id: "report", label: "Rapor" },
];
const stepBySkill = Object.fromEntries(STEPS.filter((s) => s.skill).map((s) => [s.skill, s.id]));

function buildSteps() {
  const ol = $("#steps");
  ol.replaceChildren();
  for (const s of STEPS) {
    const li = el("li", "step");
    li.id = "step-" + s.id;
    li.dataset.s = "pending";
    li.append(el("span", "", s.label), el("span", "badge", BADGES.pending));
    ol.append(li);
  }
}

function setStep(id, state, badge) {
  const li = $("#step-" + id);
  if (!li) return;
  li.dataset.s = state === "issue" ? "rejected" : state;
  $(".badge", li).textContent = badge || BADGES[state];
}

// ---- chat ------------------------------------------------------------------
const chat = $("#chat");
function scrollChat() { chat.lastElementChild?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }

function agentInfo(name) {
  if (name === "code") return { name: "🧮 Kod kontrolü", color: "var(--muted)" };
  return config.agents[name] || { name: name || "", color: "var(--muted)" };
}

function bubble(agent, text, cls) {
  const info = agentInfo(agent);
  const m = el("div", "msg" + (cls ? " " + cls : ""));
  m.style.setProperty("--c", info.color);
  const who = el("div", "who");
  who.append(el("span", "dot"), el("span", "", info.name));
  m.append(who, el("p", "", text));
  chat.append(m);
  scrollChat();
  return m;
}

function divider(text) { chat.append(el("div", "divider", text)); scrollChat(); }

const workingBubbles = {};
function clearWorking(agent) {
  workingBubbles[agent]?.remove();
  delete workingBubbles[agent];
}

// ---- job gate --------------------------------------------------------------
let openGate = null;  // close() of the gate card that still waits for an answer

function renderGate(job, auto) {
  // A new review means the previous one was answered with a correction.
  if (openGate) openGate("Düzeltme gönderildi, ilan yeniden okunuyor.");
  const g = el("div", "gate");
  g.append(el("h3", "", auto ? "İlan okuması (otomatik onaylandı)" : "İlan doğru okundu mu?"));
  const dl = el("dl");
  const rows = [
    ["Pozisyon", job.title], ["Şirket", job.company], ["Seviye", job.level],
    ["Zorunlu", (job.required_skills || []).join(", ")], ["Tercih", (job.preferred_skills || []).join(", ")],
    ["Anahtar kelimeler", (job.keywords || []).join(", ")],
  ];
  for (const [k, v] of rows) { dl.append(el("dt", "", k), el("dd", "", v || "–")); }
  g.append(dl);
  if (!auto) {
    const actions = el("div", "actions");
    const ok = el("button", "primary", "Doğru, devam et");
    const fix = el("button", "secondary", "Düzelt");
    actions.append(ok, fix);
    const box = el("div"); box.hidden = true;
    const ta = el("textarea"); ta.rows = 3; ta.placeholder = "Neyi düzeltelim?";
    ta.setAttribute("aria-label", "Düzeltme");
    const send = el("button", "primary", "Düzeltmeyi gönder");
    box.append(ta, send);
    g.append(actions, box);
    const err = el("p", "error"); err.hidden = true; g.append(err);
    const closeGate = (text) => {
      if (openGate !== closeGate) return;
      openGate = null;
      g.classList.add("closed");
      actions.hidden = box.hidden = true;
      g.append(el("p", "hint", text));
    };
    openGate = closeGate;
    const answer = async (payload) => {
      ok.disabled = fix.disabled = send.disabled = true;
      try {
        const res = await fetch(`/api/runs/${runId}/gate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(body.detail || `Hata (${res.status})`);
        closeGate(payload.action === "approve" ? "Onaylandı." : "Düzeltme gönderildi, ilan yeniden okunuyor.");
      } catch (e2) {
        err.textContent = e2.message; err.hidden = false;
        ok.disabled = fix.disabled = send.disabled = false;
      }
    };
    ok.addEventListener("click", () => answer({ action: "approve" }));
    fix.addEventListener("click", () => { box.hidden = false; ta.focus(); });
    send.addEventListener("click", () => { if (ta.value.trim()) answer({ action: "correct", text: ta.value.trim() }); else { err.textContent = "Neyin düzeltileceğini yaz"; err.hidden = false; } });
  }
  chat.append(g);
  scrollChat();
  if (!auto) ($("button", g)).focus({ preventScroll: true });
}

// ---- documents and scores --------------------------------------------------
function renderDoc(pre, text, other, cls) {
  const set = new Set(other.split("\n").map((l) => l.trim()).filter(Boolean));
  pre.replaceChildren();
  for (const line of text.split("\n")) {
    const span = el("span", "l" + (line.trim() && !set.has(line.trim()) ? " " + cls : ""), line || " ");
    pre.append(span);
  }
}

function renderCompare() {
  renderDoc($("#cv-before"), originalCv, latestCv, "del");
  renderDoc($("#cv-after"), latestCv, originalCv, "add");
}

async function getText(path) {
  const res = await fetch(`/api/runs/${runId}${path}`);
  return res.ok ? res.text() : null;
}

function setAts(which, value) {
  const n = parseFloat(value);
  if (Number.isNaN(n)) return;
  $(`#ats-${which}`).style.width = Math.min(100, n) + "%";
  $(`#ats-${which}-t`).textContent = "%" + n;
}

function openViewer(title, node) {
  $("#viewer-title").textContent = title;
  $("#viewer-body").replaceChildren(node);
  const d = $("#viewer");
  if (!d.open) d.showModal();
}
$("#viewer-close").addEventListener("click", () => $("#viewer").close());
$("#viewer").addEventListener("click", (e) => { if (e.target === $("#viewer")) $("#viewer").close(); });

$("#expand").addEventListener("click", () => {
  const wrap = el("div", "compare");
  for (const [title, id] of [["Orijinal", "cv-before"], ["Uyarlanmış", "cv-after"]]) {
    const col = el("div"); col.append(el("h3", "", title));
    const pre = el("pre", "doc"); pre.append(...$("#" + id).cloneNode(true).childNodes);
    col.append(pre); wrap.append(col);
  }
  openViewer("CV: önce / sonra", wrap);
});

async function loadFiles() {
  const res = await fetch(`/api/runs/${runId}/files`);
  if (!res.ok) return;
  const files = (await res.json()).filter((f) => f.folder === "output");
  const ul = $("#files");
  ul.replaceChildren();
  for (const f of files) {
    const li = el("li");
    const isPdf = f.name.endsWith(".pdf");
    const view = isPdf ? el("a", "", f.name) : el("button", "", f.name);
    if (isPdf) { view.href = `/api/runs/${runId}/files/${f.folder}/${f.name}`; view.target = "_blank"; view.rel = "noopener"; }
    else {
      view.type = "button";
      view.addEventListener("click", async () => {
        const text = await getText(`/files/${f.folder}/${f.name}`);
        const pre = el("pre", "doc"); pre.textContent = text || "";
        openViewer(f.name, pre);
      });
    }
    const dl = el("a", "", "indir");
    dl.href = `/api/runs/${runId}/files/${f.folder}/${f.name}?download=1`;
    dl.setAttribute("download", f.name);
    li.append(view, dl);
    ul.append(li);
  }
  if (!files.length) ul.append(el("li", "hint", "Dosya üretilmedi."));
}

async function finish(data) {
  $("#new-run").hidden = false;
  if (data) $("#score-val").textContent = data.score;
  const final = await getText("/files/output/cv.md");
  if (final) { latestCv = final; renderCompare(); }
  const report = await getText("/files/output/report.md");
  if (report) {
    const b = report.match(/ATS \(önce\) \| %([\d.]+)/), a = report.match(/ATS \(sonra\) \| %([\d.]+)/);
    if (b) setAts("before", b[1]);
    if (a) setAts("after", a[1]);
  }
  await loadFiles();
  showLessons();
  const banner = $("#banner");
  banner.className = "banner ok";
  banner.textContent = data && data.converged
    ? "Bitti. CV hedefe ulaştı. Yapay zekâ çıktıları hatalı olabilir, göndermeden önce kendin kontrol et."
    : "Bitti, ama CV hedefe ulaşmadı. En iyi sürüm kullanıldı, raporu oku ve göndermeden önce kendin kontrol et.";
  banner.hidden = false;
}

// ---- lessons (memory) --------------------------------------------------------
async function showLessons() {
  if (!config.memory) return;
  const res = await fetch(`/api/runs/${runId}/lessons`);
  if (!res.ok) return;
  const data = await res.json();
  if (data.answered || (!data.accepted.length && !data.rejected.length)) return;
  const g = el("div", "gate");
  g.append(el("h3", "", "Hafıza: bu dersler kaydedilsin mi?"));
  g.append(el("p", "hint", "Kaydedilenler sonraki çalıştırmalarda ilgili ajana eklenir. Hiçbiri sen onaylamadan kaydedilmez."));
  const boxes = [];
  data.accepted.forEach((c, i) => {
    const label = el("label", "check");
    const cb = el("input"); cb.type = "checkbox"; cb.dataset.i = i;
    boxes.push(cb);
    label.append(cb, document.createTextNode(` ${AGENT_LABEL[c.agent] || c.agent}: ${c.text}`));
    g.append(label);
  });
  data.rejected.forEach((c) => g.append(el("p", "hint", `Elendi (${c.reason}): ${c.text}`)));
  const msg = el("p", "hint"); msg.hidden = true;
  if (data.accepted.length) {
    const actions = el("div", "actions");
    const save = el("button", "primary", "Seçilenleri kaydet");
    const skip = el("button", "secondary", "Hiçbirini kaydetme");
    const send = async (accept) => {
      save.disabled = skip.disabled = true;
      const r = await fetch(`/api/runs/${runId}/lessons`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ accept }) });
      const body = await r.json().catch(() => ({}));
      msg.hidden = false;
      msg.textContent = r.ok ? `${body.saved.length} ders kaydedildi.` + body.failed.map((f) => ` Kaydedilemedi (${f.reason}).`).join("") : (body.detail || "Hata");
      if (r.ok) actions.hidden = true; else save.disabled = skip.disabled = false;
    };
    save.addEventListener("click", () => send(boxes.filter((b) => b.checked).map((b) => Number(b.dataset.i))));
    skip.addEventListener("click", () => send([]));
    actions.append(save, skip);
    g.append(actions);
  }
  g.append(msg);
  chat.append(g);
  scrollChat();
}

async function loadLessonList() {
  if (!config.memory) return;
  const res = await fetch("/api/lessons");
  if (!res.ok) return;
  const list = await res.json();
  $("#lessons-box").hidden = !list.length;
  const ul = $("#lesson-list");
  ul.replaceChildren();
  for (const l of list) {
    const li = el("li");
    li.append(el("span", "", `${AGENT_LABEL[l.agent] || l.agent}: ${l.text}`));
    const del = el("button", "", "sil");
    del.type = "button";
    del.addEventListener("click", async () => { await fetch(`/api/lessons/${l.id}`, { method: "DELETE" }); loadLessonList(); });
    li.append(del);
    ul.append(li);
  }
}

async function loadPaused() {
  const res = await fetch("/api/paused");
  if (!res.ok) return;
  const list = await res.json();
  $("#paused").hidden = !list.length;
  const ul = $("#paused-list");
  ul.replaceChildren();
  for (const p of list) {
    const li = el("li");
    li.append(el("span", "", p.title ? `${p.title} (${p.dir})` : p.dir));
    const b = el("button", "", "devam et");
    b.type = "button";
    b.addEventListener("click", () => resumeRun(p.dir, b));
    li.append(b);
    ul.append(li);
  }
}

async function loadHistory() {
  const res = await fetch("/api/history");
  if (!res.ok) return;
  const list = await res.json();
  $("#history").hidden = !list.length;
  const ul = $("#history-list");
  ul.replaceChildren();
  for (const h of list) {
    const li = el("li");
    li.append(el("span", "", h.title ? `${h.title} (${h.dir})` : h.dir));
    const b = el("button", "", "yeniden oynat");
    b.type = "button";
    b.addEventListener("click", () => replayRun(h.dir, b));
    li.append(b);
    if (h.interview) {
      const m = el("button", "", "mülakat yap");
      m.type = "button";
      m.addEventListener("click", () => startInterview(h.dir, m));
      li.append(m);
    }
    ul.append(li);
  }
}

async function replayRun(dir, button, opts) {
  if (button) button.disabled = true;
  const speed = $("#replay-speed").value;
  const payload = { dir, speed: speed === "instant" ? 1 : Number(speed), instant: speed === "instant", ...(opts || {}) };
  try {
    const res = await fetch("/api/replay", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `Sunucu hatası (${res.status})`);
    startRun(body.id, true);
  } catch (err) {
    if (button) button.disabled = false;
    showError(err.message);
  }
}

async function resumeRun(dir, button) {
  if (button) button.disabled = true;
  try {
    const res = await fetch("/api/resume", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dir, pdf: $("#pdf").checked }) });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `Sunucu hatası (${res.status})`);
    startRun(body.id);
  } catch (err) {
    if (button) button.disabled = false;
    showError(err.message);
  }
}

// ---- event handling --------------------------------------------------------
function handle(ev) {
  const d = ev.data || {};
  switch (ev.type) {
    case "reading": setStep("read", "working"); break;
    case "run_started":
      setStep("read", "done");
      getText("/cv/original").then((t) => { originalCv = t || ""; renderCompare(); });
      break;
    case "task_started": {
      const id = stepBySkill[d.skill];
      if (id) setStep(id, "working");
      clearWorking(ev.agent);
      const info = agentInfo(ev.agent);
      workingBubbles[ev.agent] = bubble(ev.agent, "çalışıyor…", "working");
      workingBubbles[ev.agent].querySelector(".who span:last-child").textContent = info.name;
      break;
    }
    case "agent_message": {
      clearWorking(ev.agent);
      bubble(ev.agent, d.text);
      const id = stepBySkill[d.skill];
      if (id) setStep(id, d.state === "rejected" ? "rejected" : "done");
      if (d.skill === "analyze_job") { /* gate card follows */ }
      if (d.skill === "tailor_cv" && iteration) {
        getText(`/files/work/cv_v${iteration}.md`).then((t) => { if (t) { latestCv = t; renderCompare(); } });
      }
      if (d.skill === "write_letter" || d.skill === "prepare_interview") loadFiles();
      break;
    }
    case "checks": {
      const m = bubble("code", "", "");
      const p = $("p", m);
      p.textContent = `${d.errors.length ? d.errors.length + " sorun" : "Sorun yok"}. ATS %${d.ats_before} → %${d.ats_after}`;
      if (d.errors.length || d.warnings.length) {
        const ul = el("ul");
        d.errors.forEach((x) => ul.append(el("li", "e", "✗ " + x)));
        d.warnings.forEach((x) => ul.append(el("li", "w", "! " + x)));
        m.append(ul);
      }
      setStep("checks", d.errors.length ? "issue" : "done", d.errors.length ? d.errors.length + " sorun" : undefined);
      setAts("before", d.ats_before); setAts("after", d.ats_after);
      break;
    }
    case "round_recorded": {
      $("#score-val").textContent = d.score;
      const li = el("li", "", `Tur ${d.iteration}: puan ${d.score}, ${d.errors} kod hatası, doğrulayıcı ${d.decision === "approve" ? "onay" : "ret"}`);
      $("#rounds").append(li);
      break;
    }
    case "loop_iteration":
      iteration = d.iteration;
      divider(`CV turu ${d.iteration}/${d.max}`);
      $("#round-label").textContent = `CV turu ${d.iteration}/${d.max}`;
      STEPS.filter((s) => s.loop).forEach((s) => setStep(s.id, "pending"));
      break;
    case "loop_done":
      if (d.converged) divider(`CV ${d.iteration}. turda hedefe ulaştı`);
      else if (d.stopped_early) divider("Puan artmadı, döngü erken durdu");
      break;
    case "warning": bubble("code", d.text, "warn"); break;
    case "run_paused": {
      Object.keys(workingBubbles).forEach(clearWorking);
      const banner = $("#banner");
      banner.className = "banner";
      banner.replaceChildren(document.createTextNode("Limit doldu, süreç duraklatıldı. Durum kaydedildi, limit yenilenince kaldığı yerden devam edebilirsin. "));
      const b = el("button", "primary", "Devam et");
      b.type = "button";
      b.addEventListener("click", () => resumeRun(d.run_dir.split("/").pop(), b));
      banner.append(b);
      banner.hidden = false;
      $("#new-run").hidden = false;
      STEPS.forEach((s) => { if ($("#step-" + s.id).dataset.s === "working") setStep(s.id, "paused"); });
      break;
    }
    case "run_resumed": $("#banner").hidden = true; $("#new-run").hidden = true; break;
    case "task_failed": {
      clearWorking(ev.agent);
      bubble(ev.agent, "hata: " + d.error, "err");
      const id = stepBySkill[d.skill];
      if (id) setStep(id, "failed");
      break;
    }
    case "input_required": setStep("gate", "waiting"); break;
    case "job_review": renderGate(d.job || {}, d.auto); break;
    case "gate_passed": setStep("gate", "done"); if (openGate) openGate("Onaylandı."); break;
    case "report": setStep("report", "done"); break;
    case "run_failed": {
      if (openGate) openGate("Süreç durdu.");
      Object.keys(workingBubbles).forEach(clearWorking);
      const banner = $("#banner");
      banner.className = "banner";
      banner.textContent = "Süreç durdu: " + d.error;
      banner.hidden = false;
      $("#new-run").hidden = false;
      STEPS.forEach((s) => { if ($("#step-" + s.id).dataset.s === "working") setStep(s.id, "failed"); });
      break;
    }
    case "run_finished": finish(d); break;
  }
}

function connect() {
  if (source) source.close();
  source = new EventSource(`/api/runs/${runId}/events?after=${lastEventId}`);
  source.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    if (ev.id <= lastEventId) return;
    lastEventId = ev.id;
    handle(ev);
  };
  source.addEventListener("end", () => source.close());
}

function startRun(id, replaying) {
  runId = id;
  lastEventId = -1; iteration = 0; originalCv = ""; latestCv = "";
  history.replaceState(null, "", replaying ? location.pathname + location.search : "#run=" + id);
  $("#start").hidden = true;
  $("#run").hidden = false;
  $("#banner").hidden = true;
  $("#replay-note").hidden = !replaying;
  $("#new-run").hidden = true;
  $("#rounds").replaceChildren();
  $("#score-val").textContent = "–";
  setAts("before", 0); setAts("after", 0);
  $("#ats-before-t").textContent = $("#ats-after-t").textContent = "–";
  chat.replaceChildren();
  renderCompare();
  buildSteps();
  connect();
}

$("#new-run").addEventListener("click", () => { history.replaceState(null, "", location.pathname); location.reload(); });

// ---- boot ------------------------------------------------------------------
(async function boot() {
  try {
    config = await (await fetch("/api/config")).json();
  } catch (_) {
    showError("Sunucuya ulaşılamadı. career-crew web çalışıyor mu?");
    return;
  }
  $("#mode-badge").textContent = "mod: " + config.mode;
  $("#lang").value = config.lang;
  document.querySelectorAll(".max-mb").forEach((n) => (n.textContent = config.max_mb));
  $("#mock-note").hidden = config.mode !== "mock";
  const q = new URLSearchParams(location.search);
  if (q.get("replay")) {
    // ?replay=KLASÖR&adim=N plays the first N events at once (used to capture frames for the README).
    const adim = q.get("adim");
    $("#replay-speed").value = q.get("hiz") || "1";
    await replayRun(q.get("replay"), null, adim !== null ? { upto: Number(adim) } : {});
    return;
  }
  const m = location.hash.match(/^#run=([0-9a-f]{12})$/);
  if (m) {
    const res = await fetch(`/api/runs/${m[1]}`);
    if (res.ok) startRun(m[1]);
    else history.replaceState(null, "", location.pathname);
  }
  loadPaused();
  loadHistory();
  loadLessonList();
})();
