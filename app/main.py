from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, employees, users, system_logs  # Add system_logs

app = FastAPI(
    title="Sakay Payroll System",
    description="Secure Payroll Management API with JWT Authentication",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://192.168.0.110:3000",
        "http://192.168.0.110:5173",
        "http://192.168.0.30:3000",
        "http://192.168.0.30:5173",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["*"]
)

# Include routers
app.include_router(auth.router)
app.include_router(employees.router)
app.include_router(users.router)
app.include_router(system_logs.router)  # Add this line


@app.get("/")
def read_root():
    return {
        "message": "Sakay Payroll API",
        "version": "1.0.0",
        "status": "running"
    }