"""
Concurrent Worker using Task Manager
Processes generate and download tasks with multiple concurrent workers
"""
import asyncio
from sqlalchemy.orm import Session
from .. import models, database
from . import account_manager
from .drivers.sora import SoraDriver
from .drivers.sora.exceptions import QuotaExhaustedException, VerificationRequiredException
from .task_manager import task_manager
from .download_utils import download_from_url
from .security import decrypt_password
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# Concurrency limits
MAX_CONCURRENT_GENERATE = 3  # Max concurrent generate tasks
MAX_CONCURRENT_DOWNLOAD = 3  # Max concurrent download tasks (match third-party limit)

# Semaphores for concurrency control
generate_semaphore = asyncio.Semaphore(MAX_CONCURRENT_GENERATE)
download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOAD)


async def process_single_generate_task(task):
    """Process a single generation task"""
    db = database.SessionLocal()
    job = db.query(models.Job).filter(models.Job.id == task.job_id).first()

    if not job:
        logger.error(f"Job #{task.job_id} not found!")
        db.close()
        return

    account = None
    driver = None

    try:
        # Get account (with exclusion for retried accounts)
        exclude_ids = task.input_data.get("exclude_account_ids", [])
        account_id = task.input_data.get("account_id")

        if account_id and account_id not in exclude_ids:
            account = db.query(models.Account).filter(models.Account.id == account_id).first()
            if account and account.status != "live":
                account = None  # Account not available anymore

        if not account:
            account = account_manager.get_available_account(db, platform="sora", exclude_ids=exclude_ids)

        if not account:
            raise Exception("No available account for generation")

        # Mark account as busy
        account_manager.mark_account_busy(account.id)

        # Update job with account info
        job.account_id = account.id
        account.last_used = datetime.utcnow()
        db.commit()

        logger.info(f"📝 Processing generate task for job #{task.job_id} with account #{account.id} ({account.email})")

        # Setup Driver
        profile_path = os.path.abspath(f"data/profiles/acc_{account.id}")

        driver = SoraDriver(
            headless=False,
            proxy=account.proxy,
            user_data_dir=profile_path
        )

        try:
            await driver.login(
                email=account.email,
                password=decrypt_password(account.password),
                cookies=account.cookies
            )

            # Check credits explicitly logic removed (redundant)
            # Driver now checks credits internally before submission


            # Generate video (Async Submit)
            logger.info(f"🚀 Submitting video generation for job #{task.job_id}...")
            
            result = await driver.submit_video(
                prompt=task.input_data["prompt"]
            )
            
            if result["submitted"]:
                logger.info(f"✅ Job #{task.job_id} submitted! Credits: {result['credits_before']} → {result['credits_after']}")
                
                # Move to Poll Queue
                await task_manager.complete_submit(
                    job, 
                    account_id=account.id,
                    credits_before=result["credits_before"],
                    credits_after=result["credits_after"]
                )
                db.commit()
            else:
                raise Exception(f"Submission verification failed (credits did not decrease). Before: {result['credits_before']}, After: {result['credits_after']}")



            # Success - complete task
            if result and result.startswith("/downloads/"):
                filename = os.path.basename(result)
                file_path = f"data/downloads/{filename}"
                file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

                # Use the web path directly (no "local:" prefix)
                # result is already "/downloads/filename.mp4" which works as href
                await task_manager.complete_generate(
                    job,
                    video_url=result,  # Web-accessible path
                    metadata={"method": "concurrent_worker", "account_id": account.id}
                )



        except QuotaExhaustedException as e:
            # Handle quota exhaustion - mark account and retry with different account
            logger.warning(f"⚠️ Account #{account.id} quota exhausted for job #{job.id}")
            account_manager.mark_account_quota_exhausted(db, account)

            # Re-queue the job with this account excluded
            exclude_ids = task.input_data.get("exclude_account_ids", [])
            exclude_ids.append(account.id)

            # Check if there are other accounts available
            other_account = account_manager.get_available_account(db, platform="sora", exclude_ids=exclude_ids)

            if other_account:
                logger.info(f"🔄 Re-queuing job #{job.id} with different account...")
                from .task_manager import TaskContext
                new_task = TaskContext(
                    job_id=job.id,
                    task_type="generate",
                    input_data={
                        "prompt": job.prompt,
                        "duration": job.duration,
                        "account_id": None,  # Let it pick a new account
                        "exclude_account_ids": exclude_ids
                    },
                    retry_count=task.retry_count  # Don't increment retry count for quota switch
                )
                await task_manager.generate_queue.put(new_task)
            else:
                # No more accounts available
                await task_manager.fail_task(job, "generate", "All accounts have exhausted quota")
                db.commit()

        except VerificationRequiredException as e:
            # Handle verification checkpoint - mark account and retry
            logger.warning(f"⚠️ Account #{account.id} requires verification: {e}")
            account_manager.mark_account_verification_needed(db, account)

            # Re-queue the job with this account excluded
            exclude_ids = task.input_data.get("exclude_account_ids", [])
            exclude_ids.append(account.id)

            # Check if there are other accounts available
            other_account = account_manager.get_available_account(db, platform="sora", exclude_ids=exclude_ids)

            if other_account:
                logger.info(f"🔄 Re-queuing job #{job.id} with different account (due to verify)...")
                from .task_manager import TaskContext
                new_task = TaskContext(
                    job_id=job.id,
                    task_type="generate",
                    input_data={
                        "prompt": job.prompt,
                        "duration": job.duration,
                        "account_id": None,  # Let it pick a new account
                        "exclude_account_ids": exclude_ids
                    },
                    retry_count=task.retry_count
                )
                await task_manager.generate_queue.put(new_task)
            else:
                 await task_manager.fail_task(job, "generate", "All accounts failed verification or exhausted")
                 db.commit()

        finally:
            if driver:
                logger.info("Closing driver session...")
                await driver.stop()

    except Exception as e:
        logger.error(f"❌ Generate task failed for job #{job.id}: {e}")
        await task_manager.fail_task(job, "generate", str(e))
        db.commit()

    finally:
        # Always mark account as free
        if account:
            account_manager.mark_account_free(account.id)
        db.close()


