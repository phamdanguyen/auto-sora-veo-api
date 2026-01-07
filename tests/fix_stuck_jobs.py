import sys
import os
import logging
from sqlalchemy import create_engine, text

# Add project root to path
sys.path.append(os.getcwd())

from app import models, database

def fix_stuck_jobs():
    print("--- Fixing Stuck Jobs ---")
    db = database.SessionLocal()
    
    # 1. Force Fail Loop Jobs (Retry > Max)
    # Note: Handle None max_retries by treating as default 3
    loop_jobs = db.query(models.Job).filter(models.Job.retry_count >= 3).filter(models.Job.status != 'failed').all()
    
    for job in loop_jobs:
        # Double check max_retries
        max_r = job.max_retries if job.max_retries is not None else 3
        if job.retry_count > max_r:
            print(f"🛑 Kill Job #{job.id} (Retry {job.retry_count}/{max_r}): Force FAILED to stop infinite loop.")
            job.status = "failed"
            job.error_message = f"Force Failed by System: Exceeded max retries ({job.retry_count}/{max_r})"
    
    db.commit()

    # 2. Reset Hung Processing Jobs
    # If a job is 'processing' but retry count is low, it might be stuck from a crash.
    # We reset it to pending.
    hung_jobs = db.query(models.Job).filter(models.Job.status == "processing").all()
    for job in hung_jobs:
         print(f"🔄 Reset Job #{job.id} (Processing -> Pending) to resume.")
         job.status = "pending"
         
    db.commit()
    db.close()
    print("--- Fix Complete ---")

if __name__ == "__main__":
    fix_stuck_jobs()
