from fastapi import FastAPI

app = FastAPI(title="Broken Test App")


@app.get("/health")
def health():
    return {"status": "ok"}
