from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import auth, companies, employees, fx, invites, me, payroll, reports, rules
from .config import settings

app = FastAPI(title="AutoTax", version="0.1.0", description="Nepal payroll & salary TDS")
app.add_middleware(
    CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)
# reports before employees so /employees/{id}/annual/{fy} isn't shadowed
for r in (auth, invites, companies, me, reports, employees, payroll, fx, rules):
    app.include_router(r.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"ok": True}
