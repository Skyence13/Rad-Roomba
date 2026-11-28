// Rad Roomba operator page. Local assets only. State arrives by server-sent events; every
// command carries a fresh id and is acknowledged once; controls are re-enabled only from the
// state the server reports (never from a cached page).
"use strict";
let csrf = null, me = null, state = null, mapData = null, layer = "coverage", es = null, tab = "scan";
const $ = (id) => document.getElementById(id);
const api = async (path, body) => {
  const r = await fetch(path, body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json", "X-CSRF": csrf || ""}, body: JSON.stringify(body)});
  let j = {}; try { j = await r.json(); } catch (e) {}
  return {status: r.status, body: j};
};
const cmdId = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random());
async function command(name, args) {
  const id = cmdId();
  const r = await api("/api/command", {id, name, args: args || {}});
  const b = r.body;
  $("ack").textContent = `${name}: ${b.accepted ? "ACCEPTED" : "REJECTED"}${b.reason ? " — " + b.reason : ""}${b.missing ? " [" + b.missing.join(", ") + "]" : ""} (receipt ${b.receipt ?? "-"})`;
  if (name === "export" && b.accepted) $("exportres").innerHTML = `<a href="/api/export/summary.txt" target="_blank">summary</a> · <a href="/api/export/map_coverage.svg" target="_blank">coverage map</a> · <a href="/api/export/MANIFEST.sha256.json" target="_blank">file manifest</a>`;
  return b;
}
async function login() {
  const r = await api("/api/login", {user: $("user").value, password: $("pass").value});
  if (r.status !== 200) { $("loginmsg").textContent = "sign-in failed"; return; }
  start(r.body);
}
function start(who) {
  me = who; csrf = who.csrf; $("login").hidden = true; $("main").hidden = false;
  $("who").textContent = `${who.user} (${who.role})`;
  connect(); loadSettings(); setInterval(loadMap, 2000); setInterval(loadSettings, 5000);
}
function connect() {
  if (es) es.close();
  es = new EventSource("/api/events");
  es.addEventListener("state", (e) => { state = JSON.parse(e.data); $("conn").textContent = "live"; render(); });
  es.addEventListener("logout", () => location.reload());
  es.onerror = () => { $("conn").textContent = "link lost — showing last state, controls disabled"; disableAll(); };
}
function disableAll() { document.querySelectorAll("button[data-cmd]").forEach((b) => b.disabled = true); }
async function loadMap() { if (!me) return; const r = await api("/api/map"); if (r.status === 200) { mapData = r.body; drawMap(); } }
async function loadSettings() {
  if (!me || tab !== "service") return;
  const r = await api("/api/settings"); if (r.status !== 200) return;
  $("profiles").innerHTML = r.body.profiles.map((p) => `<div class="item"><b>${p.id}</b> rev ${p.revision} — ${p.material}<br>` +
    (p.configured ? `investigation ${p.investigation_level_Bq_cm2} Bq/cm², detection goal &lt; ${p.detection_goal_Bq_cm2} Bq/cm², field_use_approved: ${p.field_use_approved}` : `NOT CONFIGURED (missing ${p.missing.join(", ")}) — no decision possible`) + `</div>`).join("") +
    `<div>mission uses ${r.body.mission_snapshot.id} rev ${r.body.mission_snapshot.revision}; calibration ${r.body.calibration.calibration_id} (synthetic: ${r.body.calibration.synthetic})</div>`;
  if (me.role !== "viewer") { const a = await api("/api/audit"); if (a.status === 200) $("audit").textContent = a.body.audit.slice(-25).map((x) => `${x.n} ${x.user || ""} ${x.op} ${x.command || ""} ${x.accepted === false ? "REJECTED " + (x.reason || "") : "ok"}`).join("\n"); }
}
function row(k, v) { return `<tr><td>${k}</td><td>${v ?? "—"}</td></tr>`; }
function render() {
  const s = state, c = s.control, ch = s.chassis, sf = s.safety, m = s.mission;
  const demo = c.demo_accounts ? "DEMO ACCOUNTS (trivial passwords, plain HTTP, no TLS) - not for field use" : "";
  const bn = [s.banner, demo].filter(Boolean).join(" · ");
  $("banner").hidden = !bn; $("banner").textContent = bn;
  $("robot").textContent = `${s.robot_id} · run ${s.run_id.slice(-8)} · ${s.trailer.id}`;
  $("frame").textContent = s.localization.frame;
  $("owner").textContent = c.holder ? `control: ${c.holder}` : "control: nobody";
  const mine = c.you && c.you.has_control;
  $("take").hidden = mine || !c.you || c.you.role !== "operator"; $("release").hidden = !mine;
  $("take").textContent = c.holder && !mine ? `Take over from ${c.holder}` : "Take control";
  const p = s.localization.pose;
  $("status").innerHTML =
    row("Mission", `<span class="state s-${m.state}">${m.state}</span> ${m.hold_reason || ""} ${m.task || ""} (${m.tasks_done ?? 0}/${m.tasks_total ?? 0}) ${m.method || ""}`) +
    row("Chassis", `<span class="state s-${ch.mode}">${ch.mode}</span> ${ch.motion || ""} op_mode ${ch.op_mode}`) +
    row("Head", `${s.head.state} ${s.head.head_id || ""} ${s.head.block_reason || ""} seq ${s.head.last_seq ?? "—"}`) +
    row("Clock bound", `head ${fmt(s.head.bound_us, 0)} µs · chassis ${fmt(ch.time_bound_us, 0)} µs (limit 10000)`) +
    row("Pose (map)", p ? `x ${p[0].toFixed(3)} m from door, y ${p[1].toFixed(3)} m, heading ${(p[2] * 57.3).toFixed(1)}°` : "datum not registered") +
    row("Position uncertainty (2σ at head)", `${fmt(s.localization.uncertainty_2s_m * 1000, 1)} mm · credit ${s.localization.credit ? "yes" : "NO"}${s.localization.slip ? " · SLIP" : ""}`) +
    row("Recorder", s.recorder.ok ? `ok (epoch ${s.recorder.epoch}, ${s.recorder.entries} entries)` : `FAULT ${s.recorder.error}`) +
    row("Profile / calibration", `${s.profile.id} rev ${s.profile.revision} · ${s.calibration_id} · unit ${s.profile.unit}`) +
    row("Missing before motion", (m.prerequisites_missing || []).join(", ") || "nothing");
  $("safety").innerHTML = `<div>Traction: <b>${sf.traction_inhibited ? "INHIBITED ⛔" : "permitted ✔"}</b>${sf.charge_service ? " — CHARGE/SERVICE: drive locked out" : ""}</div>` +
    `<div>Hardware inhibit: ${(sf.hw_inhibit_reasons || []).join(", ") || "none"} · latch ${sf.hw_latch ? "set" : "open"}</div>` +
    (sf.rearm_prompt ? `<div><b>${sf.rearm_prompt.press_rearm ? "▶ " : ""}${esc(sf.rearm_prompt.text)}</b>${(sf.rearm_prompt.reasons || []).length ? " — " + esc(sf.rearm_prompt.reasons.join("; ")) : ""}` +
      `${sf.rearm_prompt.refused && sf.rearm_prompt.press_rearm ? " — " + esc(sf.rearm_prompt.refused) : ""}` +
      `${(sf.rearm_prompt.warnings || []).length ? `<div style="color:#b00020"><b>${esc(sf.rearm_prompt.warnings.join("; "))}</b></div>` : ""}</div>` : "") +
    `<div>Chassis faults: ${esc((sf.faults || []).join(", ")) || "none"} · chain not closed (open or unknown): ${esc((sf.chain_not_closed || []).join(", ")) || "none"}</div>` +
    `<div>Protective stop: ${(sf.protective_stop_reasons || []).join(", ") || "none"} · hold: ${(sf.hold || []).join(", ") || "none"}</div>` +
    `<div class="small">Local only (cannot be cleared from this page): ${sf.local_only.join("; ")}.<br>Clearable by the controlling operator: ${sf.remote_clearable.join("; ")}.</div>`;
  $("mission").innerHTML = `<div class="small">phase ${m.phase || ""} ${m.station || ""} ${m.counting ? "counting " + m.counting : ""} · deferred strips: ${(m.tasks_deferred || []).length} · plan ${s.plan ? Math.round(s.plan.estimated_time_s / 60) + " min est." : "—"}</div>`;
  const rm = m.ratemeter || {};
  $("rate").innerHTML = Object.keys(rm).map((k) => { const r = rm[k]; if (r.rate == null) return `<div>lane ${k}: —</div>`;
    const w = Math.min(200, r.rate * 6), a = Math.min(200, (r.alarm_level || 0) * 6);
    return `<div>lane ${k}: <span class="bar ${r.alarm ? "alarm" : ""}" style="width:${w}px"></span><span style="margin-left:${Math.max(0, a - w)}px">▲</span> ${r.rate.toFixed(1)} (set-point ${fmt(r.alarm_level, 1)})</div>`; }).join("");
  $("scaler").innerHTML = (s.observations || []).slice(-6).map((o) => `${o.id} lane ${o.lane}: ${o.outcome}` + (o.result ? ` D=${o.result.D.toFixed(3)}±${o.result.u_total.toFixed(3)} D*=${o.result.D_star.toFixed(3)} D#=${fmt(o.result.D_hash, 3)} T=${o.result.T_F.toFixed(1)} s (${o.result.method})` : "")).join("<br>") || "none";
  $("qpolicy").textContent = s.review.policy === "ALL_UNRESOLVED" ? "— policy ALL_UNRESOLVED: every cell not cleared at the investigation level"
    : `— policy ALARM_ONLY: scan alarms at α = ${s.review.alpha_queue} only (insufficient-sensitivity floor is on the map, not here)`;
  $("queue").innerHTML = (s.review.items || []).map((i) => `<div class="item ${s.review.current === i.id ? "cur" : ""}"><b>${i.id}</b> ${i.kind} — <b>${i.status}</b><br>` +
    `${i.location.text}; lane ${i.source_lane}; D=${i.D.toFixed(3)} ± ${i.u_total.toFixed(3)} Bq/cm² (D* ${i.D_star.toFixed(3)}, D# ${fmt(i.D_hash, 3)}); position ±${(i.position_uncertainty_m * 1000).toFixed(0)} mm<br>` +
    `<span class="small">${(i.notes || []).join(" · ")}</span></div>`).join("") || "<i>no flagged areas</i>";
  $("svcnote").textContent = sf.charge_service ? "CHARGE/SERVICE: charger connected — settings and data access available, all drive requests refused." : "Settings and data access. Profile edits need the RP role and are refused while a mission uses a snapshot.";
  $("events").textContent = (s.events || []).slice(-12).map((e) => `${e.ev} ${e.reason || e.name || e.note || e.task || ""} ${e.accepted === false ? "REJECTED" : ""}`).join("\n");
  const can = mine && $("conn").textContent === "live";
  document.querySelectorAll("button[data-cmd]").forEach((b) => { b.disabled = b.dataset.free ? me.role === "viewer" : !can; });
  if (sf.charge_service) document.querySelectorAll("#missionbtns button, .tab[data-tab=review] button").forEach((b) => b.disabled = true);
  drawMap();
}
const esc = (t) => String(t == null ? "" : t).replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const fmt = (v, d) => (v == null ? "—" : Number(v).toFixed(d));
function pattern(ctx, kind) {
  const c = document.createElement("canvas"); c.width = c.height = 8; const g = c.getContext("2d");
  const fill = {UNVISITED: "#fff", ACCEPTABLE: "#2e8b57", INSUFFICIENT_SENSITIVITY: "#fdebc8", INVALID_DATA: "#f6d5d5", BLOCKED: "#e4dcf0", EXCLUDED: "#5a5a5a",
                NO_DECISION: "#e6e6f2", INCOMPLETE_COVERAGE: "#faeec0", ALARM: "#e60078", ACQUISITION_GAP: "#dddddd"}[kind];  // ALARM is never green (MODEL rev 5 s6)
  g.fillStyle = fill; g.fillRect(0, 0, 8, 8); g.strokeStyle = "#555"; g.fillStyle = "#b9770e";
  if (kind === "UNVISITED") { g.beginPath(); g.moveTo(0, 8); g.lineTo(8, 0); g.stroke(); }
  if (kind === "INVALID_DATA") { g.strokeStyle = "#c83c3c"; g.beginPath(); g.moveTo(0, 0); g.lineTo(8, 8); g.moveTo(0, 8); g.lineTo(8, 0); g.stroke(); }
  if (kind === "INSUFFICIENT_SENSITIVITY") { g.beginPath(); g.arc(4, 4, 1.4, 0, 7); g.fill(); }
  if (kind === "BLOCKED") { g.strokeStyle = "#785aa0"; g.lineWidth = 2; g.beginPath(); g.moveTo(0, 4); g.lineTo(8, 4); g.stroke(); }
  return ctx.createPattern(c, "repeat");
}
function drawMap() {
  if (!mapData || !state) return;
  const cv = $("map"), ctx = cv.getContext("2d"), L = state.trailer.length_m, W = state.trailer.width_m;
  const sc = Math.min((cv.width - 40) / L, (cv.height - 50) / W), X = (x) => 20 + x * sc, Y = (y) => 20 + (W / 2 - y) * sc;
  ctx.clearRect(0, 0, cv.width, cv.height);
  if (layer === "coverage") {
    const b = mapData.block_m; const pats = {}; mapData.reasons.forEach((r) => pats[r] = pattern(ctx, r));
    mapData.coverage_rle.forEach((rowv, iy) => { for (let k = 0; k < rowv.length; k++) { const a = rowv[k][0], e = k + 1 < rowv.length ? rowv[k + 1][0] : mapData.coverage_shape[1];
      ctx.fillStyle = pats[mapData.reasons[rowv[k][1]]]; ctx.fillRect(X(a * b), Y(mapData.origin[1] + (iy + 1) * b), (e - a) * b * sc + 0.5, b * sc + 0.5); } });
    $("legend").textContent = "patterns: diagonal = unvisited · crosses = invalid data · dots = insufficient sensitivity · bars = blocked · solid green = acceptable · dark = excluded";
  } else {
    const c = mapData.cell_m, lvl = state.profile.investigation_level, goal = state.profile.detection_goal;
    mapData.cells.forEach(([cx, cy, D, u, dh, ok]) => {
      let col;
      if (layer === "activity") { const f = Math.max(-1, Math.min(1, D / lvl)); col = f >= 0 ? `rgb(255,${255 * (1 - f)},${255 * (1 - f)})` : `rgb(${255 * (1 + 0.6 * f)},${255 * (1 + 0.6 * f)},255)`; }
      else { const f = dh == null ? 1 : Math.min(1, dh / (2 * goal)); col = `rgb(${255 * f},${200 * (1 - f) + 55},80)`; }
      ctx.fillStyle = col; ctx.fillRect(X(cx * c), Y(mapData.origin[1] + (cy + 1) * c), c * sc + 0.5, c * sc + 0.5); });
    $("legend").textContent = layer === "activity" ? `signed estimate per decision cell: blue ≤ 0 · white 0 · red ≥ investigation level ${lvl} Bq/cm² (colour clips, data do not; blank = no valid data)` : `detection limit D# per decision cell: green = well below goal ${goal} Bq/cm², red ≥ 2× goal (blank = no valid data)`;
  }
  ctx.strokeStyle = "#000"; ctx.lineWidth = 2; ctx.strokeRect(X(0), Y(W / 2), L * sc, W * sc);
  ctx.fillStyle = "#000"; ctx.font = "11px sans-serif"; ctx.fillText("DOOR x=0", X(0), Y(-W / 2) + 12); ctx.fillText(`BULKHEAD x=${L} m`, X(L) - 90, Y(-W / 2) + 12);
  ctx.fillText("left wall (+y)", X(L / 2) - 30, Y(W / 2) - 4); ctx.beginPath(); ctx.moveTo(X(0.1), Y(-W / 2) + 20); ctx.lineTo(X(0.6), Y(-W / 2) + 20); ctx.stroke(); ctx.fillText("0.5 m", X(0.1), Y(-W / 2) + 32);
  (mapData.flags || []).forEach((f) => { if (f.footprint) { ctx.setLineDash([4, 2]); ctx.beginPath(); f.footprint.forEach((p, i) => i ? ctx.lineTo(X(p[0]), Y(p[1])) : ctx.moveTo(X(p[0]), Y(p[1]))); ctx.closePath(); ctx.stroke(); ctx.setLineDash([]); } ctx.fillText(f.id, X(f.x) + 5, Y(f.y) - 5); });
  const p = state.localization.pose;
  if (p) { ctx.strokeStyle = "#1d4ed8"; mapData.outline.forEach((part) => { ctx.beginPath(); part.forEach((q, i) => { const x = p[0] + Math.cos(p[2]) * q[0] - Math.sin(p[2]) * q[1], y = p[1] + Math.sin(p[2]) * q[0] + Math.cos(p[2]) * q[1]; i ? ctx.lineTo(X(x), Y(y)) : ctx.moveTo(X(x), Y(y)); }); ctx.closePath(); ctx.stroke(); }); }
  const a = mapData.summary.areas_m2, t = mapData.summary.target_area_m2;
  $("covsum").textContent = `valid exposure ${(100 * mapData.summary.valid_exposure_fraction).toFixed(1)} % of ${t.toFixed(2)} m² · acceptable ${a.ACCEPTABLE.toFixed(2)} · insufficient sensitivity ${a.INSUFFICIENT_SENSITIVITY.toFixed(2)} · unvisited ${a.UNVISITED.toFixed(2)} · invalid ${a.INVALID_DATA.toFixed(2)} · blocked ${a.BLOCKED.toFixed(2)} m² (floor only)`;
}
document.addEventListener("click", async (e) => {
  const t = e.target;
  if (t.dataset.cmd) { t.disabled = true; await command(t.dataset.cmd, {}); }
  if (t.dataset.sim) await api("/api/sim", {action: t.dataset.sim});
  if (t.dataset.tab && t.tagName === "BUTTON") { tab = t.dataset.tab; document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("on", b === t)); document.querySelectorAll(".tab").forEach((d) => d.hidden = d.dataset.tab !== tab); loadSettings(); }
});
document.querySelectorAll("input[name=layer]").forEach((r) => r.addEventListener("change", () => { layer = r.value; drawMap(); }));
$("dologin").onclick = login;
$("logout").onclick = async () => { await api("/api/logout", {}); location.reload(); };
$("take").onclick = async () => { const held = state && state.control.holder; if (held && !confirm(`Take control from ${held}? This is recorded.`)) return; await api("/api/control", {action: "take", force: !!held}); };
$("release").onclick = () => api("/api/control", {action: "release"});
$("skip").onclick = async () => { const reason = prompt("Reason for skipping this item:"); if (reason) await command("skip", {reason}); };
$("pedit").onclick = () => command("profile_edit", {profile: state.profile.id, changes: {investigation_level_Bq_cm2: Number($("pval").value)}, unit: $("punit").value});
(async () => { const r = await api("/api/whoami"); if (r.status === 200) start(r.body); const s = await fetch("/api/sim", {method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"}); if (s.status !== 404 && s.status !== 401) $("simpanel").hidden = false; })();
