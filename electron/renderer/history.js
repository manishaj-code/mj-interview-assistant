const root = document.getElementById("root");

function render(sessions) {
  if (!sessions || !sessions.length) {
    root.innerHTML = '<p class="empty">No session history.</p>';
    return;
  }
  root.innerHTML = "";
  for (const session of sessions) {
    const box = document.createElement("section");
    box.className = "session";
    const heading = document.createElement("h2");
    heading.textContent = `Session ${session.id}`;
    box.appendChild(heading);
    const entries = session.entries || [];
    if (!entries.length) {
      const p = document.createElement("p");
      p.className = "empty";
      p.textContent = "No session history.";
      box.appendChild(p);
    }
    for (const entry of entries) {
      const div = document.createElement("div");
      div.className = "entry";
      const time = document.createElement("time");
      time.textContent = new Date(entry.timestamp_ms).toLocaleString();
      const q = document.createElement("div");
      q.className = "q";
      q.textContent = entry.question_text || "";
      const a = document.createElement("div");
      a.className = "a";
      a.textContent = entry.full_answer || "";
      div.append(time, q, a);
      box.appendChild(div);
    }
    root.appendChild(box);
  }
}

window.api.onEvent((msg) => {
  if (msg && msg.type === "history_data") {
    render((msg.payload || {}).sessions || []);
  }
});

window.api.onBackendState((data) => {
  if (data.connected) window.api.send({ type: "list_history" });
});

window.api.send({ type: "list_history" });
