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
MAX_ACCOUNT_SWITCHES = 10  # Max account switches per job before failing


# Semaphores for concurrency control (lazy-initialized to avoid event loop issues)
_generate_semaphore = None
_download_semaphore = None

# Account Locks to prevent concurrent profile access
# Key: account_id, Value: asyncio.Lock
_account_locks = {}
_account_locks_mutex = asyncio.Lock()

async def get_account_lock(account_id: int) -> asyncio.Lock:
    """Get or create a lock for a specific account"""
    async with _account_locks_mutex:
        if account_id not in _account_locks:
            _account_locks[account_id] = asyncio.Lock()
        return _account_locks[account_id]

def _get_generate_semaphore():
    """Lazy-init generate semaphore to avoid event loop attachment issues"""
    global _generate_semaphore
    if _generate_semaphore is None:
        _generate_semaphore = asyncio.Semaphore(MAX_CONCURRENT_GENERATE)
    return _generate_semaphore

def _get_download_semaphore():
    """Lazy-init download semaphore to avoid event loop attachment issues"""
    global _download_semaphore
    if _download_semaphore is None:
        _download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOAD)
    return _download_semaphore


async def process_single_generate_task(task):
    """Process a single generation task"""
    db = database.SessionLocal()
    account = None
    driver = None

    try:
        job = db.query(models.Job).filter(models.Job.id == task.job_id).first()

        if not job:
            logger.error(f"Job #{task.job_id} not found!")
            return
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
        await account_manager.mark_account_busy(account.id)

        # Update job with account info
        try:
            job.account_id = account.id
            account.last_used = datetime.utcnow()
            db.commit()
        except Exception as commit_error:
            logger.error(f"Failed to update job/account in DB: {commit_error}")
            db.rollback()
            raise

        logger.info(f"📝 Processing generate task for job #{task.job_id} with account #{account.id} ({account.email})")

        # Acquire Lock for Profile Access
        account_lock = await get_account_lock(account.id)
        await account_lock.acquire()

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

                # UPDATE ACCOUNT CREDITS
                try:
                    if result.get("credits_after") is not None and result["credits_after"] != -1:
                        account.credits_remaining = result["credits_after"]
                        account.credits_last_checked = datetime.utcnow()
                        logger.info(f"💾 Updated Account #{account.id} credits to {account.credits_remaining}")
                    else:
                        logger.warning(f"⚠️ Credits unverified for Account #{account.id}. Submission may be risky.")

                    # Move to Poll Queue
                    await task_manager.complete_submit(
                        job,
                        account_id=account.id,
                        credits_before=result["credits_before"],
                        credits_after=result["credits_after"]
                    )
                    db.commit()
                except Exception as commit_error:
                    logger.error(f"Failed to update credits/task state: {commit_error}")
                    db.rollback()
                    raise
            else:
                raise Exception(f"Submission verification failed (credits did not decrease). Before: {result['credits_before']}, After: {result['credits_after']}")

        except QuotaExhaustedException as e:
            # Handle quota exhaustion - mark account and retry with different account
            logger.warning(f"⚠️ Account #{account.id} quota exhausted for job #{job.id}")
            account_manager.mark_account_quota_exhausted(db, account)

            # Track account switches to prevent infinite loop
            account_switch_count = task.input_data.get("account_switch_count", 0) + 1

            if account_switch_count >= MAX_ACCOUNT_SWITCHES:
                logger.error(f"❌ Job #{job.id} exceeded max account switches ({MAX_ACCOUNT_SWITCHES})")
                try:
                    await task_manager.fail_task(job, "generate", f"Failed after switching {MAX_ACCOUNT_SWITCHES} accounts (all quota exhausted)")
                    db.commit()
                except Exception as commit_error:
                    logger.error(f"Failed to commit task failure: {commit_error}")
                    db.rollback()
            else:
                # Re-queue the job with this account excluded
                exclude_ids = task.input_data.get("exclude_account_ids", [])
                exclude_ids.append(account.id)

                # Check if there are other accounts available
                other_account = account_manager.get_available_account(db, platform="sora", exclude_ids=exclude_ids)

                if other_account:
                    logger.info(f"🔄 Re-queuing job #{job.id} with different account (switch {account_switch_count}/{MAX_ACCOUNT_SWITCHES})...")
                    from .task_manager import TaskContext
                    new_task = TaskContext(
                        job_id=job.id,
                        task_type="generate",
                        input_data={
                            "prompt": job.prompt,
                            "duration": job.duration,
                            "account_id": None,  # Let it pick a new account
                            "exclude_account_ids": exclude_ids,
                            "account_switch_count": account_switch_count
                        },
                        retry_count=task.retry_count  # Don't increment retry count for quota switch
                    )
                    await task_manager.generate_queue.put(new_task)
                else:
                    # No more accounts available
                    try:
                        await task_manager.fail_task(job, "generate", "All accounts have exhausted quota")
                        db.commit()
                    except Exception as commit_error:
                        logger.error(f"Failed to commit task failure: {commit_error}")
                        db.rollback()

        except VerificationRequiredException as e:
            # Handle verification checkpoint - mark account and retry
            logger.warning(f"⚠️ Account #{account.id} requires verification: {e}")
            account_manager.mark_account_verification_needed(db, account)

            # Track account switches to prevent infinite loop
            account_switch_count = task.input_data.get("account_switch_count", 0) + 1

            if account_switch_count >= MAX_ACCOUNT_SWITCHES:
                logger.error(f"❌ Job #{job.id} exceeded max account switches ({MAX_ACCOUNT_SWITCHES})")
                try:
                    await task_manager.fail_task(job, "generate", f"Failed after switching {MAX_ACCOUNT_SWITCHES} accounts (verification required)")
                    db.commit()
                except Exception as commit_error:
                    logger.error(f"Failed to commit task failure: {commit_error}")
                    db.rollback()
            else:
                # Re-queue the job with this account excluded
                exclude_ids = task.input_data.get("exclude_account_ids", [])
                exclude_ids.append(account.id)

                # Check if there are other accounts available
                other_account = account_manager.get_available_account(db, platform="sora", exclude_ids=exclude_ids)

                if other_account:
                    logger.info(f"🔄 Re-queuing job #{job.id} with different account (due to verify, switch {account_switch_count}/{MAX_ACCOUNT_SWITCHES})...")
                    from .task_manager import TaskContext
                    new_task = TaskContext(
                        job_id=job.id,
                        task_type="generate",
                        input_data={
                            "prompt": job.prompt,
                            "duration": job.duration,
                            "account_id": None,  # Let it pick a new account
                            "exclude_account_ids": exclude_ids,
                            "account_switch_count": account_switch_count
                        },
                        retry_count=task.retry_count
                    )
                    await task_manager.generate_queue.put(new_task)
                else:
                     try:
                         await task_manager.fail_task(job, "generate", "All accounts failed verification or exhausted")
                         db.commit()
                     except Exception as commit_error:
                         logger.error(f"Failed to commit task failure: {commit_error}")
                         db.rollback()

        finally:
            if driver:
                logger.info("Closing driver session...")
                await driver.stop()
            if 'account_lock' in locals():
                account_lock.release()

    except Exception as e:
        logger.error(f"❌ Generate task failed for job #{job.id}: {e}")

        # SMART RETRY: If we have an account and haven't hit max retries, switch account
        retry_count = task.retry_count + 1
        max_retries = job.max_retries if job.max_retries else 3
        account_switch_count = task.input_data.get("account_switch_count", 0) + 1

        if account and retry_count <= max_retries and account_switch_count < MAX_ACCOUNT_SWITCHES:
             logger.warning(f"🔄 Smart Switch: Job #{job.id} failed on Account #{account.id}. Switching account (Attempt {retry_count}/{max_retries}, Switch {account_switch_count}/{MAX_ACCOUNT_SWITCHES})...")

             # Exclude this bad account
             exclude_ids = task.input_data.get("exclude_account_ids", [])
             exclude_ids.append(account.id)

             from .task_manager import TaskContext
             new_task = TaskContext(
                job_id=job.id,
                task_type="generate",
                input_data={
                    "prompt": job.prompt,
                    "duration": job.duration,
                    "account_id": None,  # Force pick new account
                    "exclude_account_ids": exclude_ids,
                    "account_switch_count": account_switch_count
                },
                retry_count=retry_count
             )
             await task_manager.generate_queue.put(new_task)
             try:
                 db.commit()
             except Exception as commit_error:
                 logger.error(f"Failed to commit retry: {commit_error}")
                 db.rollback()
        else:
            # Permanent failure or no account involved or too many switches
            failure_reason = str(e)
            if account_switch_count >= MAX_ACCOUNT_SWITCHES:
                failure_reason = f"Exceeded max account switches ({MAX_ACCOUNT_SWITCHES}): {e}"
            try:
                await task_manager.fail_task(job, "generate", failure_reason)
                db.commit()
            except Exception as commit_error:
                logger.error(f"Failed to commit task failure: {commit_error}")
                db.rollback()

    finally:
        # Always mark account as free
        if account:
            await account_manager.mark_account_free(account.id)
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
                async with _get_generate_semaphore():
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
MAX_POLL_COUNT = 60  # Max 60 polls x 30s = 30 minutes max wait

