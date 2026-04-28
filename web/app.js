// NetProbeKit · Test Bench — static report viewer.
// Fed by a `report.json` file (drag-and-drop or fetched from ./report.json).

const root = document.getElementById("app");

function el(t, a = {}, ...c) {
  const e = document.createElement(t);
  for (const [k, v] of Object.entries(a)) {
    if (k === "class") e.className = v;
    else if (k === "html") e.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2).toLowerCase(), v);
    else if (v != null) e.setAttribute(k, v);
  }
  for (const x of c.flat()) {
    if (x == null) continue;
    e.append(typeof x === "string" || typeof x === "number" ? document.createTextNode(String(x)) : x);
  }
  return e;
}

async function loadDefault() {
  try {
    const r = await fetch("./report.json");
    if (!r.ok) throw new Error("no default report");
    return await r.json();
  } catch {
    return null;
  }
}

function classify(ok) { return ok ? "ok" : "err"; }
function dot(ok)      { return el("span", { class: "dot " + (ok ? "ok" : "err") }); }
function tag(label, kind) { return el("span", { class: "tag " + kind }, label); }

function renderEthernet(eth) {
  return el(
    "div",
    { class: "module" },
    el("div", { class: "head" },
      dot(eth.ping?.ok && eth.throughput?.ok && eth.integrity?.ok),
      el("h2", {}, "Ethernet"),
      el("span", { class: "ch" }, "ch.01"),
    ),
    readout("Link", `${eth.ping?.latency_ms.toFixed(2)} ms p99`,
            classify(eth.ping?.ok)),
    readout("Throughput", `${eth.throughput?.mb_per_sec.toFixed(2)} MB/s`,
            eth.throughput?.mb_per_sec >= 1.0 ? "ok" : "warn"),
    readout("Integrity CRC", `${eth.integrity?.target_crc}`, classify(eth.integrity?.ok)),
    readout("Expected CRC", `${eth.integrity?.expected_crc}`, "ok"),
    el("div", { class: "tags" },
      tag(eth.ping?.ok ? "PING OK" : "PING FAIL", classify(eth.ping?.ok)),
      tag(eth.throughput?.ok ? "BW OK" : "BW LOW", classify(eth.throughput?.ok)),
      tag(eth.integrity?.ok ? "CRC OK" : "CRC MISMATCH", classify(eth.integrity?.ok)),
    ),
  );
}

function renderCAN(canMod) {
  const allValid = (canMod.frames || []).every((f) => f.valid);
  return el(
    "div",
    { class: "module" },
    el("div", { class: "head" }, dot(allValid),
      el("h2", {}, "CAN Bus"), el("span", { class: "ch" }, "ch.02")),
    readout("Frames received", String(canMod.frames?.length ?? 0), "ok"),
    readout("All valid", allValid ? "yes" : "no", classify(allValid)),
    ...(canMod.frames || []).slice(0, 6).map((f) =>
      readout(`0x${f.id.toString(16).padStart(3, "0")}`,
        `dlc=${f.dlc} ${f.data.map((b) => b.toString(16).padStart(2, "0")).join(" ")}`,
        f.valid ? "ok" : "err"),
    ),
  );
}

function renderSensors(sensors) {
  const allOK = sensors.every((s) => s.in_range);
  return el(
    "div",
    { class: "module" },
    el("div", { class: "head" }, dot(allOK),
      el("h2", {}, "Sensors"), el("span", { class: "ch" }, "ch.03")),
    ...sensors.map(sensorRow),
  );
}

function sensorRow(s) {
  // Build a tiny gauge (0..100% mapped onto an arbitrary band).
  const ranges = { tempC0: [5, 40], tempC1: [5, 40], vbat: [11, 13.5], imu_g: [9.7, 9.9] };
  const [lo, hi] = ranges[s.id] || [0, 100];
  const pct = Math.max(0, Math.min(100, ((s.value - lo) / (hi - lo)) * 100));
  return el(
    "div",
    { class: "sensor-row" },
    el("div", { class: "id" }, s.id),
    el(
      "div",
      { class: "gauge" },
      el("div", { class: "ok-band", style: "left: 10%; width: 80%" }),
      el("div", { class: "needle", style: `left: ${pct}%` }),
    ),
    el("div", { class: `val ${s.in_range ? "ok" : "err"}` }, s.value.toFixed(2)),
  );
}

