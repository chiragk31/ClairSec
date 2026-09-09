from fastapi import FastAPI

app = FastAPI(title="Test App")


@app.get("/health")
def health():
    return {"status": "ok"}
