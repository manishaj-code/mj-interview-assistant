from dataclasses import dataclass


@dataclass(frozen=True)
class LlmConfig:
    model: str
    max_tokens: int
    temperature: float
    answer_style: str  # "concise" | "detailed" | "star_format"


@dataclass(frozen=True)
class SttConfig:
    engine: str  # "local" | "cloud"
    local_model_size: str  # "tiny" | "base" | "small" | "medium" | "large-v3"
    cloud_provider: str | None  # "deepgram" | None


@dataclass(frozen=True)
class QuestionDetectionConfig:
    silence_gap_ms: int
    use_llm_fallback_classifier: bool


@dataclass(frozen=True)
class ContextConfig:
    max_history_pairs: int
    resume_path: str | None
    job_description: str


@dataclass(frozen=True)
class AudioConfig:
    input_device: str
    sample_rate: int
    chunk_ms: int


@dataclass(frozen=True)
class OverlayConfig:
    always_on_top: bool
    content_protection: bool
    opacity: float
    hotkey_toggle_visibility: str
    hotkey_panic_hide: str


@dataclass(frozen=True)
class StorageConfig:
    session_history_enabled: bool
    session_history_path: str


@dataclass(frozen=True)
class ServerConfig:
    host: str  # always "127.0.0.1" for MVP
    port: int  # default 8765


@dataclass(frozen=True)
class AppConfig:
    llm: LlmConfig
    stt: SttConfig
    question_detection: QuestionDetectionConfig
    context: ContextConfig
    audio: AudioConfig
    overlay: OverlayConfig
    storage: StorageConfig
    server: ServerConfig
    anthropic_api_key: str | None
    groq_api_key: str | None
    gemini_api_key: str | None
    deepgram_api_key: str | None
    log_level: str
