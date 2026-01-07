import sys
import os
import logging
from sqlalchemy import create_engine, text

# Add project root to path
sys.path.append(os.getcwd())

from app import models, database

def check_status():
    print("--- Current Job/Account Status ---")
    db = database.SessionLocal()
    
    # 1. Active Jobs
    print("\n[Jobs - Processing/Pending]")
    active_jobs = db.query(models.Job).filter(models.Job.status.in_(["processing", "pending"])).all()
    if not active_jobs:
        print("No active jobs.")
    for job in active_jobs:
        print(f"Job #{job.id} | Status: {job.status} | Retry: {job.retry_count}/{job.max_retries} (Raw Max: {job.max_retries}) | Account ID: {job.account_id}")
        if job.error_message:
            print(f"   Last Error: {job.error_message}")
            
    # 2. Failed Jobs (Last 5)
    print("\n[Jobs - Failed (Last 5)]")
    failed_jobs = db.query(models.Job).filter(models.Job.status == "failed").order_by(models.Job.id.desc()).limit(5).all()
    for job in failed_jobs:
        print(f"Job #{job.id} | Status: {job.status} | Retry: {job.retry_count} | Error: {job.error_message[:100]}...")

    # 3. Accounts
    print("\n[Accounts - All]")
    accounts = db.query(models.Account).all()
    for acc in accounts:
        print(f"Account {acc.id}: {acc.email} | Status: {acc.status}")

    db.close()
    print("\n------------------------------")

if __name__ == "__main__":
    check_status()
