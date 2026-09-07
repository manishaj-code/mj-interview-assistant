const store = window.OverlayStore.createStore();
let backendConnected = false;
let sawStatus = false;
let autoStartSent = false;

function maybeAutoStart() {
  const s = store.get();
  if (autoStartSent) return;
  if (!backendConnected || !sawStatus || !s.startEnabled || s.missingApiKey) return;
  if (s.listening) {
    autoStartSent = true;
    return;
  }
  autoStartSent = true;
  window.api.send({ type: "start_listening" });
}

const el = {
  status: document.getElementById("status-pill"),
  question: document.getElementById("question"),
  answer: document.getElementById("answer"),
  errorBanner: document.getElementById("error-banner"),
  errorText: document.getElementById("error-text"),
  keyBanner: document.getElementById("key-banner"),
  warnBanner: document.getElementById("warn-banner"),
  setup: document.getElementById("btn-setup"),
  history: document.getElementById("btn-history"),
  settings: document.getElementById("btn-settings"),
  hide: document.getElementById("btn-hide"),
  dismiss: document.getElementById("btn-dismiss"),
};

function render() {
  const s = store.get();
  const status = backendConnected ? s.status : "disconnected";
  el.status.textContent = status;
  el.status.className = status;
  el.question.textContent = s.question;
  el.answer.textContent = s.answer;
  el.keyBanner.hidden = !s.missingApiKey;
  const warnings = s.warnings || [];
  el.warnBanner.hidden = warnings.length === 0;
  el.warnBanner.textContent = warnings.join(", ");
  const showError = Boolean(s.error);
  el.errorBanner.hidden = !showError;
  el.errorText.textContent = s.error;
}

window.api.onEvent((msg) => {
  store.apply(msg);
  if (msg && msg.type === "status") {
    sawStatus = true;
    if (msg.payload && msg.payload.state === "listening") {
      store.dismissError();
    }
  }
  render();
  maybeAutoStart();
});

window.api.onBackendState((data) => {
  backendConnected = !!data.connected;
  if (!data.connected) {
    sawStatus = false;
    autoStartSent = false;
    store.apply({
      type: "error",
      payload: { code: "BACKEND_DISCONNECTED", message: "Backend disconnected", fatal: false },
    });
  } else if (store.get().error === "Backend disconnected") {
    store.dismissError();
  }
  render();
  maybeAutoStart();
});

el.setup.addEventListener("click", () => window.api.openSetup());
el.history.addEventListener("click", () => window.api.openHistory());
el.settings.addEventListener("click", () => window.api.openSettings());
el.hide.addEventListener("click", () => window.api.hideOverlay());
el.dismiss.addEventListener("click", () => {
  store.dismissError();
  render();
});

render();
