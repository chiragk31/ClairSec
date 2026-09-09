from fastapi import FastAPI

app = FastAPI(title="ClairSec Test App")


@app.get("/health")
def health():
    """Health check endpoint — required for Phase 3 health check polling."""
    return {"status": "ok"}


@app.get("/")
def root():
    return {"app": "ClairSec Test App"}
