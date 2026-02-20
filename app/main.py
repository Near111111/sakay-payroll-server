from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.api import auth, users, employees, system_logs, payrolls, archives
from app.core.config import settings
from app.api import auth, users, employees, system_logs, payrolls, archives, inventory
from app.core.limiter import limiter
import re

app = FastAPI(
    title="Payroll Management System",
    description="Payroll system with JWT authentication",
    version="1.0.0"
)

# ─────────────────────────────────────────────
# Rate Limiter
# ─────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ─────────────────────────────────────────────
# CORS
# ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://192.168.0.110:3000",
        "http://192.168.0.30:3000",
        "https://sakay-ph-frontend-payroll.vercel.app",
        "http://192.168.0.54:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# SQL Injection Protection
# (Ginawa bilang route handler, hindi middleware
#  para maiwasan ang conflict sa SlowAPI)
# ─────────────────────────────────────────────
SQL_INJECTION_PATTERNS = re.compile(
    r"(select|union|insert|update|delete|drop|cast|convert|declare|exec|execute|--|;|'|%27|%3B|%2D%2D)",
    re.IGNORECASE
)

@app.middleware("http")
async def block_sql_injection(request: Request, call_next):
    if SQL_INJECTION_PATTERNS.search(str(request.url.path)):
        return JSONResponse(
            status_code=400,
            content={"detail": "Bad request"}
        )
    # Must await and return properly to avoid RuntimeError
    response = await call_next(request)
    return response

# ─────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(employees.router)
app.include_router(system_logs.router)
app.include_router(payrolls.router)
app.include_router(inventory.router)
app.include_router(archives.router)


@app.get("/")
def read_root():
    return {
        "message": "Payroll Management System API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
def health():
    return {
        "status": "healthy",
    }