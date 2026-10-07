from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import auth, companies, employees, fx, payroll, rules
from .config import settings

app = FastAPI(title="AutoTax", version="0.1.0", description="Nepal payroll & salary TDS")
app.add_middleware(
    CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)
for r in (auth, companies, employees, payroll, fx, rules):
    app.include_router(r.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}