async def process_generate_tasks():
    """Worker loop for generation tasks - spawns concurrent workers"""
    logger.info(f"🎬 Generate Worker started (max concurrent: {MAX_CONCURRENT_GENERATE})")

    while True:
        try:
            # Wait for a task
            task = await task_manager.generate_queue.get()

            # Acquire semaphore and process
            async def process_with_semaphore():
                async with generate_semaphore:
                    await process_single_generate_task(task)

            # Spawn task concurrently (don't wait for it)
            asyncio.create_task(process_with_semaphore())

        except Exception as e:
            logger.error(f"Generate worker error: {e}")
            await asyncio.sleep(1)


# ============================================================================
# POLL WORKER - Check video completion status
# ============================================================================

MAX_CONCURRENT_POLL = 5  # Can poll many videos concurrently
poll_semaphore = asyncio.Semaphore(MAX_CONCURRENT_POLL)

async def process_single_poll_task(task):
    """Poll for video completion and move to download when ready"""
    db = database.SessionLocal()
    job = db.query(models.Job).filter(models.Job.id == task.job_id).first()
    
    if not job:
        logger.error(f"Job #{task.job_id} not found!")
        db.close()
        return
    
    account_id = task.input_data.get("account_id")
    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    
    if not account:
        logger.error(f"Account #{account_id} not found for poll task!")
        db.close()
        return
    
    driver = None
    
    try:
        logger.info(f"🔍 Polling job #{job.id} video status...")
        
        # Setup driver to check status
        profile_path = os.path.abspath(f"data/profiles/acc_{account.id}")
        driver = SoraDriver(
            headless=False,
            proxy=account.proxy,
            user_data_dir=profile_path
        )
        
        await driver.login(
            email=account.email,
            password=decrypt_password(account.password),
            cookies=account.cookies
        )
        
        # Check video status
        status = await driver.check_video_status()
        
        if status == "completed":
            logger.info(f"✅ Job #{job.id} video completed! Getting public link...")
            
            # Get public link
            public_link = await driver.get_video_public_link()
            
            # Download immediately
            from .third_party_downloader import ThirdPartyDownloader
            downloader = ThirdPartyDownloader()
            local_path, file_size = await downloader.download_from_public_link(
                driver.page,
                public_link
            )
            
            # Move to download complete
            await task_manager.complete_poll(job, f"/downloads/{os.path.basename(local_path)}")
            job.local_path = f"/downloads/{os.path.basename(local_path)}"
            db.commit()
            
            logger.info(f"✅ Job #{job.id} downloaded: {local_path}")
        else:
            # Still generating - re-queue with delay
            logger.info(f"⏳ Job #{job.id} still generating. Will poll again in 30s...")
            await asyncio.sleep(30)
            
            # Re-add to poll queue
            from .task_manager import TaskContext
            await task_manager.poll_queue.put(TaskContext(
                job_id=job.id,
                task_type="poll",
                input_data=task.input_data,
                retry_count=task.retry_count
            ))
            
    except Exception as e:
        logger.error(f"❌ Poll task failed for job #{job.id}: {e}")
        await task_manager.fail_task(job, "poll", str(e))
        db.commit()
        
    finally:
        if driver:
            await driver.stop()
        db.close()


