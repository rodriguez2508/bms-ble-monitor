"use strict";
const METRIC_LABEL = { voltage: "Voltaje (V)", current: "Corriente (A)", power: "Potencia (W)", soc: "SOC (%)" };
let activeMetric = "voltage";

const WARNING_BITS = {
  0: "Celda sobrevoltaje", 1: "Celda bajo voltaje", 2: "Pack sobrevoltaje", 3: "Pack bajo voltaje",
  4: "Sobrecorriente carga", 5: "Sobrecorriente descarga",
  8: "Alta temp. carga", 9: "Alta temp. descarga", 10: "Baja temp. carga", 11: "Baja temp. descarga",
  12: "Alta temp. ambiente", 13: "Baja temp. ambiente", 14: "Alta temp. MOSFET", 15: "SOC bajo"
};
const PROTECTION_BITS = {
  0: "Celda sobrevoltaje", 1: "Celda bajo voltaje", 2: "Pack sobrevoltaje", 3: "Pack bajo voltaje",
  4: "Sobrecorriente carga", 5: "Sobrecorriente descarga", 6: "Cortocircuito", 7: "Cargador sobrevoltaje",
  8: "Alta temp. carga", 9: "Alta temp. descarga", 10: "Baja temp. carga", 11: "Baja temp. descarga",
  12: "Alta temp. MOSFET", 13: "Alta temp. ambiente", 14: "Baja temp. ambiente"
};
const STATUS_BITS = {
  0: "Falla MOSFET carga", 1: "Falla MOSFET descarga", 2: "Falla sensor temp.", 4: "Falla de celda",
  5: "Falla muestreo", 8: "En carga", 9: "En descarga", 10: "MOSFET carga ON", 11: "MOSFET descarga ON",
  12: "Limitador de carga ON", 14: "Cargador invertido", 15: "Calentador ON"
};
const THRESHOLD_ROWS = [
  ["pack_ov_alarm_V", "Pack sobrevoltaje (alarma)", "V"],
  ["pack_ov_protection_V", "Pack sobrevoltaje (protección)", "V"],
  ["cell_ov_alarm_V", "Celda sobrevoltaje (alarma)", "V"],
  ["cell_ov_protection_V", "Celda sobrevoltaje (protección)", "V"],
  ["pack_uv_protection_V", "Pack bajo voltaje (protección)", "V"],
  ["cell_uv_protection_V", "Celda bajo voltaje (protección)", "V"],
  ["charge_oc_alarm_A", "Sobrecorriente carga (alarma)", "A"],
  ["charge_oc_protection_A", "Sobrecorriente carga (protección)", "A"],
  ["charge_ot_alarm_C", "Alta temp. carga (alarma)", "°C"],
  ["balance_start_cell_V", "Inicio balanceo (celda)", "V"],
  ["balance_start_delta_mV", "Delta de balanceo", "mV"],
  ["pack_full_charge_V", "Pack carga completa", "V"],
  ["cell_sleep_V", "Voltaje de reposo (celda)", "V"],
  ["cell_sleep_delay_min", "Retardo reposo", "min"],
  ["soc_alarm_pct", "Alarma SOC bajo", "%"]
];

function fmt(x, digits) {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return Number(x).toFixed(digits);
}

async function fetchJSON(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(url + " -> HTTP " + res.status);
  return res.json();
}

function setBadge(connected) {
  const badge = document.getElementById("conn-badge");
  badge.textContent = connected ? "conectado" : "desconectado";
  badge.className = "badge " + (connected ? "on" : "off");
}

function bitsToChips(value, map, cls) {
  const chips = [];
  for (const [bit, label] of Object.entries(map)) {
    if ((value >> Number(bit)) & 1) chips.push('<span class="chip ' + cls + '">' + label + "</span>");
  }
  return chips;
}

function renderAlerts(d) {
  const box = document.getElementById("alerts");
  if (!d) { box.innerHTML = '<span class="muted">Sin datos</span>'; return; }
  const chips = []
    .concat(bitsToChips(d.warning_flags || 0, WARNING_BITS, "warn"))
    .concat(bitsToChips(d.protection_flags || 0, PROTECTION_BITS, "bad"))
    .concat(bitsToChips(d.status_flags || 0, STATUS_BITS, "info"));
  if ((d.soc_pct || 0) <= ALERT.threshold) {
    chips.unshift('<span class="chip bad">SOC bajo: ' + fmt(d.soc_pct, 0) + "%</span>");
  }
  if ((d.soc_pct || 0) >= ALERT.highThreshold) {
    chips.unshift('<span class="chip warn">SOC alto: ' + fmt(d.soc_pct, 0) + "%</span>");
  }
  box.innerHTML = chips.length ? chips.join("") : '<span class="chip ok">sin alarmas</span>';
}