function renderFirmware(fw) {
  const ok = fw.is_semver && fw.version === "1.4.2";
  return el(
    "div",
    { class: "module" },
    el("div", { class: "head" }, dot(ok),
      el("h2", {}, "Firmware"), el("span", { class: "ch" }, "ch.04")),
    readout("Version", fw.version || "—", classify(ok)),
    readout("Region CRC", fw.crc || "—", "ok"),
    el("div", { class: "tags" },
      tag(fw.is_semver ? "SEMVER OK" : "SEMVER FAIL", classify(fw.is_semver)),
      tag(fw.version === "1.4.2" ? "PINNED MATCH" : "VERSION DRIFT",
          fw.version === "1.4.2" ? "ok" : "err"),
    ),
  );
}

function readout(k, v, cls) {
  return el("div", { class: "readout" },
    el("div", { class: "k" }, k),
    el("div", { class: `v ${cls || ""}` }, v),
  );
}

function emptyState(onPick) {
  return el(
    "div",
    { class: "empty" },
    "no report.json found · drop one onto this page or run:",
    el("br"),
    el("code", {}, "  python -m netprobe.runner ./target/target > web/report.json"),
    el("br"),
    el("button", { onClick: () => onPick() }, "Pick file…"),
  );
}

async function pickFile() {
  return new Promise((resolve) => {
    const inp = el("input", { type: "file", accept: ".json" });
    inp.style.display = "none";
    document.body.append(inp);
    inp.addEventListener("change", async () => {
      const f = inp.files?.[0];
      if (!f) return resolve(null);
      const text = await f.text();
      resolve(JSON.parse(text));
    });
    inp.click();
  });
}

async function render() {
  let report = await loadDefault();
  if (!report) {
    root.innerHTML = "";
    root.append(el("div", { class: "chassis" },
      el("div", { class: "label" },
        el("span", { class: "badge" }, "OFFLINE"),
        el("h1", {}, "NetProbeKit · TestBench"),
      ),
      emptyState(async () => {
        const r = await pickFile();
        if (r) draw(r);
      })));
    return;
  }
  draw(report);
}

function draw(report) {
  root.innerHTML = "";
  const eth = report.ethernet || {};
  const canMod = report.can || {};
  const sensors = report.sensors || [];
  const fw = report.firmware || {};
  const ok = (eth.ping?.ok && eth.throughput?.ok && eth.integrity?.ok &&
              (canMod.frames || []).every((f) => f.valid) &&
              sensors.every((s) => s.in_range) &&
              fw.is_semver);
  root.append(
    el(
      "div",
      { class: "chassis" },
      el(
        "div",
        { class: "label" },
        el("span", { class: "badge" }, ok ? "PASS" : "FAULT"),
        el("h1", {}, "NetProbeKit · TestBench"),
        el("small", {}, "session " + (report.session?.started_at?.slice(0, 19) || "—")),
      ),
      el("div", { class: "modules" },
        renderEthernet(eth),
        renderCAN(canMod),
        renderSensors(sensors),
        renderFirmware(fw),
      ),
      el("footer", { class: "foot" },
        el("span", {}, "RIG ", el("b", {}, "RACK 7B")),
        el("span", {}, "OPERATOR ", el("b", {}, "you")),
        el("span", {}, "TARGET FW ", el("b", {}, fw.version || "—")),
        el("span", { style: "margin-left: auto" }, ok ? "READY TO INTEGRATE" : "INVESTIGATE BEFORE INTEGRATION"),
      ),
    ),
  );
}

render();
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", async (e) => {
  e.preventDefault();
  const f = e.dataTransfer?.files?.[0];
  if (!f) return;
  const text = await f.text();
  draw(JSON.parse(text));
});
