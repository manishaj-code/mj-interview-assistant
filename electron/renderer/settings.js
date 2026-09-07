const toast = document.getElementById("toast");
const errorEl = document.getElementById("error");
const hotkeyWarning = document.getElementById("hotkey-warning");
let pendingSave = false;
let capturing = null;

let lastCfg = null;

function fillDevices(devices) {
  const select = document.getElementById("audio-device");
  select.innerHTML = "";
  const list = devices && devices.length ? devices : [{ id: "system_default_loopback", name: "Default loopback" }];
  for (const device of list) {
    const opt = document.createElement("option");
    opt.value = String(device.id);
    opt.textContent = device.name || String(device.id);
    select.appendChild(opt);
  }
  if (lastCfg && lastCfg.audio) select.value = lastCfg.audio.input_device;
}

function applyConfig(cfg) {
  if (!cfg) return;
  lastCfg = cfg;
  document.getElementById("llm-model").value = cfg.llm.model;
  document.getElementById("llm-max-tokens").value = cfg.llm.max_tokens;
  document.getElementById("llm-temperature").value = cfg.llm.temperature;
  document.getElementById("llm-style").value = cfg.llm.answer_style;
  document.getElementById("stt-engine").value = cfg.stt.engine;
  document.getElementById("stt-model").value = cfg.stt.local_model_size;
  document.getElementById("stt-cloud").value = cfg.stt.cloud_provider || "";
  document.getElementById("silence-gap").value = cfg.question_detection.silence_gap_ms;
  document.getElementById("llm-fallback").checked = cfg.question_detection.use_llm_fallback_classifier;
  document.getElementById("audio-device").value = cfg.audio.input_device;
  document.getElementById("chunk-ms").value = String(cfg.audio.chunk_ms);
  document.getElementById("always-on-top").checked = cfg.overlay.always_on_top;
  document.getElementById("content-protection").checked = cfg.overlay.content_protection;
  document.getElementById("opacity").value = cfg.overlay.opacity;
  document.getElementById("hotkey-toggle").value = cfg.overlay.hotkey_toggle_visibility;
  document.getElementById("hotkey-panic").value = cfg.overlay.hotkey_panic_hide;
  document.getElementById("history-enabled").checked = cfg.storage.session_history_enabled;
}

function payload() {
  const cloud = document.getElementById("stt-cloud").value;
  return {
    llm: {
      model: document.getElementById("llm-model").value,
      max_tokens: Number(document.getElementById("llm-max-tokens").value),
      temperature: Number(document.getElementById("llm-temperature").value),
      answer_style: document.getElementById("llm-style").value,
    },
    stt: {
      engine: document.getElementById("stt-engine").value,
      local_model_size: document.getElementById("stt-model").value,
      cloud_provider: cloud || null,
    },
    question_detection: {
      silence_gap_ms: Number(document.getElementById("silence-gap").value),
      use_llm_fallback_classifier: document.getElementById("llm-fallback").checked,
    },
    audio: {
      input_device: document.getElementById("audio-device").value,
      chunk_ms: Number(document.getElementById("chunk-ms").value),
    },
    overlay: {
      always_on_top: document.getElementById("always-on-top").checked,
      content_protection: document.getElementById("content-protection").checked,
      opacity: Number(document.getElementById("opacity").value),
      hotkey_toggle_visibility: document.getElementById("hotkey-toggle").value,
      hotkey_panic_hide: document.getElementById("hotkey-panic").value,
    },
    storage: {
      session_history_enabled: document.getElementById("history-enabled").checked,
    },
  };
}

function bindHotkey(id) {
  const field = document.getElementById(id);
  field.addEventListener("click", () => {
    capturing = field;
    field.value = "Press keys...";
  });
}

window.addEventListener("keydown", (event) => {
  if (!capturing) return;
  event.preventDefault();
  const skip = ["Control", "Shift", "Alt", "Meta"];
  if (skip.includes(event.key)) return;
  const parts = [];
  if (event.ctrlKey || event.metaKey) parts.push("CommandOrControl");
  if (event.altKey) parts.push("Alt");
  if (event.shiftKey) parts.push("Shift");
  const key = event.key.length === 1 ? event.key.toUpperCase() : event.key;
  parts.push(key);
  capturing.value = parts.join("+");
  capturing = null;
});

bindHotkey("hotkey-toggle");
bindHotkey("hotkey-panic");

window.api.onEvent((msg) => {
  if (!msg) return;
  if (msg.type === "audio_devices") {
    fillDevices((msg.payload || {}).devices || []);
  }
  if (msg.type === "error") {
    errorEl.textContent = (msg.payload && (msg.payload.message || msg.payload.code)) || "error";
    pendingSave = false;
    toast.hidden = true;
  }
  if (msg.type === "status" && pendingSave) {
    pendingSave = false;
    if (!errorEl.textContent) {
      toast.hidden = false;
      setTimeout(() => {
        toast.hidden = true;
      }, 1500);
    }
  }
});

window.api.onHotkeyWarning((text) => {
  hotkeyWarning.textContent = text || "";
});

document.getElementById("form").addEventListener("submit", (event) => {
  event.preventDefault();
  errorEl.textContent = "";
  pendingSave = true;
  window.api.send({ type: "update_config", payload: payload() });
});

window.api.getConfig().then(applyConfig);
window.api.send({ type: "list_audio_devices" });
window.api.onBackendState((data) => {
  if (data.connected) window.api.send({ type: "list_audio_devices" });
});