# Lazy-init poll semaphore
_poll_semaphore = None

def _get_poll_semaphore():
    """Lazy-init poll semaphore to avoid event loop attachment issues"""
    global _poll_semaphore
    if _poll_semaphore is None:
        _poll_semaphore = asyncio.Semaphore(MAX_CONCURRENT_POLL)
    return _poll_semaphore

async def process_single_poll_task(task):
    """Poll for video completion and move to download when ready"""
    db = database.SessionLocal()
    driver = None

    try:
        job = db.query(models.Job).filter(models.Job.id == task.job_id).first()

        if not job:
            logger.error(f"Job #{task.job_id} not found!")
            return

        account_id = task.input_data.get("account_id")
        account = db.query(models.Account).filter(models.Account.id == account_id).first()

        if not account:
            logger.error(f"Account #{account_id} not found for poll task!")
            return
        logger.info(f"🔍 Polling job #{job.id} video status...")
        
        # Acquire Lock for Profile Access
        account_lock = await get_account_lock(account.id)
        await account_lock.acquire()
        
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
            try:
                await task_manager.complete_poll(job, f"/downloads/{os.path.basename(local_path)}")
                job.local_path = f"/downloads/{os.path.basename(local_path)}"
                db.commit()
            except Exception as commit_error:
                logger.error(f"Failed to update job after poll completion: {commit_error}")
                db.rollback()
                raise

            logger.info(f"✅ Job #{job.id} downloaded: {local_path}")
        else:
            # Still generating - check poll limit before re-queueing
            poll_count = task.input_data.get("poll_count", 0) + 1

            if poll_count >= MAX_POLL_COUNT:
                logger.error(f"❌ Job #{job.id} exceeded max poll count ({MAX_POLL_COUNT}). Failing task.")
                try:
                    await task_manager.fail_task(job, "poll", f"Video did not complete after {MAX_POLL_COUNT} polls (30 minutes)")
                    db.commit()
                except Exception as commit_error:
                    logger.error(f"Failed to commit poll failure: {commit_error}")
                    db.rollback()
            else:
                # Re-queue with incremented poll count
                logger.info(f"⏳ Job #{job.id} still generating. Poll {poll_count}/{MAX_POLL_COUNT}. Will poll again in 30s...")
                await asyncio.sleep(30)

                # Re-add to poll queue with updated poll_count
                from .task_manager import TaskContext
                updated_input_data = task.input_data.copy()
                updated_input_data["poll_count"] = poll_count

                await task_manager.poll_queue.put(TaskContext(
                    job_id=job.id,
                    task_type="poll",
                    input_data=updated_input_data,
                    retry_count=task.retry_count
                ))
            
    except Exception as e:
        logger.error(f"❌ Poll task failed for job #{job.id}: {e}")
        try:
            await task_manager.fail_task(job, "poll", str(e))
            db.commit()
        except Exception as commit_error:
            logger.error(f"Failed to commit poll task failure: {commit_error}")
            db.rollback()

    finally:
        if driver:
            await driver.stop()
        if 'account_lock' in locals():
            account_lock.release()
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
                async with _get_poll_semaphore():
                    await process_single_poll_task(task)
            
            asyncio.create_task(process_with_semaphore())
            
        except Exception as e:
            logger.error(f"Poll worker error: {e}")
            await asyncio.sleep(1)


async def process_single_download_task(task):
    """Process a single download task"""
    db = database.SessionLocal()

    try:
        job = db.query(models.Job).filter(models.Job.id == task.job_id).first()

        if not job:
            logger.error(f"Job #{task.job_id} not found!")
            return
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

        try:
            db.commit()
            logger.info(f"✅ Download complete for job #{job.id}")
        except Exception as commit_error:
            logger.error(f"Failed to commit download completion: {commit_error}")
            db.rollback()
            raise

    except Exception as e:
        logger.error(f"❌ Download task failed for job #{job.id}: {e}")
        try:
            await task_manager.fail_task(job, "download", str(e))
            db.commit()
        except Exception as commit_error:
            logger.error(f"Failed to commit download failure: {commit_error}")
            db.rollback()
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
                async with _get_download_semaphore():
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
