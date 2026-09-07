(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.OverlayStore = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  function createStore() {
    let state = {
      status: "disconnected",
      transcript: "",
      question: "",
      answer: "",
      error: "",
      startEnabled: false,
      missingApiKey: false,
      listening: false,
      warnings: [],
    };
    function apply(msg) {
      if (!msg || !msg.type) return;
      const p = msg.payload || {};
      if (msg.type === "status") {
        state.status = p.state;
        state.startEnabled = true;
        state.missingApiKey = !!p.missing_api_key;
        state.listening = p.state === "listening";
        state.warnings = Array.isArray(p.warnings) ? p.warnings : [];
      }
      if (msg.type === "transcript_partial" || msg.type === "transcript_final") {
        state.transcript = p.text || "";
      }
      if (msg.type === "question_detected") {
        state.question = p.question_text || "";
      }
      if (msg.type === "answer_token") {
        if (p.seq === 1) state.answer = "";
        state.answer += p.token || "";
      }
      if (msg.type === "answer_complete") state.answer = p.full_answer || state.answer;
      if (msg.type === "error") state.error = p.message || p.code;
    }
    function dismissError() {
      state.error = "";
    }
    function get() {
      return { ...state };
    }
    return { apply, get, dismissError };
  }
  return { createStore };
});