async def process_poll_tasks():
    """Worker loop for polling video completion"""
    logger.info(f"🔍 Poll Worker started (max concurrent: {MAX_CONCURRENT_POLL})")
    
    while True:
        try:
            # logger.debug("Poll worker waiting for task...")
            task = await task_manager.poll_queue.get()
            logger.info(f"📬 Poll worker received task for job #{task.job_id}")
            
            async def process_with_semaphore():
                async with poll_semaphore:
                    await process_single_poll_task(task)
            
            asyncio.create_task(process_with_semaphore())
            
        except Exception as e:
            logger.error(f"Poll worker error: {e}")
            await asyncio.sleep(1)


async def process_single_download_task(task):
    """Process a single download task"""
    db = database.SessionLocal()
    job = db.query(models.Job).filter(models.Job.id == task.job_id).first()

    if not job:
        logger.error(f"Job #{task.job_id} not found!")
        db.close()
        return

    try:
        video_url = task.input_data["video_url"]
        logger.info(f"📥 Processing download task for job #{task.job_id}")

        # Check if already downloaded (local path starts with /downloads/)
        if video_url.startswith("/downloads/"):
            # Already downloaded - just verify and complete
            file_path = f"data{video_url}"  # data/downloads/filename.mp4
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
            await task_manager.complete_download(job, video_url, file_size)
        else:
            # Remote URL - need to download
            logger.info("Starting ad-hoc driver for download...")
            driver = SoraDriver(headless=True)
            try:
                await driver.start()
                local_path, file_size = await download_from_url(
                    driver.page,
                    video_url
                )
                await task_manager.complete_download(job, local_path, file_size)
            finally:
                await driver.stop()

        db.commit()
        logger.info(f"✅ Download complete for job #{job.id}")

    except Exception as e:
        logger.error(f"❌ Download task failed for job #{job.id}: {e}")
        await task_manager.fail_task(job, "download", str(e))
        db.commit()
    finally:
        db.close()


async def process_download_tasks():
    """Worker loop for download tasks - spawns concurrent workers"""
    logger.info(f"📥 Download Worker started (max concurrent: {MAX_CONCURRENT_DOWNLOAD})")

    while True:
        try:
            # Wait for a task
            task = await task_manager.download_queue.get()

            # Acquire semaphore and process
            async def process_with_semaphore():
                async with download_semaphore:
                    await process_single_download_task(task)

            # Spawn task concurrently (don't wait for it)
            asyncio.create_task(process_with_semaphore())

        except Exception as e:
            logger.error(f"Download worker error: {e}")
            await asyncio.sleep(1)

async def reset_stale_jobs():
    """Periodically reset jobs stuck in processing state"""
    logger.info("🔄 Stale job monitor started")

    while True:
        try:
            await asyncio.sleep(60)  # Check every 1 minute (more frequent for debug)
            
            # Log Queue Stats
            q_gen = task_manager.generate_queue.qsize() if task_manager._generate_queue else 0
            q_poll = task_manager.poll_queue.qsize() if task_manager._poll_queue else 0
            q_dl = task_manager.download_queue.qsize() if task_manager._download_queue else 0
            logger.info(f"📊 Queue Stats: Generate={q_gen}, Poll={q_poll}, Download={q_dl}")

            db = database.SessionLocal()
            try:
                # Reset quota exhausted accounts after 24 hours
                account_manager.reset_quota_exhausted_accounts(db, hours=24)

                # Find jobs stuck in processing for more than 15 minutes
                from datetime import timedelta
                cutoff = datetime.utcnow() - timedelta(minutes=15)

                stale_jobs = db.query(models.Job).filter(
                    models.Job.status == "processing",
                    models.Job.updated_at < cutoff
                ).all()

                for job in stale_jobs:
                    logger.warning(f"🔄 Resetting stale job #{job.id}")
                    job.status = "pending"
                    job.error_message = "Reset: Job was stuck in processing"

                if stale_jobs:
                    db.commit()
                    logger.info(f"Reset {len(stale_jobs)} stale jobs")

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Stale job monitor error: {e}")


async def start_task_manager_worker():
    """
    New task manager based worker
    Runs generate, poll, and download workers concurrently
    """
    logger.info("🚀 Task Manager Worker started!")
    logger.info(f"   - Max concurrent generate: {MAX_CONCURRENT_GENERATE}")
    logger.info(f"   - Max concurrent poll: {MAX_CONCURRENT_POLL}")
    logger.info(f"   - Max concurrent download: {MAX_CONCURRENT_DOWNLOAD}")

    # Start all workers
    await asyncio.gather(
        process_generate_tasks(),
        process_poll_tasks(),  # NEW: Poll worker for async status checking
        process_download_tasks(),
        reset_stale_jobs()
    )



# Keep old worker for backward compatibility
async def start_worker():
    """Start the new task manager worker"""
    await start_task_manager_worker()
