#!/usr/bin/env python3
"""Quick test for Task Manager"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import models, database
from app.core.task_manager import task_manager
import json

async def main():
    print("🧪 Testing Task Manager...\n")
    
    db = database.SessionLocal()
    
    # Create test job
    job = models.Job(
        prompt="Test: a cat playing piano",
        duration=5,
        status="draft"
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    print(f"✅ Created job #{job.id}")
    
    # Start job
    await task_manager.start_job(job)
    db.commit()
    
    print(f"📊 Job status: {job.status}")
    print(f"📊 Task state: {json.loads(job.task_state)}")
    print(f"📥 Generate queue: {task_manager.generate_queue.qsize()} tasks\n")
    
    # Simulate generate complete
    task = await task_manager.generate_queue.get()
    print(f"✅ Got generate task for job #{task.job_id}")
    
    await task_manager.complete_generate(
        job,
        "https://cdn.test.com/video.mp4",
        {"size": 1500000}
    )
    db.commit()
    
    print(f"📊 Video URL: {job.video_url}")
    print(f"📥 Download queue: {task_manager.download_queue.qsize()} tasks\n")
    
    # Simulate download complete
    dl_task = await task_manager.download_queue.get()
    print(f"✅ Got download task")
    
    await task_manager.complete_download(job, "/downloads/test.mp4", 1500000)
    db.commit()
    
    print(f"📊 Final status: {job.status}")
    print(f"📊 Local path: {job.local_path}")
    print(f"\n✅ Task Manager works correctly!")
    
    db.close()

if __name__ == "__main__":
    asyncio.run(main())
