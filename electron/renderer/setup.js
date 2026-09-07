const banner = document.getElementById("key-banner");
const errorEl = document.getElementById("error");
const toast = document.getElementById("toast");
const preview = document.getElementById("resume-preview");
const chars = document.getElementById("resume-chars");
const jd = document.getElementById("jd");
let pendingSave = false;
let backendConnected = false;

window.api.onBackendState((data) => {
  backendConnected = !!data.connected;
});

window.api.onEvent((msg) => {
  if (!msg || !msg.type) return;
  const p = msg.payload || {};
  if (msg.type === "status") {
    banner.hidden = !p.missing_api_key;
  }
  if (msg.type === "context_updated") {
    chars.textContent = String(p.resume_chars || 0);
    preview.textContent = p.resume_preview || "";
    errorEl.textContent = "";
    if (pendingSave) {
      pendingSave = false;
      toast.hidden = false;
      setTimeout(() => {
        toast.hidden = true;
      }, 1500);
    }
  }
  if (msg.type === "error") {
    pendingSave = false;
    errorEl.textContent = p.message || p.code || "error";
  }
});

document.getElementById("btn-upload").addEventListener("click", async () => {
  const filePath = await window.api.openResumeDialog();
  if (!filePath) return;
  window.api.send({ type: "extract_resume", payload: { path: filePath } });
});

document.getElementById("btn-save").addEventListener("click", () => {
  if (!backendConnected) {
    errorEl.textContent = "Backend disconnected. Wait and try Save JD again.";
    return;
  }
  pendingSave = true;
  errorEl.textContent = "";
  window.api.send({
    type: "update_context",
    payload: { resume_text: "", job_description: jd.value },
  });
});

document.getElementById("btn-continue").addEventListener("click", () => {
  window.api.showOverlay();
});

window.api.onEvent((msg) => {
  if (!msg || !msg.type) return;
  const p = msg.payload || {};
  if (msg.type === "status") {
    banner.hidden = !p.missing_api_key;
  }
  if (msg.type === "context_updated") {
    chars.textContent = String(p.resume_chars || 0);
    preview.textContent = p.resume_preview || "";
    errorEl.textContent = "";
  }
  if (msg.type === "error") {
    errorEl.textContent = p.message || p.code || "error";
  }
});

document.getElementById("btn-upload").addEventListener("click", async () => {
  const filePath = await window.api.openResumeDialog();
  if (!filePath) return;
  window.api.send({ type: "extract_resume", payload: { path: filePath } });
});

document.getElementById("btn-save").addEventListener("click", () => {
  window.api.send({
    type: "update_context",
    payload: { resume_text: "", job_description: jd.value },
  });
});

document.getElementById("btn-continue").addEventListener("click", () => {
  window.api.showOverlay();
});
