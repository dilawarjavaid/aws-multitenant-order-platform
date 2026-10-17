from fastapi import FastAPI

app = FastAPI(
    title="Multi-Tenant Order Platform",
    description="An order management API for multiple retailers.",
    version="0.1.0",
)


@app.get("/health", tags=["Operations"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}