function renderTemperatures(d) {
  const box = document.getElementById("temps");
  const info = document.getElementById("temp-info");
  if (!d) { box.innerHTML = '<span class="muted">Sin datos</span>'; info.textContent = ""; return; }
  const items = [];
  (d.cell_temperatures_C || []).forEach((t, i) => items.push({ n: "Celda " + (i + 1), v: t }));
  if (d.mosfet_temperature_C) items.push({ n: "MOSFET", v: d.mosfet_temperature_C });
  if (d.ambient_temperature_C) items.push({ n: "Ambiente", v: d.ambient_temperature_C });
  (d.extra_temperatures_C || []).forEach((t, i) => items.push({ n: "Sensor " + (i + 1), v: t, note: true }));
  if (!items.length) { box.innerHTML = '<span class="muted">Sin datos</span>'; info.textContent = ""; return; }
  box.innerHTML = items.map(it =>
    '<div class="cell"><div class="n">' + it.n + '</div><div class="v">' + fmt(it.v, 1) +
    ' °C</div>' + (it.note ? '<div class="n">sin confirmar</div>' : "") + "</div>"
  ).join("");
  const vals = items.map(i => i.v);
  info.textContent = "min " + fmt(Math.min.apply(null, vals), 1) + " °C · max " +
    fmt(Math.max.apply(null, vals), 1) + " °C";
}

function renderStatus(payload) {
  setBadge(payload.connected);
  const d = payload.data;
  const ids = ["v-voltage", "v-current", "v-power", "v-soc", "v-soh", "v-cap", "v-runtime", "v-cycles"];
  if (!d) {
    ids.forEach(id => { document.getElementById(id).textContent = "—"; });
    document.getElementById("v-current-dir").textContent = "";
    document.getElementById("v-cap-sub").textContent = "";
    document.getElementById("v-runtime-sub").textContent = "";
    document.getElementById("v-runtime-value").classList.remove("warn", "bad");
    document.getElementById("cells").innerHTML = '<span class="muted">Sin datos</span>';
    document.getElementById("cell-info").textContent = "";
    renderTemperatures(null);
    renderAlerts(null);
    document.getElementById("last-update").textContent = "sin lecturas";
    return;
  }
  document.getElementById("v-voltage").textContent = fmt(d.voltage_V, 2);
  document.getElementById("v-current").textContent = fmt(d.current_A, 2);
  document.getElementById("v-power").textContent = fmt(d.power_W, 1);
  document.getElementById("v-soc").textContent = fmt(d.soc_pct, 0);
  document.getElementById("v-soh").textContent = fmt(d.soh_pct, 0);
  document.getElementById("v-cap").textContent = fmt(d.cap_remain_Ah, 1);
  document.getElementById("v-cap-sub").textContent = "de " + fmt(d.cap_design_Ah, 1) + " Ah";
  const cur = d.current_A || 0;
  const runtimeValueEl = document.getElementById("v-runtime-value");
  runtimeValueEl.classList.remove("warn", "bad");
  let runtimeText = "—";
  let runtimeSub = "en reposo";
  if (cur < -0.05) {
    const hours = (d.cap_remain_Ah || 0) / Math.abs(cur);
    if (isFinite(hours) && hours >= 0) {
      runtimeText = fmt(hours, 1);
      runtimeSub = "a " + fmt(Math.abs(cur), 2) + " A";
      if (hours <= 0.5) runtimeValueEl.classList.add("bad");
      else if (hours <= 1) runtimeValueEl.classList.add("warn");
    }
  } else if (cur > 0.05) {
    runtimeSub = "cargando";
  }
  document.getElementById("v-runtime").textContent = runtimeText;
  document.getElementById("v-runtime-sub").textContent = runtimeSub;
  document.getElementById("v-cycles").textContent = fmt(d.cycles, 0);
  document.getElementById("v-current-dir").textContent =
    d.current_A > 0.01 ? "cargando" : (d.current_A < -0.01 ? "descargando" : "en reposo");
  document.getElementById("last-update").textContent = "última lectura: " + (d.ts || "—");

  const cells = d.cell_voltages_V || [];
  const box = document.getElementById("cells");
  if (cells.length === 0) {
    box.innerHTML = '<span class="muted">Sin datos</span>';
    document.getElementById("cell-info").textContent = "";
  } else {
    const bal = d.balance_status || 0;
    box.innerHTML = cells.map((v, i) =>
      '<div class="cell"><div class="n">C' + (i + 1) + '</div><div class="v">' + fmt(v, 3) +
      ' V</div>' + (((bal >> i) & 1) ? '<div class="bal">BAL</div>' : "") + "</div>"
    ).join("");
    const min = Math.min.apply(null, cells);
    const max = Math.max.apply(null, cells);
    document.getElementById("cell-info").textContent =
      cells.length + " celdas · min " + fmt(min, 3) + " V · max " + fmt(max, 3) +
      " V · Δ " + fmt(max - min, 3) + " V";
  }

  renderTemperatures(d);
  renderAlerts(d);
}

