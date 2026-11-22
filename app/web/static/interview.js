"use strict";
// Mock interview page: a chat where the Interviewer asks and the user answers.
// Shares helpers ($, el, config, agentInfo, openViewer) with app.js.

let ivSource = null;
let ivLast = -1;
let ivQuestion = 0;
let ivReport = null;
const IV_VERDICT = { strong: "güçlü", ok: "orta", weak: "zayıf" };
const ivChat = $("#iv-chat");

function ivBubble(cls, who, text, color) {
  const m = el("div", "msg" + (cls ? " " + cls : ""));
  m.style.setProperty("--c", color || "var(--accent)");
  const w = el("div", "who");
  w.append(el("span", "dot"), el("span", "", who));
  m.append(w, el("p", "", text));
  ivChat.append(m);
  m.scrollIntoView({ block: "nearest", behavior: "smooth" });
  return m;
}

function ivSetInput(open) {
  $("#iv-form").hidden = !open;
  if (open) { $("#iv-answer").value = ""; $("#iv-answer").focus({ preventScroll: true }); }
}

let ivTyping = null;
function ivClearTyping() { ivTyping?.remove(); ivTyping = null; }

function ivHandle(ev) {
  const d = ev.data || {};
  const who = agentInfo("interviewer");
  switch (ev.type) {
    case "interview_started":
      $("#iv-title").textContent = d.title ? `Deneme mülakatı: ${d.title}` : "Deneme mülakatı";
      break;
    case "task_started":
      ivClearTyping();
      ivTyping = ivBubble("working", who.name, "yazıyor…", who.color);
      break;
    case "interview_question":
      ivClearTyping();
      ivQuestion = d.n;
      $("#iv-progress").textContent = `Soru ${d.n}/${d.total}`;
      ivBubble("", who.name, d.text, who.color);
      break;
    case "interview_answer":
      ivBubble("me", "Sen", d.text, "var(--muted)");
      break;
    case "interview_evaluation": {
      ivClearTyping();
      const m = ivBubble("", who.name, `${IV_VERDICT[d.verdict] || d.verdict}: ${d.feedback}`, who.color);
      const ul = el("ul");
      d.flags.forEach((f) => ul.append(el("li", "e", `✗ CV'de yok: ${f.claim}${f.why ? " (" + f.why + ")" : ""}`)));
      d.code_flags.forEach((c) => ul.append(el("li", "w", "! " + c)));
      if (ul.children.length) m.append(ul);
      if (d.framing) m.append(el("p", "framing", "Dürüst çerçeve: " + d.framing));
      break;
    }
    case "input_required": ivSetInput(true); break;
    case "interview_report": ivReport = d.path; break;
    case "interview_finished":
      ivClearTyping(); ivSetInput(false);
      ivBubble("", "🧮 Kod kontrolü", `Mülakat bitti, ${d.answered}/${d.total} soru cevaplandı.`, "var(--muted)");
      $("#iv-done").hidden = false;
      break;
    case "warning": ivBubble("warn", "🧮 Kod kontrolü", d.text, "var(--muted)"); break;
    case "run_paused":
    case "run_failed": {
      ivClearTyping(); ivSetInput(false);
      const b = $("#iv-banner");
      b.className = "banner";
      b.textContent = ev.type === "run_paused" ? "Limit doldu, mülakat durdu. Cevapladıkların kaydedildi." : "Mülakat durdu: " + d.error;
      b.hidden = false;
      $("#iv-done").hidden = false;
      break;
    }
    case "task_failed": ivClearTyping(); ivBubble("err", who.name, "hata: " + d.error, who.color); break;
  }
}

function ivConnect(id) {
  if (ivSource) ivSource.close();
  ivSource = new EventSource(`/api/runs/${id}/events?after=${ivLast}`);
  ivSource.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    if (ev.id <= ivLast) return;
    ivLast = ev.id;
    ivHandle(ev);
  };
  ivSource.addEventListener("end", () => {
    ivSource.close();
    if (ivReport) $("#iv-report").hidden = false;
  });
}

async function startInterview(dir, button) {
  if (button) button.disabled = true;
  try {
    const res = await fetch("/api/interviews", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dir, count: 5 }) });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `Sunucu hatası (${res.status})`);
    runId = body.id;
    ivLast = -1; ivReport = null;
    $("#start").hidden = true;
    $("#interview").hidden = false;
    ivChat.replaceChildren();
    $("#iv-sample").hidden = !(config.mock_answers || []).length;
    ivConnect(body.id);
  } catch (err) {
    if (button) button.disabled = false;
    showError(err.message);
  }
}

async function ivSend(payload) {
  const err = $("#iv-error");
  err.hidden = true;
  document.querySelectorAll("#iv-form button").forEach((b) => (b.disabled = true));
  try {
    const res = await fetch(`/api/runs/${runId}/answer`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || `Hata (${res.status})`);
    ivSetInput(false);
  } catch (e) {
    err.textContent = e.message; err.hidden = false;
  } finally {
    document.querySelectorAll("#iv-form button").forEach((b) => (b.disabled = false));
  }
}

$("#iv-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("#iv-answer").value.trim();
  if (!text) { $("#iv-error").textContent = "Cevabı yaz, ya da soruyu geç"; $("#iv-error").hidden = false; return; }
  ivSend({ action: "answer", text });
});
$("#iv-skip").addEventListener("click", () => ivSend({ action: "skip" }));
$("#iv-finish").addEventListener("click", () => ivSend({ action: "finish" }));
$("#iv-sample").addEventListener("click", () => {
  const list = config.mock_answers || [];
  if (list.length) $("#iv-answer").value = list[(ivQuestion - 1) % list.length];
});
$("#iv-report").addEventListener("click", async () => {
  const text = await getText("/files/output/mulakat_geri_bildirim.md");
  const pre = el("pre", "doc"); pre.textContent = text || "";
  openViewer("Deneme mülakatı geri bildirimi", pre);
});
$("#iv-new").addEventListener("click", () => location.reload());
