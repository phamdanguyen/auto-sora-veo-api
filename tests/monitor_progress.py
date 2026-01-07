import sys
import os
import time
from app import models, database

sys.path.append(os.getcwd())

def monitor_jobs():
    print("Monitoring Job Status (Ctrl+C to stop)...")
    last_status = {}
    
    try:
        for _ in range(5): # Check 5 times
            db = database.SessionLocal()
            jobs = db.query(models.Job).filter(models.Job.status.in_(["pending", "processing"])).all()
            
            print(f"\n--- Time: {time.strftime('%H:%M:%S')} ---")
            if not jobs:
                print("No active jobs.")
            
            for job in jobs:
                print(f"Job #{job.id} | Status: {job.status} | Retry: {job.retry_count}/{job.max_retries}")
            
            db.close()
            time.sleep(3)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    monitor_jobs()
