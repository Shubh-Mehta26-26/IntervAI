from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://intervai:intervai_local_only@127.0.0.1:5433/intervai"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    auth_secret: SecretStr = Field(min_length=32)
    session_ttl_seconds: int = Field(default=86400, ge=300, le=604800)
    cookie_secure: bool = False
    auth_rate_limit_attempts: int = Field(default=10, ge=1)
    auth_rate_limit_ip_attempts: int = Field(default=100, ge=1)
    auth_rate_limit_window_seconds: int = Field(default=900, ge=60)
    storage_root: Path = ROOT / "storage"
    code_runner_url: str = "http://sandbox:8080"
    code_runner_api_key: SecretStr | None = None
    llm_provider: str = "openai"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = ""
    openai_model: str = ""
    openai_api_key: SecretStr | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: int = Field(default=45, ge=5, le=180)
    embedding_provider: str = ""
    embedding_model: str = ""
    embedding_dimensions: int = Field(default=1536, ge=256, le=4096)
    embedding_batch_size: int = Field(default=64, ge=1, le=256)
    retrieval_top_k: int = Field(default=6, ge=1, le=20)
    retrieval_min_similarity: float = Field(default=0.2, ge=-1, le=1)
    stt_provider: str = "vosk"
    stt_model: str = ""
    stt_api_key: SecretStr | None = None
    vosk_model_path: Path | None = None
    tts_provider: str = "espeak"
    tts_model: str = ""
    tts_api_key: SecretStr | None = None
    tts_voice: str = "en"
    tts_speed: float = Field(default=1.0, ge=0.5, le=2.0)
    tts_style: str = (
        "Warm, calm professional interviewer speaking to one person. "
        "Speak slowly and conversationally, around 130 words per minute. "
        "Leave natural pauses between sentences and before the main question. "
        "Use gentle emphasis and curious intonation; never sound like an announcer."
    )
    espeak_executable: str = "espeak-ng"
    speech_language: str = Field(default="en", pattern=r"^[a-z]{2}$")
    speech_locale: str = Field(default="en-IN", pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    speech_vocabulary: list[str] = Field(
        default=[
            "IntervAI",
            "Python",
            "PostgreSQL",
            "pgvector",
            "FastAPI",
            "JavaScript",
            "TypeScript",
            "React",
            "Next.js",
            "SQL",
            "Docker",
            "Kubernetes",
            "API",
        ],
        max_length=100,
    )
    speech_timeout_seconds: int = Field(default=60, ge=5, le=120)
    voice_max_seconds: int = Field(default=180, ge=5, le=180)
    voice_min_speech_seconds: float = Field(default=0.4, ge=0.1, le=3)
    voice_silence_seconds: float = Field(default=3.0, ge=0.5, le=5)
    voice_audio_ttl_seconds: int = Field(default=600, ge=180, le=3600)
    speech_fillers: list[str] = ["um", "uh", "you know"]
    vision_enabled: bool = False
    vision_model_dir: Path = ROOT / "vision/models"
    vision_sample_interval_ms: int = Field(default=1000, ge=500, le=2000)
    vision_detection_threshold: float = Field(default=0.55, ge=0.4, le=0.95)
    vision_absence_ms: int = Field(default=3000, ge=2000, le=10000)
    vision_confirmation_ms: int = Field(default=2000, ge=1000, le=10000)

    @field_validator("storage_root")
    @classmethod
    def resolve_storage_root(cls, value: Path) -> Path:
        # API and worker may start in different working directories.
        return (value if value.is_absolute() else ROOT / value).resolve()

    @model_validator(mode="after")
    def production_security(self):
        if not self.code_runner_url.strip():
            self.code_runner_url = "http://sandbox:8080"
        if self.app_env == "production":
            if not self.cookie_secure or any(
                not url.startswith("https://") for url in self.cors_origins
            ):
                raise ValueError("Production requires secure cookies and HTTPS origins")
        if "*" in self.cors_origins:
            raise ValueError("Credentialed CORS requires explicit origins")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
