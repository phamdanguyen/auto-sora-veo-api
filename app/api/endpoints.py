from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from .. import models, schemas, database

router = APIRouter()

# Dependency
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

from ..core.security import encrypt_password

# ... (Previous imports)

# --- Accounts ---
@router.post("/accounts/", response_model=schemas.Account)
def create_account(account: schemas.AccountCreate, db: Session = Depends(get_db)):
    db_account = models.Account(
        platform=account.platform,
        email=account.email,
        password=encrypt_password(account.password),
        proxy=account.proxy,
        status="live"
    )
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account

@router.get("/accounts/", response_model=List[schemas.Account])
def read_accounts(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    accounts = db.query(models.Account).offset(skip).limit(limit).all()
    return accounts

# --- Jobs ---
@router.post("/jobs/", response_model=schemas.Job)
def create_job(job: schemas.JobCreate, db: Session = Depends(get_db)):
    db_job = models.Job(
        prompt=job.prompt,
        image_path=job.image_path,
        duration=job.duration,
        aspect_ratio=job.aspect_ratio,
        status="draft" # Default to draft so user must verify/start manually
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job

@router.get("/jobs/", response_model=List[schemas.Job])
def read_jobs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    jobs = db.query(models.Job).order_by(models.Job.id.desc()).offset(skip).limit(limit).all()
    return jobs

@router.get("/jobs/{job_id}", response_model=schemas.Job)
def read_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.put("/jobs/{job_id}", response_model=schemas.Job)
def update_job(job_id: int, job_update: schemas.JobUpdate, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job_update.prompt is not None:
        job.prompt = job_update.prompt
    if job_update.duration is not None:
        job.duration = job_update.duration
    if job_update.aspect_ratio is not None:
        job.aspect_ratio = job_update.aspect_ratio
        
    db.commit()
    db.refresh(job)
    return job

@router.delete("/jobs/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if job:
        db.delete(job)
        db.commit()
    return {"ok": True}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if job:
        # Only allow cancelling if not already completed/failed (optional, but good practice)
        # But user might want to force cancel if stuck. 
        # So we allow cancelling 'processing' or 'pending'.
        if job.status in ["pending", "processing"]:
            job.status = "cancelled"
            job.error_message = "Cancelled by user"
            db.commit()
    return {"ok": True}

# --- Bulk Actions ---
class BulkActionRequest(BaseModel):
    action: str # retry_failed, delete_all, clear_completed
    job_ids: Optional[List[int]] = None # Optional list of specific IDs

# --- Imports ---
from ..core.task_manager import task_manager

# ... (Previous code)

@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if job:
        # Reset job
        job.status = "pending"
        job.error_message = None
        job.retry_count = 0
        db.commit()
        
        # Trigger Task
        await task_manager.start_job(job)
        db.commit() # Save task_state updated by start_job
        
    return {"ok": True}

# ...

@router.post("/jobs/bulk_action")
async def bulk_job_action(req: BulkActionRequest, db: Session = Depends(get_db)):
    # Note: Bulk actions with task_manager need to iterate to trigger tasks
    # Simple query.update() puts DB in state but doesn't trigger Queue.
    
    if req.action == "start_selected" and req.job_ids:
        jobs = db.query(models.Job).filter(models.Job.id.in_(req.job_ids)).all()
        for job in jobs:
            if job.status == "draft":
                 await task_manager.start_job(job)
        db.commit()

    elif req.action == "retry_selected" and req.job_ids:
        jobs = db.query(models.Job).filter(models.Job.id.in_(req.job_ids)).all()
        for job in jobs:
             # Retry (Clean slate)
            job.status = "pending"
            job.error_message = None
            job.retry_count = 0
            await task_manager.start_job(job)
        db.commit()

    elif req.action == "retry_download_selected" and req.job_ids:
        # Retry only subtasks (Poll/Download) for Submitted/Completed jobs
        jobs = db.query(models.Job).filter(models.Job.id.in_(req.job_ids)).all()
        for job in jobs:
            await task_manager.retry_subtasks(job)
        db.commit()

        
    elif req.action == "retry_failed":
        jobs = db.query(models.Job).filter(models.Job.status == "failed").all()
        for job in jobs:
             job.status = "pending"
             job.error_message = None
             job.retry_count = 0
             await task_manager.start_job(job)
        db.commit()

    elif req.action == "delete_all":
        db.query(models.Job).delete(synchronize_session=False)
        db.commit()
    elif req.action == "clear_completed":
         db.query(models.Job).filter(models.Job.status == "completed").delete(synchronize_session=False)
         db.commit()
    elif req.action == "delete_selected" and req.job_ids:
        db.query(models.Job).filter(models.Job.id.in_(req.job_ids)).delete(synchronize_session=False)
        db.commit()
    
    return {"ok": True}