function renderConfig(payload) {
  const body = document.querySelector("#thresholds tbody");
  const info = document.getElementById("config-info");
  const d = payload.data;
  if (!d) { body.innerHTML = '<tr><td class="muted">Sin datos</td><td></td></tr>'; info.textContent = ""; return; }
  body.innerHTML = THRESHOLD_ROWS.map(([key, label, unit]) =>
    "<tr><td>" + label + "</td><td>" + fmt(d[key], 2) + " " + unit + "</td></tr>"
  ).join("");
  info.textContent = "actualizado: " + new Date().toLocaleTimeString();
}

function drawChart(points) {
  const canvas = document.getElementById("chart");
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  const padL = 56, padR = 12, padT = 14, padB = 28;
  ctx.clearRect(0, 0, W, H);

  if (!points || points.length === 0) {
    ctx.fillStyle = "#8b96ad";
    ctx.font = "13px system-ui";
    ctx.fillText("Sin datos en el historial", padL, H / 2);
    document.getElementById("chart-info").textContent = "";
    return;
  }

  const vals = points.map(p => p.value);
  let min = Math.min.apply(null, vals);
  let max = Math.max.apply(null, vals);
  if (min === max) { min -= 1; max += 1; }
  const span = max - min;
  min -= span * 0.08;
  max += span * 0.08;

  const x = i => padL + (points.length === 1 ? 0 : (i / (points.length - 1)) * (W - padL - padR));
  const y = v => padT + (1 - (v - min) / (max - min)) * (H - padT - padB);

  ctx.strokeStyle = "#263049";
  ctx.fillStyle = "#8b96ad";
  ctx.font = "11px system-ui";
  ctx.lineWidth = 1;
  const ticks = 4;
  for (let t = 0; t <= ticks; t++) {
    const v = min + (t / ticks) * (max - min);
    const yy = y(v);
    ctx.beginPath();
    ctx.moveTo(padL, yy);
    ctx.lineTo(W - padR, yy);
    ctx.stroke();
    ctx.fillText(v.toFixed(2), 6, yy + 4);
  }

  ctx.strokeStyle = "#4da3ff";
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((p, i) => {
    const px = x(i), py = y(p.value);
    if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  });
  ctx.stroke();

  ctx.fillStyle = "#8b96ad";
  ctx.fillText(points[0].ts || "", padL, H - 8);
  const last = points[points.length - 1].ts || "";
  ctx.fillText(last, W - padR - ctx.measureText(last).width, H - 8);

  document.getElementById("chart-info").textContent =
    METRIC_LABEL[activeMetric] + " · " + points.length + " puntos · " +
    "min " + Math.min.apply(null, vals).toFixed(3) + " · " +
    "max " + Math.max.apply(null, vals).toFixed(3);
}

async function refreshStatus() {
  try {
    renderStatus(await fetchJSON("/api/status"));
  } catch (e) {
    setBadge(false);
    document.getElementById("last-update").textContent = "API no disponible";
  }
}

async function refreshConfig() {
  try {
    renderConfig(await fetchJSON("/api/config"));
  } catch (e) {
    renderConfig({ data: null });
  }
}

