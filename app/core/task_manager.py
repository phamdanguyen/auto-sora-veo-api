"""
Simple Task Manager - Zero-config task orchestration
Uses in-memory queues for task management
"""
import asyncio
from dataclasses import dataclass
from typing import Dict, Optional
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class TaskContext:
    """Lightweight task context - no DB needed!"""
    job_id: int
    task_type: str  # "generate" | "download" | "verify"
    input_data: dict
    retry_count: int = 0

class SimpleTaskManager:
    """
    Zero-config Task Manager using in-memory queues

    Tasks flow: GENERATE → DOWNLOAD → VERIFY (optional)
    Each task is processed by dedicated worker loops
    """

    def __init__(self):
        # Lazy initialization - queues created when first accessed
        self._generate_queue = None
        self._poll_queue = None  # NEW: For polling video completion
        self._download_queue = None
        self._verify_queue = None
        self._initialized = False

    def _ensure_initialized(self):
        """Initialize queues in the current event loop"""
        if not self._initialized:
            self._generate_queue = asyncio.Queue()
            self._poll_queue = asyncio.Queue()  # NEW
            self._download_queue = asyncio.Queue()
            self._verify_queue = asyncio.Queue()
            self._initialized = True
            logger.info("✅ SimpleTaskManager queues initialized (with poll_queue)")


    @property
    def generate_queue(self):
        self._ensure_initialized()
        return self._generate_queue

    @property
    def download_queue(self):
        self._ensure_initialized()
        return self._download_queue

    @property
    def poll_queue(self):
        """Queue for polling video completion status"""
        self._ensure_initialized()
        return self._poll_queue

    @property
    def verify_queue(self):
        self._ensure_initialized()
        return self._verify_queue

    
    async def start_job(self, job):
        """
        Bắt đầu job - initialize task state và add generate task vào queue
        
        Args:
            job: Job model instance
        """
        # Initialize task state in job
        task_state = {
            "tasks": {
                "generate": {"status": "pending"},
                "download": {"status": "blocked"},
                "verify": {"status": "blocked"}
            },
            "current_task": "generate"
        }
        
        job.task_state = json.dumps(task_state)
        job.status = "processing"
        
        # Add to generate queue
        task = TaskContext(
            job_id=job.id,
            task_type="generate",
            input_data={
                "prompt": job.prompt,
                "duration": job.duration,
                "account_id": job.account_id
            }
        )
        
        await self.generate_queue.put(task)
        logger.info(f"✅ Job #{job.id} added to generate queue")
    
    async def complete_submit(self, job, account_id: int, credits_before: int, credits_after: int):
        """
        Submit phase complete → move to poll queue
        
        Args:
            job: Job model instance
            account_id: Account used for generation
            credits_before: Credits before submission
            credits_after: Credits after submission
        """
        state = json.loads(job.task_state) if job.task_state else self._default_state()
        
        # Update state to reflect submission
        state["tasks"]["generate"] = {
            "status": "completed",  # Mark as completed (Submission done)
            "completed_at": datetime.now().isoformat(),
            "submitted_at": datetime.now().isoformat(),
            "account_id": account_id,
            "credits_before": credits_before,
            "credits_after": credits_after
        }
        state["tasks"]["poll"] = {"status": "pending"}
        state["current_task"] = "poll"
        
        job.task_state = json.dumps(state)
        
        # Add to poll queue
        task = TaskContext(
            job_id=job.id,
            task_type="poll",
            input_data={
                "account_id": account_id,
                "submitted_at": datetime.now().isoformat()
            }
        )
        
        await self.poll_queue.put(task)
        logger.info(f"✅ Job #{job.id} submitted, moved to poll queue")
    
    async def complete_poll(self, job, video_url: str):
        """
        Poll phase complete (video ready) → move to download queue
        
        Args:
            job: Job model instance
            video_url: Public video URL
        """
        state = json.loads(job.task_state) if job.task_state else self._default_state()
        
        state["tasks"]["generate"]["status"] = "completed"
        state["tasks"]["generate"]["completed_at"] = datetime.now().isoformat()
        state["tasks"]["poll"] = {"status": "completed"}
        state["tasks"]["download"] = {
            "status": "pending",
            "input": {"video_url": video_url}
        }
        state["current_task"] = "download"
        
        job.task_state = json.dumps(state)
        job.video_url = video_url
        
        # Add to download queue
        task = TaskContext(
            job_id=job.id,
            task_type="download",
            input_data={"video_url": video_url}
        )
        
        await self.download_queue.put(task)
        logger.info(f"✅ Job #{job.id} video ready, moved to download queue")
    
    async def complete_generate(self, job, video_url: str, metadata: dict):
        """
        Generate complete → unlock download task
        
        Args:
            job: Job model instance
            video_url: Captured video URL from generation
            metadata: Additional metadata (size, etc.)
        """
        state = json.loads(job.task_state) if job.task_state else self._default_state()
        
        # Update generate task
        state["tasks"]["generate"] = {
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "output": {"video_url": video_url, "metadata": metadata}
        }
        
        # Unlock download
        state["tasks"]["download"] = {
            "status": "pending",
            "input": {"video_url": video_url}
        }
        state["current_task"] = "download"
        
        job.task_state = json.dumps(state)
        job.video_url = video_url  # Save URL for reference
        
        # Add to download queue
        task = TaskContext(
            job_id=job.id,
            task_type="download",
            input_data={"video_url": video_url}
        )
        
        await self.download_queue.put(task)
        logger.info(f"✅ Job #{job.id} moved to download queue (video: {video_url[:60]}...)")
    
    async def complete_download(self, job, local_path: str, file_size: int):
        """
        Download complete → complete job (skip verify for now)
        
        Args:
            job: Job model instance
            local_path: Path to downloaded video
            file_size: Size of downloaded file
        """
        state = json.loads(job.task_state) if job.task_state else self._default_state()
        
        state["tasks"]["download"] = {
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "output": {"local_path": local_path, "file_size": file_size}
        }
        
        # For now, skip verify - just complete job
        state["current_task"] = "completed"
        job.status = "completed"
        job.local_path = local_path
        job.task_state = json.dumps(state)
        
        logger.info(f"✅ Job #{job.id} completed! Video at {local_path} ({file_size:,} bytes)")
    
    async def fail_task(self, job, task_type: str, error: str):
        """
        Handle task failure với retry logic
        
        Args:
            job: Job model instance
            task_type: Type of task that failed
            error: Error message
        """
        state = json.loads(job.task_state) if job.task_state else self._default_state()
        task_state = state["tasks"].get(task_type, {})
        
        retry_count = task_state.get("retry_count", 0) + 1
        max_retries = 3
        
        if retry_count < max_retries:
            # Retry - update state and re-queue
            task_state["retry_count"] = retry_count
            task_state["status"] = "pending"
            task_state["last_error"] = error
            state["tasks"][task_type] = task_state
            
            job.task_state = json.dumps(state)
            
            # Re-add to appropriate queue
            queue = getattr(self, f"{task_type}_queue")
            
            # Get input data from state or job
            if task_type == "generate":
                input_data = {
                    "prompt": job.prompt,
                    "duration": job.duration,
                    "account_id": job.account_id
                }
            elif task_type == "download":
                input_data = task_state.get("input", {"video_url": job.video_url})
            else:
                input_data = task_state.get("input", {})
            
            task = TaskContext(
                job_id=job.id,
                task_type=task_type,
                input_data=input_data,
                retry_count=retry_count
            )
            await queue.put(task)
            
            logger.warning(f"⚠️ Job #{job.id} {task_type} failed, retry {retry_count}/{max_retries}: {error}")
        else:
            # Max retries reached - fail job
            task_state["status"] = "failed"
            task_state["error"] = error
            state["tasks"][task_type] = task_state
            
            job.status = "failed"
            job.error_message = f"{task_type} failed after {max_retries} retries: {error}"
            job.task_state = json.dumps(state)
            
            logger.error(f"❌ Job #{job.id} failed permanently: {task_type} - {error}")
    
    def _default_state(self):
        """Default task state structure"""
        return {
            "tasks": {
                "generate": {"status": "pending"},
                "download": {"status": "blocked"},
                "verify": {"status": "blocked"}
            },
            "current_task": "generate"
        }
    
    async def get_job_state(self, job) -> dict:
        """Get parsed task state from job"""
        if job.task_state:
            return json.loads(job.task_state)
        return self._default_state()

    async def retry_subtasks(self, job):
        """
        Retry post-generation tasks (Poll or Download)
        Useful if a submitted job got stuck or download failed
        """
        # Await the coroutine
        state = await self.get_job_state(job)
        gen_status = state["tasks"]["generate"]["status"]
        
        if job.video_url:
            # Video URL exists -> Retry Download
            logger.info(f"🔄 Retrying Download for Job #{job.id}")
            state["tasks"]["download"]["status"] = "pending"
            state["current_task"] = "download"
            job.task_state = json.dumps(state)
            
            task = TaskContext(
                job_id=job.id,
                task_type="download",
                input_data={"video_url": job.video_url}
            )
            await self.download_queue.put(task)
            
        elif gen_status in ["submitted", "completed"]:
            # Generation done/submitted, but no URL -> Retry Poll
            logger.info(f"🔄 Retrying Poll for Job #{job.id}")
            state["tasks"]["poll"]["status"] = "pending"
            state["current_task"] = "poll"
            job.task_state = json.dumps(state)
            
            # Need account status from state
            acct_id = state["tasks"]["generate"].get("account_id")
            if not acct_id:
                # Try to get from job
                acct_id = job.account_id
                
            task = TaskContext(
                job_id=job.id,
                task_type="poll",
                input_data={
                    "account_id": acct_id,
                    "retry_count": 0
                }
            )
            await self.poll_queue.put(task)
        else:
            logger.warning(f"⚠️ Job #{job.id} not in a state to retry subtasks (Gen Status: {gen_status})")

# Global instance
task_manager = SimpleTaskManager()
