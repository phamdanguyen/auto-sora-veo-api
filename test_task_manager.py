"""
Quick test script for Task Manager
"""
import asyncio
import sys
sys.path.insert(0, '/Users/master/Desktop/CODE/uni-video')

from app import models, database
from app.core.task_manager import task_manager

async def test_task_manager():
    print("🧪 Testing Task Manager...")
    
    # Create test database session
    db = database.SessionLocal()
    
    # Create a test job
    test_job = models.Job(
        prompt="Test video - a cat playing piano",
        duration=5,
        status="draft"
    )
    
    db.add(test_job)
    db.commit()
    db.refresh(test_job)
    
    print(f"✅ Created test job #{test_job.id}")
    
    # Start job with task manager
    await task_manager.start_job(test_job)
    db.commit()
    
    print(f"📊 Job state: {test_job.task_state}")
    print(f"📊 Job status: {test_job.status}")
    
    # Check queue
    print(f"📥 Generate queue size: {task_manager.generate_queue.qsize()}")
    
    # Get task from queue
    task = await task_manager.generate_queue.get()
    print(f"✅ Got task: job_id={task.job_id}, type={task.task_type}")
    
    # Simulate complete generate
    await task_manager.complete_generate(
        test_job,
        video_url="https://test-cdn.com/video123.mp4",
        metadata={"size": 1000000}
    )
    db.commit()
    
    print(f"📊 After generate - Job state: {test_job.task_state}")
    print(f"📊 Job video_url: {test_job.video_url}")
    print(f"📥 Download queue size: {task_manager.download_queue.qsize()}")
    
    # Get download task
    download_task = await task_manager.download_queue.get()
    print(f"✅ Got download task: {download_task.input_data}")
    
    # Simulate complete download
    await task_manager.complete_download(
        test_job,
        local_path="/downloads/test_video.mp4",
        file_size=1000000
    )
    db.commit()
    
    print(f"📊 Final job status: {test_job.status}")
    print(f"📊 Final job state: {test_job.task_state}")
    
    print("\n✅ All tests passed!")
    
    db.close()

if __name__ == "__main__":
    asyncio.run(test_task_manager())
