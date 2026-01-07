import sys
import os
import logging

# Add project root to path
sys.path.append(os.getcwd())

from app import models, database
from app.core.worker import reset_stale_jobs

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_reset_logic():
    print("--- Starting Stale Job Reset Test ---")
    db = database.SessionLocal()
    
    # 1. Create a Fake Stale Job
    fake_job = models.Job(
        prompt="Test Stale Reset",
        status="processing", # Simulate stuck job
        retry_count=0
    )
    db.add(fake_job)
    db.commit()
    db.refresh(fake_job)
    
    job_id = fake_job.id
    print(f"[Setup] Created fake stale job ID {job_id} with status '{fake_job.status}'")
    
    # 2. Run the Reset Function
    print("[Action] Running reset_stale_jobs()...")
    reset_stale_jobs()
    
    # 3. Verify Result
    db.refresh(fake_job)
    print(f"[Verification] Job ID {job_id} status is now '{fake_job.status}'")
    print(f"[Verification] Job ID {job_id} retry_count is now {fake_job.retry_count}")
    
    if fake_job.status == "pending" and fake_job.retry_count == 1:
        print("✅ TEST PASSED: Job was successfully reset to pending.")
    else:
        print("❌ TEST FAILED: Job status or retry count incorrect.")
        
    # Cleanup
    db.delete(fake_job)
    db.commit()
    db.close()
    print("--- Test Completed ---")

if __name__ == "__main__":
    test_reset_logic()
