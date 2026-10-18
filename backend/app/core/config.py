from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Adversarial Security Platform"
    version: str = "0.1.0"

    # Root directory for trusted fixtures. Computed by default from the package location.
    trusted_fixtures_root: Path = (
        Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"
    ).resolve()

    # MongoDB — override with MONGODB_URL / MONGODB_DB environment variables.
    # Never hard-code credentials here; use a .env file or host environment.
    # No silent defaults per OPERATIONS §3 and Step 1.
    mongodb_url: str = ""
    mongodb_db: str = "clairsec"

    # Root directory where scan workspaces are created.
    # Kept outside the repo so user project data is never committed.
    # No silent default per OPERATIONS §3 and Step 1.
    workspace_root: str = ""

    # LLM Provider configuration per LLM.md §1
    # Default is "mock" so that the platform boots and tests without network or credentials.
    llm_provider: str = "mock"  # "mock" | "anthropic" | "ollama"
    llm_model_id: str = "claude-opus-5"  # Exact pinned model identifier per LLM.md §1
    llm_cache_mode: str = "read_write"  # "off" | "read_write" | "replay"

    # LLM API key — required only when llm_provider != "mock".
    llm_api_key: str = ""

    # Ollama URL and model for local AI execution per FEATURES.md F4
    # Database fallback: when MongoDB is unreachable at startup, run on an in-memory
    # database so Demo mode works with nothing else installed (Round 3 audit D3).
    memory_storage_fallback: bool = True
    mongodb_connect_timeout_ms: int = 3000

    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2"

    # Docker resource limits for the target container.
    # Assumption: 256 MB RAM and 0.5 CPU are reasonable defaults for a lightweight
    # FastAPI app in a security-testing context. Users running large apps can override.
    docker_mem_limit: str = "256m"
    docker_nano_cpus: int = 500_000_000  # 0.5 CPU expressed as nanocpus

    # Build timeout (seconds). A hung pip install must not block the platform,
    # but this also has to accommodate real projects: the benchmark fixture has
    # 5 dependencies and builds in ~30s, while a typical application with 100+
    # pinned packages needs several minutes to download and install on a cold
    # cache. 120s was too aggressive and failed legitimate projects.
    docker_build_timeout: int = 600

    # Startup timeout (seconds). Time allowed for the container to pass health
    # check. Applications that build indexes or warm caches on boot need more
    # than the original 30s.
    docker_startup_timeout: int = 90

    # Maximum bytes captured from container stdout/stderr per retrieval.
    # 100 KB is enough for debugging without risking unbounded log accumulation.
    docker_log_max_bytes: int = 102_400

    # -------------------------------------------------------------------------
    # Phase V3: Git & GitHub import settings (FEATURES.md F2, THREAT_MODEL C2)
    # -------------------------------------------------------------------------
    git_allowed_hosts: list[str] = ["github.com"]
    git_clone_timeout: int = 180
    git_max_repo_mb: int = 200
    git_max_files: int = 20_000
    git_min_version: str = "2.45.1"

    # Name of the isolated Docker bridge network for target containers.
    docker_network_name: str = "clairsec-net"

    # Port the target container is expected to listen on internally.
    docker_target_port: int = 8000

    # -------------------------------------------------------------------------
    # Phase 3.5: Container hardening (THREAT_MODEL C3.1, C3.2, C3.4)
    # These are config flags so their impact on import success can be measured
    # before committing (correction #3 — research metric sensitivity).
    # -------------------------------------------------------------------------
    docker_pids_limit: int = 256
    docker_read_only: bool = True
    docker_non_root: bool = True
    docker_sqlite_data_dir: str = "/tmp/clairsec-data"
    # Base image pinned by SHA-256 digest for reproducibility and security.
    # To re-resolve or update this pin, run:
    #   docker pull python:3.11-slim
    #   docker inspect --format='{{index .RepoDigests 0}}' python:3.11-slim
    docker_base_image: str = "python:3.11-slim@sha256:9534e5a8e315485d4061ed659af0fd78a284c015f9b73661b41d6bab25604534"

    # -------------------------------------------------------------------------
    # Phase 3.5: API authentication (THREAT_MODEL C7.1–C7.4)
    # -------------------------------------------------------------------------

    # Where to write the per-launch bearer token for the Flutter client.
    auth_token_path: str = "~/.clairsec/auth_token"

    # Bind address — 127.0.0.1 only per C7.1. Never 0.0.0.0.
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Host header validation allowlist (C7.3).
    # Flutter desktop doesn't send Origin headers, so CORS is deny-all.
    # 'testserver' is included so FastAPI TestClient works in tests.
    allowed_hosts: list[str] = [
        "127.0.0.1",
        "localhost",
        "testserver",
    ]

    # Testing mode — set by test fixtures, never in production.
    # Allows test-specific overrides without weakening production config.
    testing: bool = False

    def check_required_settings(self) -> None:
        """
        Validate that required settings are configured (OPERATIONS §3).
        Fails loudly on any missing required setting:
        - MONGODB_URL
        - WORKSPACE_ROOT
        - LLM_API_KEY
        """
        if self.testing:
            return
        missing: list[str] = []
        if not self.mongodb_url or not self.mongodb_url.strip():
            missing.append("MONGODB_URL")
        if not self.workspace_root or not self.workspace_root.strip():
            missing.append("WORKSPACE_ROOT")
        if self.llm_provider not in ("mock", "replay", "ollama"):
            if not self.llm_api_key or not self.llm_api_key.strip():
                missing.append("LLM_API_KEY")
        if missing:
            raise RuntimeError(
                f"Startup failed: missing required setting(s): {', '.join(missing)}. "
                "See .env.example for required configuration."
            )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