async function refreshHistory() {
  try {
    const payload = await fetchJSON("/api/history/" + activeMetric + "?limit=200");
    drawChart(payload.points || []);
  } catch (e) {
    drawChart([]);
    document.getElementById("chart-info").textContent = "API no disponible";
  }
}

document.getElementById("metric-tabs").addEventListener("click", ev => {
  const btn = ev.target.closest("button[data-metric]");
  if (!btn) return;
  activeMetric = btn.dataset.metric;
  document.querySelectorAll("#metric-tabs button").forEach(b => b.classList.toggle("active", b === btn));
  refreshHistory();
});

// --- Real-time link: WebSocket push with polling fallback ---
let pollingTimer = null;
let ws = null;
let wsRetry = 1000;
let lastStaticVersion = null;

function setLink(label, cls) {
  const b = document.getElementById("link-badge");
  b.textContent = label;
  b.className = "badge " + (cls || "");
}

function startPolling() {
  if (!pollingTimer) pollingTimer = setInterval(refreshStatus, 2000);
}
function stopPolling() {
  if (pollingTimer) { clearInterval(pollingTimer); pollingTimer = null; }
}

function connectWS() {
  try {
    const proto = location.protocol === "https:" ? "wss://" : "ws://";
    ws = new WebSocket(proto + location.host + "/ws");
  } catch (e) {
    startPolling();
    return;
  }
  ws.onopen = () => { setLink("WS", "on"); stopPolling(); wsRetry = 1000; };
  ws.onmessage = ev => {
    try {
      const m = JSON.parse(ev.data);
      if (m.type !== "status") return;
      if (typeof m.static_version === "number") {
        if (lastStaticVersion !== null && m.static_version !== lastStaticVersion) {
          location.reload();  // dev live-reload: static files changed
          return;
        }
        lastStaticVersion = m.static_version;
      }
      renderStatus(m);
    } catch (e) {}
  };
  ws.onclose = () => {
    setLink("polling", "");
    startPolling();
    setTimeout(connectWS, wsRetry);
    wsRetry = Math.min(wsRetry * 2, 15000);
  };
  ws.onerror = () => { try { ws.close(); } catch (e) {} };
}

// --- Charge/balance cycle log (GET /api/balance) ---
const BALANCE_THRESHOLD_MV = 30;
const BALANCE_TABLE_ROWS = 20;

function cellKeysOf(point) {
  return Object.keys(point || {})
    .filter(k => /^cell\d+_v$/.test(k))
    .sort((a, b) => parseInt(a.match(/\d+/)[0], 10) - parseInt(b.match(/\d+/)[0], 10));
}

function drawBalanceChart(points) {
  const canvas = document.getElementById("balance-chart");
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  const padL = 56, padR = 12, padT = 14, padB = 28;
  ctx.clearRect(0, 0, W, H);
  const info = document.getElementById("balance-info");

  if (!points || points.length === 0) {
    ctx.fillStyle = "#8b96ad";
    ctx.font = "13px system-ui";
    ctx.fillText("Sin datos del ciclo de balanceo", padL, H / 2);
    info.textContent = "";
    return;
  }

  const vals = points.map(p => p.delta_mv || 0);
  let min = Math.min.apply(null, vals.concat([BALANCE_THRESHOLD_MV]));
  let max = Math.max.apply(null, vals.concat([BALANCE_THRESHOLD_MV]));
  if (min === max) { min -= 1; max += 1; }
  const span = max - min;
  min -= span * 0.08;
  max += span * 0.08;

  const x = i => padL + (points.length === 1 ? 0 : (i / (points.length - 1)) * (W - padL - padR));
  const y = v => padT + (1 - (v - min) / (max - min)) * (H - padT - padB);

  ctx.strokeStyle = "#263049";
  ctx.fillStyle = "#8b96ad";
  ctx.font = "11px system-ui";
  ctx.lineWidth = 1;
  for (let t = 0; t <= 4; t++) {
    const v = min + (t / 4) * (max - min);
    const yy = y(v);
    ctx.beginPath();
    ctx.moveTo(padL, yy);
    ctx.lineTo(W - padR, yy);
    ctx.stroke();
    ctx.fillText(v.toFixed(0), 6, yy + 4);
  }

  // Threshold line (balance start delta).
  const ty = y(BALANCE_THRESHOLD_MV);
  ctx.strokeStyle = "#ffc857";
  ctx.setLineDash([6, 4]);
  ctx.beginPath();
  ctx.moveTo(padL, ty);
  ctx.lineTo(W - padR, ty);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = "#ffc857";
  ctx.fillText(BALANCE_THRESHOLD_MV + " mV", padL + 4, ty - 4);

  // Delta between cells.
  ctx.strokeStyle = "#4da3ff";
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((p, i) => {
    const px = x(i), py = y(p.delta_mv || 0);
    if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  });
  ctx.stroke();

  // Mark samples where balancing was reported (reg12 != 0).
  ctx.fillStyle = "#39d98a";
  points.forEach((p, i) => {
    if ((p.reg12_balance || 0) !== 0) {
      ctx.beginPath();
      ctx.arc(x(i), y(p.delta_mv || 0), 3, 0, 2 * Math.PI);
      ctx.fill();
    }
  });

  ctx.fillStyle = "#8b96ad";
  ctx.fillText(points[0].ts || "", padL, H - 8);
  const last = points[points.length - 1].ts || "";
  ctx.fillText(last, W - padR - ctx.measureText(last).width, H - 8);

  info.textContent = points.length + " muestras · Δ max " +
    Math.max.apply(null, vals) + " mV · umbral " + BALANCE_THRESHOLD_MV + " mV";
}

