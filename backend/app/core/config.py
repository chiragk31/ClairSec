from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Adversarial Security Platform"
    version: str = "0.1.0"

    # MongoDB — override with MONGODB_URL / MONGODB_DB environment variables.
    # Never hard-code credentials here; use a .env file or host environment.
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db: str = "clairsec"

    # -------------------------------------------------------------------------
    # Phase 3: Isolation / Docker settings
    # Override any of these via environment variables or .env file.
    # -------------------------------------------------------------------------

    # Root directory where scan workspaces are created.
    # Kept outside the repo so user project data is never committed.
    workspace_root: str = "~/.clairsec/workspaces"

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
    # Phase 4: LLM provider settings
    # Assumption: Google Gemini is wired as the first concrete provider because it
    # is the most accessible for this development environment. The provider interface
    # allows any other provider (OpenAI, Anthropic, local Ollama) to be swapped in
    # by changing llm_provider + the relevant api_key setting.
    # -------------------------------------------------------------------------

    # Provider name: "gemini" | "openai" | "anthropic" | "mock"
    # "mock" disables all real LLM calls — used in tests.
    llm_provider: str = "gemini"

    # Model identifier passed to the active provider.
    llm_model: str = "gemini-2.0-flash"

    # API keys — never hard-coded; always from environment / .env file.
    # Only the key matching the active llm_provider is required at runtime.
    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # LLM call settings
    llm_max_retries: int = 3          # bounded retries on malformed/failed responses
    llm_request_timeout: int = 60     # seconds per LLM call

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
