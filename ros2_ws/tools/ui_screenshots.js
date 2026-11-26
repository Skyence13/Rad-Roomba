// Operator-UI screenshots against the stand-alone simulator (headless Chromium via Playwright).
//
//   tools/run_sim.sh --port 8090 --auto --method SEARCH_THEN_COUNT --speedup 6 &   # simulator + UI
//   node tools/ui_screenshots.js [http://127.0.0.1:8090] [out_dir]
//
// Evidence class: simulated / tool-checked.  Drives the real page (login, take control, Start,
// layers, review Next / Expose spot / Park, Charge/Service) and writes PNGs (desktop 1280 px and
// phone 390 px) plus ui_checks.json with what the page and the server reported.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");
const base = process.argv[2] || "http://127.0.0.1:8090";
const out = process.argv[3] || path.join(__dirname, "..", "evidence", "ui");
fs.mkdirSync(out, { recursive: true });
const checks = [];
const check = (name, ok, info) => { checks.push({ check: name, ok: !!ok, ...(info || {}) }); console.log((ok ? "PASS " : "FAIL ") + name, info ? JSON.stringify(info).slice(0, 300) : ""); };
const state = (p) => p.evaluate(async () => (await fetch("/api/state")).json());
const sim = (p, action) => p.evaluate(async (a) => (await fetch("/api/sim", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: a }) })).json(), action);
async function waitState(p, pred, timeoutS, label) {
  const end = Date.now() + timeoutS * 1000;
  let s;
  while (Date.now() < end) { s = await state(p); if (pred(s)) return s; await p.waitForTimeout(1000); }
  console.log("timeout waiting for", label, s && s.mission && s.mission.state);
  return null;
}
async function shot(p, name, full = true) { await p.screenshot({ path: path.join(out, name), fullPage: full }); }
async function login(p, user) {
  await p.goto(base + "/");
  await p.fill("#user", user); await p.fill("#pass", user); await p.click("#dologin");
  await p.waitForSelector("#main:not([hidden])"); await p.waitForTimeout(1500);
}
async function tab(p, t) { await p.click(`nav button[data-tab=${t}]`); await p.waitForTimeout(1200); }
async function layer(p, l) { await p.check(`input[value=${l}]`); await p.waitForTimeout(2500); }

