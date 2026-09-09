from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Adversarial Security Platform"
    version: str = "0.1.0"

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
    llm_provider: str = "mock"  # "mock" | "anthropic"
    llm_model_id: str = "claude-opus-5"  # Exact pinned model identifier per LLM.md §1
    llm_cache_mode: str = "read_write"  # "off" | "read_write" | "replay"

    # LLM API key — required only when llm_provider != "mock".
    llm_api_key: str = ""

    # Docker resource limits for the target container.
    # Assumption: 256 MB RAM and 0.5 CPU are reasonable defaults for a lightweight
    # FastAPI app in a security-testing context. Users running large apps can override.
    docker_mem_limit: str = "256m"
    docker_nano_cpus: int = 500_000_000  # 0.5 CPU expressed as nanocpus

    # Build timeout (seconds). A hung pip install must not block the platform.
    docker_build_timeout: int = 120

    # Startup timeout (seconds). Time allowed for the container to pass health check.
    docker_startup_timeout: int = 30

    # Maximum bytes captured from container stdout/stderr per retrieval.
    # 100 KB is enough for debugging without risking unbounded log accumulation.
    docker_log_max_bytes: int = 102_400

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
        if self.llm_provider != "mock":
            if not self.llm_api_key or not self.llm_api_key.strip():
                missing.append("LLM_API_KEY")
        if missing:
            raise RuntimeError(
                f"Startup failed: missing required setting(s): {', '.join(missing)}. "
                "See .env.example for required configuration."
            )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
