const API = "/api/v1";
const TOKEN = localStorage.getItem("opendoist_token") || "local";
const H = { "Content-Type": "application/json", "Authorization": "Bearer " + TOKEN };
let view = "today";
let activeProject = null;
let editingId = null;
let cache = [];
let projectNames = { "inbox": "Inbox" };

function toast(msg, isErr) {
  const box = document.getElementById("toasts");
  const d = document.createElement("div");
  d.className = "toast" + (isErr ? " error" : "");
  d.textContent = msg;
  box.appendChild(d);
  setTimeout(() => d.remove(), 3200);
}

async function api(path, opts = {}) {
  const r = await fetch(API + path, {
    ...opts,
    headers: { ...H, ...(opts.headers || {}) },
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || ("HTTP " + r.status()));
  }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r.text();
}

function prioClass(p) {
  if (p === 4) return "prio-4 p1";
  if (p === 3) return "prio-3 p2";
  if (p === 2) return "prio-2 p3";
  return "prio-1 p4";
}

function fmtDue(t) {
  const due = t.due || {};
  const day = due.date || (due.datetime || "").slice(0, 10) || "";
  if (!day) return { text: "", over: false };
  const today = new Date().toISOString().slice(0, 10);
  const tm = new Date(Date.parse(today + "T00:00:00Z") + 86400000).toISOString().slice(0, 10);
  let text = day;
  try {
    const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    const [y, m, d] = day.split("-").map(Number);
    text = d + " " + (months[m - 1] || m);
  } catch (e) { /* keep raw */ }
  if (day === today) text = "Today";
  else if (day === tm) text = "Tomorrow";
  if (due.datetime && due.datetime.length > 10) text += " " + due.datetime.slice(11, 16);
  const s = due.string || "";
  if (s && !/[#@]/.test(s) && s !== day && s.length < 40 && s !== t.content) text += " · " + s;
  return { text, over: day < today };
}

function sortTasks(items) {
  const mode = document.getElementById("sort-select").value;
  const arr = [...items];
  if (mode === "date") {
    arr.sort((a, b) => {
      const da = ((a.due || {}).date || (a.due || {}).datetime || "9999");
      const db = ((b.due || {}).date || (b.due || {}).datetime || "9999");
      return da < db ? -1 : da > db ? 1 : 0;
    });
  } else if (mode === "priority") {
    arr.sort((a, b) => (b.priority || 1) - (a.priority || 1));
  }
  return arr; // smart = server order preserved
}

function taskRow(t) {
  const row = document.createElement("div");
  row.className = "task-row";
  const btn = document.createElement("button");
  btn.className = "check " + prioClass(t.priority);
  btn.title = "Complete (priority p" + (5 - (t.priority || 1)) + ")";
  btn.onclick = async () => {
    try {
      await api("/tasks/" + t.id + "/close", { method: "POST", body: "{}" });
      toast("Task completed");
      reload();
    } catch (e) { toast("Complete failed: " + e.message, true); }
  };
  const body = document.createElement("div");
  body.className = "task-body";
  const c = document.createElement("div");
  c.className = "task-content";
  c.textContent = t.content;
  body.appendChild(c);
  const meta = document.createElement("div");
  meta.className = "task-meta";
  const due = fmtDue(t);
  if (due.text) {
    const s = document.createElement("span");
    s.textContent = "📅 " + due.text;
    if (due.over) s.className = "due-over";
    meta.appendChild(s);
  }
  if (t.project_id && t.project_id !== "inbox") {
    const s = document.createElement("span");
    s.textContent = "# " + (projectNames[t.project_id] || t.project_id);
    meta.appendChild(s);
  }
  (t.labels || []).forEach((l) => {
    const s = document.createElement("span");
    s.textContent = "@" + l;
    meta.appendChild(s);
  });
  const pr = document.createElement("span");
  pr.textContent = "p" + (5 - (t.priority || 1));
  meta.appendChild(pr);
  body.appendChild(meta);
  const acts = document.createElement("div");
  acts.className = "task-actions";
  const eb = document.createElement("button");
  eb.textContent = "Edit";
  eb.onclick = () => openEdit(t);
  const db = document.createElement("button");
  db.textContent = "Delete";
  db.onclick = async () => {
    if (!confirm("Delete '" + t.content + "'?")) return;
    try {
      await api("/tasks/" + t.id, { method: "DELETE" });
      toast("Task deleted");
      reload();
    } catch (e) { toast("Delete failed: " + e.message, true); }
  };
  acts.appendChild(eb);
  acts.appendChild(db);
  row.appendChild(btn);
  row.appendChild(body);
  row.appendChild(acts);
  return row;
}

function renderGroups(groups) {
  const box = document.getElementById("task-groups");
  box.innerHTML = "";
  if (!groups.length) {
    const d = document.createElement("div");
    d.className = "empty";
    d.textContent = "No tasks. Enjoy your day!";
    box.appendChild(d);
    return;
  }
  groups.forEach(([title, items, cls]) => {
    const h = document.createElement("div");
    h.className = "group-title" + (cls ? " " + cls : "");
    h.textContent = title;
    box.appendChild(h);
    sortTasks(items).forEach((t) => box.appendChild(taskRow(t)));
  });
  const ci = document.getElementById("count-inbox");
  const ct = document.getElementById("count-today");
  if (ci) ci.textContent = "";
  if (ct) ct.textContent = "";
}

function dayKey(t) {
  const d = t.due || {};
  return d.date || (d.datetime || "").slice(0, 10) || "No date";
}

async function loadToday() {
  document.getElementById("view-title").textContent = "Today";
  const [over, today] = await Promise.all([
    api("/tasks/filter?query=" + encodeURIComponent("overdue")),
    api("/tasks/filter?query=" + encodeURIComponent("today")),
  ]);
  const o = over.results || over || [];
  const td = today.results || today || [];
  // de-dupe overlapping
  const seen = new Set(td.map((t) => t.id));
  const onlyOver = o.filter((t) => !seen.has(t.id));
  cache = [...onlyOver, ...td];
  renderGroups([
    ["Overdue (" + onlyOver.length + ")", onlyOver, "overdue"],
    ["Today (" + td.length + ")", td, ""],
  ]);
}

async function loadInbox() {
  document.getElementById("view-title").textContent = "Inbox";
  const j = await api("/tasks?project_id=inbox");
  const items = j.results || j || [];
  cache = items;
  renderGroups([["Inbox (" + items.length + ")", items, ""]]);
}

async function loadUpcoming() {
  document.getElementById("view-title").textContent = "Upcoming";
  const j = await api("/tasks");
  const items = j.results || j || [];
  cache = items;
  const byDay = {};
  items.forEach((t) => {
    const k = dayKey(t);
    (byDay[k] = byDay[k] || []).push(t);
  });
  const days = Object.keys(byDay).sort();
  renderGroups(days.map((d) => [d + " (" + byDay[d].length + ")", byDay[d], ""]));
}

async function loadProject(pid, name) {
  document.getElementById("view-title").textContent = name || pid;
  const j = await api("/tasks?project_id=" + encodeURIComponent(pid));
  const items = j.results || j || [];
  cache = items;
  renderGroups([[(name || pid) + " (" + items.length + ")", items, ""]]);
}

async function loadSearch(q) {
  document.getElementById("view-title").textContent = "Search: " + q;
  const j = await api("/tasks/filter?query=" + encodeURIComponent(q));
  const items = j.results || j || [];
  cache = items;
  renderGroups([["Results (" + items.length + ")", items, ""]]);
}

async function loadFilters() {
  document.getElementById("view-title").textContent = "Filters & Labels";
  const [projs, labels] = await Promise.all([api("/projects"), api("/labels")]);
  const box = document.getElementById("task-groups");
  box.innerHTML = "";
  const g1 = document.createElement("div");
  g1.className = "group-title";
  g1.textContent = "Projects";
  box.appendChild(g1);
  (projs || []).forEach((p) => {
    const d = document.createElement("div");
    d.className = "task-row";
    d.textContent = "# " + p.name;
    d.style.cursor = "pointer";
    d.onclick = () => setView("project", p);
    box.appendChild(d);
  });
  const g2 = document.createElement("div");
  g2.className = "group-title";
  g2.textContent = "Labels";
  box.appendChild(g2);
  (labels || []).forEach((l) => {
    const d = document.createElement("div");
    d.className = "task-row";
    d.textContent = "@" + l.name;
    d.style.cursor = "pointer";
    d.onclick = () => loadSearch("@" + l.name);
    box.appendChild(d);
  });
}

async function loadProjects() {
  try {
    const projs = await api("/projects");
    const box = document.getElementById("project-list");
    box.innerHTML = "";
    (projs || []).filter((p) => !p.is_deleted).forEach((p) => {
      projectNames[p.id] = p.name;
      const b = document.createElement("button");
      b.className = "proj-item" + (activeProject === p.id ? " active" : "");
      b.innerHTML = "<span>#</span> ";
      b.appendChild(document.createTextNode(p.name));
      b.onclick = () => setView("project", p);
      box.appendChild(b);
    });
  } catch (e) { /* offline */ }
}

async function reload() {
  try {
    await loadProjects();
    if (view === "today") await loadToday();
    else if (view === "inbox") await loadInbox();
    else if (view === "upcoming") await loadUpcoming();
    else if (view === "filters") await loadFilters();
    else if (view === "project" && activeProject) {
      const name = document.getElementById("view-title").textContent;
      await loadProject(activeProject, name);
    }
  } catch (e) { toast("Load failed: " + e.message, true); }
}

function setView(v, proj) {
  view = v;
  document.querySelectorAll("#main-nav .nav-item").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === v)
  );
  if (v === "project" && proj) {
    activeProject = proj.id;
    loadProject(proj.id, proj.name).catch((e) => toast(e.message, true));
    loadProjects();
  } else {
    activeProject = null;
    reload();
  }
}

