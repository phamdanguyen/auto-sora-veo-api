from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import logging
import sys

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Uni-Video Automation")

# Mount static files (Frontend Assets)
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")

# Mount downloads (User Data)
import os
ABS_DOWNLOAD_DIR = os.path.abspath("data/downloads")
os.makedirs(ABS_DOWNLOAD_DIR, exist_ok=True)
app.mount("/downloads", StaticFiles(directory=ABS_DOWNLOAD_DIR), name="downloads")

# CORS (allow all for local dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import FileResponse
import asyncio
from .core import worker_v2 as worker  # Use Refactored Worker (v2)

@app.on_event("startup")
async def on_startup():
    from .database import engine, Base, migrate_if_needed
    
    # Auto-migrate DB schema
    migrate_if_needed()
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    # Start Background Worker (Task Manager version)
    asyncio.create_task(worker.start_worker())

# Include API Router
from .api import endpoints
app.include_router(endpoints.router, prefix="/api")

@app.get("/")
async def read_dashboard():
    return FileResponse("app/web/templates/index.html")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
