from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.api import auth, users, employees, system_logs, payrolls, archives
from app.core.config import settings
from app.core.limiter import limiter

app = FastAPI(
    title="Payroll Management System",
    description="Payroll system with JWT authentication",
    version="1.0.0"
)

# Attach rate limiter to app state
app.state.limiter = limiter

# Register 429 Too Many Requests error handler
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Rate limiting middleware (must come before CORS in the stack)
app.add_middleware(SlowAPIMiddleware)

# CORS Configuration
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

# Include Routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(employees.router)
app.include_router(system_logs.router)
app.include_router(payrolls.router)
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