function renderBalanceTable(points) {
  const table = document.getElementById("balance-table");
  if (!points || points.length === 0) {
    table.innerHTML = '<tbody><tr><td class="muted">Sin datos</td></tr></tbody>';
    return;
  }
  const cellKeys = cellKeysOf(points[points.length - 1]);
  const head = ["Hora"].concat(cellKeys.map(k => "C" + k.match(/\d+/)[0]))
    .concat(["ΔmV", "reg12", "reg13", "warn", "prot"]);
  let html = "<thead><tr>" + head.map(h => "<th>" + h + "</th>").join("") + "</tr></thead><tbody>";
  points.slice(-BALANCE_TABLE_ROWS).reverse().forEach(p => {
    const bal = (p.reg12_balance || 0) !== 0;
    const style = bal ? ' style="background:rgba(57,217,138,.15)"' : "";
    const t = (p.ts || "").split(" ")[1] || p.ts || "";
    html += "<tr" + style + "><td>" + t + "</td>";
    cellKeys.forEach(k => { html += "<td>" + fmt(p[k], 3) + "</td>"; });
    html += "<td>" + fmt(p.delta_mv, 0) + "</td>";
    html += "<td>" + (p.reg12_balance || 0) + "</td>";
    html += "<td>" + (p.reg13 || 0) + "</td>";
    html += "<td>" + (p.warn_hex || "—") + "</td>";
    html += "<td>" + (p.prot_hex || "—") + "</td></tr>";
  });
  table.innerHTML = html + "</tbody>";
}

async function refreshBalance() {
  try {
    const payload = await fetchJSON("/api/balance?limit=500");
    const points = payload.points || [];
    drawBalanceChart(points);
    renderBalanceTable(points);
  } catch (e) {
    drawBalanceChart([]);
    renderBalanceTable([]);
    document.getElementById("balance-info").textContent = "API no disponible";
  }
}

// --- Low-SOC browser push alerts ---
const ALERT = { swReg: null, subscribed: false, threshold: 10, highThreshold: 95 };

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

function setAlertNote(msg) {
  document.getElementById("alert-note").textContent = msg;
}

function updateAlertStatus() {
  const parts = [];
  parts.push("secure: " + (window.isSecureContext ? "sí" : "NO"));
  parts.push(("serviceWorker" in navigator) ? "SW ok" : "sin SW");
  parts.push(("PushManager" in window) ? "Push ok" : "sin Push");
  parts.push("permiso: " + (("Notification" in window) ? Notification.permission : "n/a"));
  parts.push(ALERT.subscribed ? "suscripto" : "sin suscripción");
  document.getElementById("alert-status").textContent = parts.join(" · ");
}

async function registerSW() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    setAlertNote("Este navegador no soporta notificaciones push.");
    return null;
  }
  if (!window.isSecureContext) {
    setAlertNote("Requiere https:// o http://localhost (no funciona por IP en HTTP).");
    return null;
  }
  try {
    ALERT.swReg = await navigator.serviceWorker.register("/sw.js");
    return ALERT.swReg;
  } catch (e) {
    console.error("SW register error:", e);
    setAlertNote("No se pudo registrar el service worker: " + e.message);
    return null;
  }
}

