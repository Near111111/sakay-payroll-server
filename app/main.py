from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, users, employees, system_logs, payrolls  # ✅ Add payrolls
from app.core.config import settings
from app.api import auth, users, employees, system_logs, payrolls, archives

app = FastAPI(
    title="Payroll Management System",
    description="Payroll system with JWT authentication",
    version="1.0.0"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://192.168.0.110:3000",
        "http://192.168.0.30:3000",
        "https://sakay-ph-frontend-payroll.vercel.app"
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
app.include_router(archives.router)  # ✅ Add this


@app.get("/")
def read_root():
    return {
        "message": "Payroll Management System API",
        "version": "1.0.0",
        "docs": "/docs"
    }