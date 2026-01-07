import logging
from .drivers.sora import SoraDriver
# from .drivers.veo3 import Veo3Driver # Future
from .. import models
import asyncio

logger = logging.getLogger(__name__)

from .drivers.sora import SoraDriver
# from .drivers.veo3 import Veo3Driver # Future
from .. import models, database
import asyncio

logger = logging.getLogger(__name__)

async def run_job(job_id: int, account_id: int):
    """
    Execute the job using the appropriate driver based on account platform.
    """
    db = database.SessionLocal()
    driver = None
    try:
        job = db.query(models.Job).get(job_id)
        account = db.query(models.Account).get(account_id)
        
        if not job or not account:
            logger.error("Job or Account not found in background task")
            return

        logger.info(f"Starting job {job.id} on platform {account.platform}")
        
        if account.platform == "sora":
            driver = SoraDriver(headless=False, proxy=account.proxy) # Headless=False for demo/MVP
        # elif account.platform == "veo3":
        #     driver = Veo3Driver(...)
        else:
            raise Exception(f"Unsupported platform: {account.platform}")

        # Login
        await driver.login(cookies=account.cookies)
        
        # Create Video
        video_url = await driver.create_video(prompt=job.prompt, image_path=job.image_path)
        
        # Update Job
        job.status = "completed"
        job.video_url = video_url
        db.commit()
        logger.info(f"Job {job.id} completed successfully.")

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        # Re-fetch job to ensure session is valid for update if needed (though session is local here)
        try:
            job.status = "failed"
            job.error_message = str(e)
            db.commit()
        except:
            pass
    finally:
        if driver:
            await driver.stop()
        db.close()