async function enableNotifications() {
  const reg = ALERT.swReg || (await registerSW());
  if (!reg) return;
  if (!("Notification" in window)) {
    setAlertNote("Este navegador no soporta la Notification API.");
    return;
  }
  const perm = await Notification.requestPermission();
  if (perm !== "granted") {
    setAlertNote("Permiso de notificaciones: " + perm);
    updateAlertStatus();
    return;
  }
  try {
    const ready = await navigator.serviceWorker.ready;
    const res = await fetchJSON("/api/push/public_key");
    const sub = await ready.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(res.key),
    });
    const r = await fetch("/api/push/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sub),
    });
    const j = await r.json();
    if (!j.ok) {
      setAlertNote("El servidor no guardó la suscripción.");
      updateAlertStatus();
      return;
    }
    ALERT.subscribed = true;
    setAlertNote("Notificaciones activadas. Pulsa «Probar».");
  } catch (e) {
    console.error("push subscribe error:", e);
    setAlertNote("Error al suscribir: " + (e && e.message ? e.message : e));
  }
  updateAlertStatus();
}

async function saveThreshold() {
  const low = Number(document.getElementById("soc-threshold").value);
  const high = Number(document.getElementById("soc-high-threshold").value);
  if (!Number.isFinite(low) || low <= 0 || low >= 100) {
    setAlertNote("SOC mínimo inválido (1–99).");
    return;
  }
  if (!Number.isFinite(high) || high <= 0 || high >= 100) {
    setAlertNote("SOC máximo inválido (1–99).");
    return;
  }
  if (high <= low) {
    setAlertNote("El SOC máximo debe ser mayor que el mínimo.");
    return;
  }
  try {
    const r = await fetch("/api/alerts/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ soc_alert_pct: low, soc_high_alert_pct: high }),
    });
    const j = await r.json();
    ALERT.threshold = j.soc_alert_pct;
    ALERT.highThreshold = j.soc_high_alert_pct;
    setAlertNote("Umbrales guardados: mínimo " + j.soc_alert_pct +
      "% · máximo " + j.soc_high_alert_pct + "%.");
  } catch (e) {
    setAlertNote("No se pudo guardar: " + e.message);
  }
}

async function testPush() {
  try {
    const r = await fetch("/api/push/test", { method: "POST" });
    const j = await r.json();
    setAlertNote("Push de prueba enviado a " + j.sent + " dispositivo(s)." +
      (j.sent === 0 ? " — activa las notificaciones primero." : ""));
  } catch (e) {
    setAlertNote("Error al probar: " + e.message);
  }
}

async function refreshAlertConfig() {
  try {
    const j = await fetchJSON("/api/alerts/config");
    ALERT.threshold = j.soc_alert_pct;
    ALERT.highThreshold = j.soc_high_alert_pct;
    document.getElementById("soc-threshold").value = j.soc_alert_pct;
    document.getElementById("soc-high-threshold").value = j.soc_high_alert_pct;
    const firedLow = j.fired ? " · ALERTA BAJA" : "";
    const firedHigh = j.fired_high ? " · ALERTA ALTA" : "";
    document.getElementById("alert-status").textContent =
      "mín " + j.soc_alert_pct + "% · máx " + j.soc_high_alert_pct + "%" +
      firedLow + firedHigh;
  } catch (e) {}
}

async function initAlerts() {
  const reg = await registerSW();
  if (reg) {
    try {
      const ready = await navigator.serviceWorker.ready;
      ALERT.subscribed = !!(await ready.pushManager.getSubscription());
    } catch (e) {}
  }
  updateAlertStatus();
  refreshAlertConfig();
}

document.getElementById("btn-enable").addEventListener("click", enableNotifications);
document.getElementById("btn-save-threshold").addEventListener("click", saveThreshold);
document.getElementById("btn-test").addEventListener("click", testPush);

refreshStatus();
refreshConfig();
refreshHistory();
refreshBalance();
initAlerts();
startPolling();
connectWS();
setInterval(refreshHistory, 10000);
setInterval(refreshConfig, 60000);
setInterval(refreshBalance, 10000);
setInterval(refreshAlertConfig, 30000);
