"""
config.py — Configurazione centralizzata con Pydantic Settings.
Legge variabili da .env o dall'ambiente.
"""

from __future__ import annotations
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Config(BaseSettings):
    # ── LLM ─────────────────────────────────────────────────────────────────
    llm_base_url: str = Field("http://localhost:1234/v1", alias="LLM_BASE_URL")
    llm_api_key: str = Field("lm-studio", alias="LLM_API_KEY")
    llm_model: str = Field("", alias="LLM_MODEL")
    llm_max_tokens: int = Field(4096, alias="LLM_MAX_TOKENS")
    llm_retry: int = Field(3, alias="LLM_RETRY")
    llm_temperature: float = Field(0.1, alias="LLM_TEMPERATURE")
    llm_timeout: int = Field(120, alias="LLM_TIMEOUT")

    # ── Chunking ─────────────────────────────────────────────────────────────
    chunk_size: int = Field(6000, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(500, alias="CHUNK_OVERLAP")
    use_token_chunking: bool = Field(False, alias="USE_TOKEN_CHUNKING")

    # ── Processing ───────────────────────────────────────────────────────────
    parallel_workers: int = Field(1, alias="PARALLEL_WORKERS")
    enrich_batch_size: int = Field(30, alias="ENRICH_BATCH_SIZE")
    verify_sample_size: int = Field(0, alias="VERIFY_SAMPLE_SIZE")  # 0 = tutti
    fuzzy_merge_threshold: int = Field(90, alias="FUZZY_MERGE_THRESHOLD")

    # ── Output ───────────────────────────────────────────────────────────────
    output_dir: Path = Field(Path("."), alias="OUTPUT_DIR")

    @field_validator("chunk_overlap")
    @classmethod
    def overlap_lt_size(cls, v: int, info) -> int:
        # Non possiamo accedere agli altri campi agevolmente qui, 
        # la validazione viene fatta in cli.py
        return v

    model_config = {
        "env_file": ".env",
        "populate_by_name": True,
        "extra": "ignore",
    }


# Singleton caricato una volta sola
_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config


def set_config(cfg: Config) -> None:
    global _config
    _config = cfg
