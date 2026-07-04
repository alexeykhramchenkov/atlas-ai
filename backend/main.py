from fastapi import FastAPI

import core.logger  # noqa: F401
from backend.routes.shopify_auth import router as shopify_auth_router


app = FastAPI(title="Atlas AI Backend")

app.include_router(shopify_auth_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