function openQuick(prefill) {
  const m = document.getElementById("quick-modal");
  m.classList.remove("hidden");
  const inp = document.getElementById("quick-input");
  inp.value = prefill || sessionStorage.getItem("opendoist_draft") || "";
  setTimeout(() => inp.focus(), 30);
}
function closeQuick() {
  document.getElementById("quick-modal").classList.add("hidden");
  sessionStorage.removeItem("opendoist_draft");
}

function openEdit(t) {
  editingId = t.id;
  document.getElementById("edit-input").value = t.content;
  document.getElementById("edit-modal").classList.remove("hidden");
  setTimeout(() => document.getElementById("edit-input").focus(), 30);
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("#main-nav .nav-item[data-view]").forEach((b) =>
    b.addEventListener("click", () => setView(b.dataset.view))
  );
  document.getElementById("nav-add").onclick = () => openQuick();
  document.getElementById("inline-add").onclick = () => openQuick();
  document.getElementById("sort-select").onchange = () => reload();

  const si = document.getElementById("search-input");
  let deb = null;
  si.addEventListener("input", () => {
    clearTimeout(deb);
    const q = si.value.trim();
    if (!q) { if (view === "search") setView("today"); return; }
    deb = setTimeout(() => { view = "search"; loadSearch(q).catch((e) => toast(e.message, true)); }, 350);
  });

  const qi = document.getElementById("quick-input");
  qi.addEventListener("input", () => sessionStorage.setItem("opendoist_draft", qi.value));
  document.querySelectorAll(".chip").forEach((ch) =>
    ch.addEventListener("click", () => {
      qi.value += ch.dataset.add;
      sessionStorage.setItem("opendoist_draft", qi.value);
      qi.focus();
    })
  );
  document.getElementById("quick-cancel").onclick = closeQuick;
  document.getElementById("quick-submit").onclick = async () => {
    const text = qi.value.trim();
    if (!text) { toast("Task name required", true); return; }
    try {
      await api("/tasks/quick", { method: "POST", body: JSON.stringify({ text }) });
      toast("Task added");
      closeQuick();
      qi.value = "";
      reload();
    } catch (e) { toast("Add failed: " + e.message, true); }
  };

  document.getElementById("edit-cancel").onclick = () =>
    document.getElementById("edit-modal").classList.add("hidden");
  document.getElementById("edit-submit").onclick = async () => {
    const v = document.getElementById("edit-input").value.trim();
    if (!v) { toast("Content required", true); return; }
    try {
      await api("/tasks/" + editingId, { method: "POST", body: JSON.stringify({ content: v }) });
      toast("Task updated");
      document.getElementById("edit-modal").classList.add("hidden");
      reload();
    } catch (e) { toast("Update failed: " + e.message, true); }
  };

  const pm = document.getElementById("project-modal");
  document.getElementById("add-project-btn").onclick = () => {
    pm.classList.remove("hidden");
    setTimeout(() => document.getElementById("project-input").focus(), 30);
  };
  document.getElementById("project-cancel").onclick = () => pm.classList.add("hidden");
  document.getElementById("project-submit").onclick = async () => {
    const name = document.getElementById("project-input").value.trim();
    if (!name) { toast("Project name required", true); return; }
    try {
      await api("/projects", { method: "POST", body: JSON.stringify({ name }) });
      toast("Project added");
      pm.classList.add("hidden");
      document.getElementById("project-input").value = "";
      loadProjects();
    } catch (e) { toast("Project add failed: " + e.message, true); }
  };

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      document.querySelectorAll(".modal").forEach((m) => m.classList.add("hidden"));
    }
  });

  reload();
});
