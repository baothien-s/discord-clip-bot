const drop = document.getElementById("drop");
const picker = document.getElementById("picker");
const queueEl = document.getElementById("queue");
const countEl = document.getElementById("count");
const sendBtn = document.getElementById("send");
const clearBtn = document.getElementById("clear");
const statusEl = document.getElementById("status");
const bannerEl = document.getElementById("banner");
const logEl = document.getElementById("log");
const refreshBtn = document.getElementById("refresh");

const files = []; // {file, url, statusEl}

function fmtMB(n) { return (n / 1048576).toFixed(1) + " MB"; }

fetch("/api/config").then(r => r.json()).then(cfg => {
  let msg = `Max upload: ${cfg.max_upload_mb} MB per file. ` +
    `Files over ${cfg.discord_upload_limit_mb} MB are posted as self-hosted links.`;
  if (!cfg.channel_configured) msg += " WARNING: CHANNEL_ID is not set — bot cannot post.";
  if (cfg.links_local_only)
    msg += ` NOTE: PUBLIC_BASE_URL is ${cfg.public_base_url} — links only work on this machine until you set a LAN IP or tunnel.`;
  bannerEl.textContent = msg;
  bannerEl.classList.remove("hidden");
}).catch(() => {});

function render() {
  queueEl.innerHTML = "";
  files.forEach((it, i) => {
    const card = document.createElement("div");
    card.className = "card";
    let media;
    if (it.file.type.startsWith("image/")) {
      media = document.createElement("img");
      media.src = it.url;
    } else {
      media = document.createElement("video");
      media.src = it.url;
      media.controls = true;
      media.muted = true;
    }
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = it.file.name;
    const size = document.createElement("div");
    size.className = "size";
    size.textContent = fmtMB(it.file.size);
    const rm = document.createElement("button");
    rm.className = "rm";
    rm.textContent = "✕";
    rm.onclick = () => { URL.revokeObjectURL(it.url); files.splice(i, 1); render(); };
    const st = document.createElement("div");
    st.className = "st";
    it.statusEl = st;
    if (it.status) { st.textContent = it.status; st.classList.add(it.statusCls || ""); }
    card.append(media, name, size, rm, st);
    queueEl.append(card);
  });
  countEl.textContent = files.length;
  sendBtn.disabled = files.length === 0;
}

function addFiles(list) {
  for (const f of list) {
    if (!f.type.startsWith("image/") && !f.type.startsWith("video/")) continue;
    files.push({ file: f, url: URL.createObjectURL(f) });
  }
  render();
}

drop.addEventListener("dragover", e => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", e => {
  e.preventDefault(); drop.classList.remove("over");
  addFiles(e.dataTransfer.files);
});
picker.addEventListener("change", () => { addFiles(picker.files); picker.value = ""; });
clearBtn.onclick = () => { files.forEach(it => URL.revokeObjectURL(it.url)); files.length = 0; render(); };

sendBtn.onclick = async () => {
  if (!files.length) return;
  sendBtn.disabled = true;
  statusEl.textContent = `Uploading ${files.length} file(s)...`;
  files.forEach(it => { it.status = "uploading..."; });
  render();
  const fd = new FormData();
  files.forEach(it => fd.append("files", it.file, it.file.name));
  try {
    const r = await fetch("/api/send", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || r.statusText);
    const byName = {};
    data.results.forEach(res => { (byName[res.original_name] ||= []).push(res); });
    files.forEach(it => {
      const res = (byName[it.file.name] || []).shift();
      if (!res) { it.status = "unknown"; it.statusCls = "err"; }
      else if (res.status === "queued") { it.status = "queued for Discord ✓"; it.statusCls = "ok"; }
      else { it.status = "rejected: " + (res.error || "?"); it.statusCls = "err"; }
    });
    const ok = data.results.filter(x => x.status === "queued").length;
    statusEl.textContent = `${ok}/${data.results.length} queued for Discord.`;
    refreshLog();
  } catch (e) {
    statusEl.textContent = "Upload failed: " + e.message;
  }
  render();
  sendBtn.disabled = files.length === 0;
};

async function refreshLog() {
  try {
    const r = await fetch("/api/log?limit=20");
    const data = await r.json();
    logEl.textContent = data.rows.length
      ? data.rows.map(x => `${x.timestamp} | ${x.original_name} | ${x.mode || "?"} | ${x.status} | ${x.url || x.message_id || ""}`).join("\n")
      : "(empty)";
  } catch { logEl.textContent = "(log unavailable)"; }
}
refreshBtn.onclick = refreshLog;
refreshLog();
render();