(async () => {
  const browser = await chromium.launch();
  const desk = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  const phone = await (await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })).newPage();
  await desk.goto(base + "/");
  await shot(desk, "d01_login.png");
  check("login page states demo accounts / TLS needed", (await desk.textContent("#login")).includes("DEMONSTRATION"));
  await login(desk, "operator");
  await desk.click("#take"); await desk.waitForTimeout(1000);
  let s = await state(desk);
  check("operator holds the control lease", s.control.holder === "operator");
  check("demo-account banner shown", (await desk.textContent("#banner")).includes("DEMO ACCOUNTS"));
  await desk.click("button[data-cmd=start]"); await desk.waitForTimeout(1500);
  check("Start acknowledged", (await desk.textContent("#ack")).includes("start: ACCEPTED"), { ack: await desk.textContent("#ack") });
  s = await waitState(desk, (x) => x.mission.state === "SCAN" && x.recorder.entries > 0 && (x.mission.tasks_done || 0) >= 1, 300, "first task done");
  await desk.reload(); await desk.waitForSelector("#main:not([hidden])"); await desk.waitForTimeout(2500);   // sim panel appears on reload
  await shot(desk, "d02_status_scan_coverage_layer.png");
  await layer(desk, "activity"); await shot(desk, "d03_map_activity_layer.png");
  await layer(desk, "sensitivity"); await shot(desk, "d04_map_detection_limit_layer.png");
  await layer(desk, "coverage");
  // ratemeter / scaler view: wait for a scaler count (search alarm -> stop -> count)
  s = await waitState(desk, (x) => (x.observations || []).some((o) => o.result), 900, "scaler observation");
  check("scaler count with result shown (SEARCH_THEN_COUNT)", !!s, s ? { obs: s.observations.slice(-1)[0].id } : {});
  await desk.waitForTimeout(1500);
  await (await desk.$("#rate")).scrollIntoViewIfNeeded();
  await shot(desk, "d05_ratemeter_scaler.png");
  await login(phone, "viewer"); await phone.waitForTimeout(2500);
  await shot(phone, "p01_viewer_status_scan.png");
  const vOwner = await phone.textContent("#owner"), vDis = await phone.$$eval("button[data-cmd=start]", (b) => b.every((x) => x.disabled));
  check("viewer: Start disabled, ownership visible", vDis && vOwner.includes("operator"), { owner: vOwner, start_disabled: vDis });
  // review queue after the committed survey
  s = await waitState(desk, (x) => x.mission.state === "REVIEW", 1800, "REVIEW");
  check("mission reached REVIEW", !!s, s ? { finish: s.mission.finish_reason, items: (s.review.items || []).length } : {});
  await tab(desk, "review");
  await shot(desk, "d06_review_queue.png");
  await tab(phone, "review"); await shot(phone, "p02_viewer_review_queue.png");
  const items = (s && s.review.items) || [];
  s = await state(desk);
  check("operator still holds the lease at REVIEW", s.control.holder === "operator", { holder: s.control.holder });
  if (s.control.holder !== "operator") { await desk.click("#take"); await desk.waitForTimeout(1500); }
  if (items.length) {
    await desk.click("button[data-cmd=next]");
    s = await waitState(desk, (x) => !x.review.busy && x.review.current && (x.review.items.find((i) => i.id === x.review.current) || {}).status === "AT_SPOT", 600, "AT_SPOT");
    check("Next: lane at the spot (AT_SPOT)", !!s, s ? { current: s.review.current } : {});
    await shot(desk, "d07_review_next_at_spot.png");
    await desk.click("button[data-cmd=expose]");
    s = await waitState(desk, (x) => !x.review.busy, 120, "expose done"); await desk.waitForTimeout(1500);
    check("Expose spot acknowledged", (await desk.textContent("#ack")).includes("ACCEPTED"), { ack: await desk.textContent("#ack") });
    await shot(desk, "d08_review_expose_spot.png");
    await desk.click("button[data-cmd=park]");
    s = await waitState(desk, (x) => x.review.parked, 600, "parked");
    check("Park: robot parked", !!s);
    await shot(desk, "d09_review_parked.png");
  }
  // Charge/Service
  await sim(desk, "charger_on");
  s = await waitState(desk, (x) => x.safety.charge_service, 60, "charge_service");
  await tab(desk, "service"); await desk.waitForTimeout(3000);
  check("Charge/Service shown, drive locked out", !!s && (await desk.textContent("#safety")).includes("CHARGE/SERVICE"));
  const refused = await desk.evaluate(async () => {
    const who = await (await fetch("/api/whoami")).json();
    const r = await fetch("/api/command", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF": who.csrf }, body: JSON.stringify({ id: "ui-shot-" + Date.now(), name: "next" }) });
    return r.json();
  });
  check("server refuses Next in Charge/Service", !refused.accepted && String(refused.reason).startsWith("CHARGE_SERVICE"), { reason: refused.reason, refused_by: refused.refused_by });
  await desk.click("button[data-cmd=export]"); await desk.waitForTimeout(6000);
  await shot(desk, "d10_charge_service_reports_settings.png");
  await tab(phone, "service"); await phone.waitForTimeout(2000); await shot(phone, "p03_viewer_charge_service.png");
  await phone.close();
  const op2 = await (await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })).newPage();
  await login(op2, "operator2"); await shot(op2, "p04_operator2_phone_control_held_by_other.png");
  await sim(desk, "charger_off");
  fs.writeFileSync(path.join(out, "ui_checks.json"), JSON.stringify({ evidence_class: "simulated / tool-checked (headless Chromium, Playwright)", base, method: "SEARCH_THEN_COUNT", generated: new Date().toISOString(), checks, passed: checks.every((c) => c.ok) }, null, 1) + "\n");
  await browser.close();
  process.exit(checks.every((c) => c.ok) ? 0 : 1);
})().catch((e) => { console.error("ERR", e.stack || e.message); process.exit(2); });
