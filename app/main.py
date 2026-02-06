from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, employees

app = FastAPI(
    title="Sakay Payroll System",
    description="Secure Payroll Management API with JWT Authentication",
    version="1.0.0"
)

# CORS configuration - Updated to allow Frontend PC
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://192.168.0.110:3000",      # Frontend PC (Next.js) ✅
        "http://192.168.0.110:5173",      # Frontend PC (Vite) ✅
        "http://localhost:3000",           # Local testing
        "http://localhost:5173",           # Local testing
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["*"]
)

# Include routers
app.include_router(auth.router)
app.include_router(employees.router)


@app.get("/")
def read_root():
    return {
        "message": "Sakay Payroll API",
        "version": "1.0.0",
        "status": "running"
    }