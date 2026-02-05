from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, employees  # Add employees here

app = FastAPI(
    title="Sakay Payroll System",
    description="Secure Payroll Management API with JWT Authentication",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
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
app.include_router(employees.router)  # Add this line


@app.get("/")
def read_root():
    return {
        "message": "Sakay Payroll API",
        "version": "1.0.0",
        "status": "running"
    }