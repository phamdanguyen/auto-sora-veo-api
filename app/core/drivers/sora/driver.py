from ..base import BaseDriver
from .pages.login import SoraLoginPage
from .pages.creation import SoraCreationPage
import logging
import asyncio
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)

class SoraDriver(BaseDriver):
    def __init__(self, headless: bool = False, proxy: Optional[str] = None, user_data_dir: Optional[str] = None):
        super().__init__(headless=headless, proxy=proxy, user_data_dir=user_data_dir)
        # Use direct auth URL for reliable login flow
        self.base_url = "https://chatgpt.com/auth/login?next=%2Fsora%2F"
        
        # Page Objects (initialized after start)
        self.login_page = None
        self.creation_page = None

    async def start(self):
        await super().start()
        self.login_page = SoraLoginPage(self.page)
        self.creation_page = SoraCreationPage(self.page)
    
    async def check_credits(self) -> int:
        """Get remaining video credits"""
        if self.creation_page:
            return await self.creation_page.check_credits()
        return -1

    async def login(self, email: Optional[str] = None, password: Optional[str] = None, cookies: Optional[dict] = None) -> dict:
        await self.start()
        
        if cookies:
            logger.info("Loading existing cookies...")
            # Todo: Implement actual cookie loading if needed
            pass
            
        await self.login_page.login(email or "", password or "", self.base_url)
        return await self.context.cookies()

    async def submit_video(self, prompt: str) -> dict:
        """
        Submit video generation request and return IMMEDIATELY after confirmation.
        Does NOT wait for video completion.
        
        Args:
            prompt: Video generation prompt
            
        Returns:
            dict: {
                "submitted": bool - True if credit decreased (confirmed),
                "credits_before": int,
                "credits_after": int
            }
        """
        from .pages.creation import QuotaExhaustedException
        
        if not await self.login_page.check_is_logged_in():
            logger.error("User not logged in.")
            raise Exception("Session expired or not logged in.")
        
        # Check credits BEFORE
        logger.info("Checking credits before submission...")
        credits_before = await self.check_credits()
        
        if credits_before == 0:
            logger.warning("Credits are 0. Aborting submission.")
            raise QuotaExhaustedException("Account has 0 credits remaining.")
        
        logger.info(f"Credits BEFORE: {credits_before}")
        
        # Fill prompt and submit
        await self.creation_page.fill_prompt(prompt)
        
        # Capture UI Success Status
        ui_success = await self.creation_page.click_generate(prompt)
        
        # Wait for UI to update (with retry)
        credits_after = -1
        submitted = False
        
        if ui_success:
             logger.info("✅ Submission confirmed via UI state change. Now verifying credit deduction...")
        
        # Strict polling loop: Check credits for up to 60 seconds (variable intervals)
        # Sora can be slow to update credits sometimes
        retry_intervals = [2] * 30  # 30 attempts * 2 seconds = 60 seconds max
        
        for attempt, wait_time in enumerate(retry_intervals):
            await asyncio.sleep(wait_time)
            
            # Handle potential post-click popups that might appear late
            if attempt % 5 == 0: # Check every 10 seconds
                 try:
                     await self.creation_page.handle_blocking_popups()
                 except Exception as e:
                     logger.warning(f"Benign error handling popups during verification: {e}")
            
            credits_after = await self.check_credits()
            
            if credits_before != -1 and credits_after != -1:
                credit_used = credits_before - credits_after
                
                if credit_used >= 1:
                    logger.info(f"✅ Credit reduction verified! Credits: {credits_before} → {credits_after} (Attempt {attempt+1})")
                    submitted = True
                    break
                
                elif credit_used < 0:
                     # Rare case: credits increased? (Refund or top-up)
                     logger.warning(f"⚠️ Credits INCREASED? {credits_before} → {credits_after}. Continuing verification...")
                     
                else: # credit_used == 0
                     # Log progress every few attempts
                     if attempt % 5 == 0:
                         logger.info(f"⏳ Waiting for credit drop... ({credits_before} remaining) - Attempt {attempt+1}/{len(retry_intervals)}")

                     # Secondary Check REMOVED for Strict Verification
                     # We rely ONLY on credit deduction.
                     pass
                     
            else:
                 logger.warning("⚠️ Could not read credits during verification.")

        if not submitted:
             logger.error(f"❌ Verification FAILED. Credits did not decrease after 60s. Before: {credits_before}, After: {credits_after}")
             # Visual check removed - Strict Logic

        
        if not submitted:
             # STRICT FAILURE: If we couldn't verify, we return False (or raise exception)
             # The caller (worker) handles 'submitted: False' by marking as failed/retry.
             logger.error("🛑 Strict verification failed: No credit drop & no visual confirmation.")
        
        return {
            "submitted": submitted,
            "credits_before": credits_before,
            "credits_after": credits_after
        }
    
    async def check_video_status(self) -> str:
        """
        Check if video generation is complete.
        
        Returns:
            str: "generating" | "completed" | "unknown"
        """
        # Check for completion indicators
        from .selectors import SoraSelectors
        
        for indicator in SoraSelectors.VIDEO_COMPLETION_INDICATORS:
            try:
                if await self.page.is_visible(indicator, timeout=2000):
                    logger.info(f"Video status: completed (indicator: {indicator})")
                    return "completed"
            except:
                continue
        
        # If not completed, assume still generating
        return "generating"
    
    async def get_video_public_link(self) -> str:
        """
        Get public link for completed video.
        
        Returns:
            str: Public video URL
        """
        return await self.creation_page.get_public_link()

    async def create_video(self, prompt: str, image_path: Optional[str] = None, check_cancel: Optional[Callable[[], Awaitable[bool]]] = None):
        """
        Create (generate) a video with prompt using new approach:
        1. Fill prompt and click generate
        2. Wait for video completion (UI-based)
        3. Get public link
        4. Download via third-party service (removes watermark)
        
        Returns:
            str: Local path to downloaded video (e.g., "/downloads/video_123.mp4")
        """
        if not await self.login_page.check_is_logged_in():
            logger.error("User not logged in.")
            raise Exception("Session expired or not logged in.")
        
        if check_cancel and await check_cancel():
             raise Exception("Cancelled by user (Before Start)")
             
        # New Requirement: Check credits BEFORE generating
        logger.info("Checking credits before generation...")
        credits_before = await self.check_credits()
        
        # Raise QuotaExhaustedException if credits are 0
        if credits_before == 0:
            logger.warning("Credits are 0. Aborting generation.")
            raise QuotaExhaustedException("Account has 0 credits remaining.")
        
        logger.info(f"Credits BEFORE: {credits_before}. Proceeding with generation.")
             
        logger.info(f"Creating video with prompt: {prompt}")
        
        # 1. Fill Prompt
        await self.creation_page.fill_prompt(prompt)
        
        if check_cancel and await check_cancel():
             raise Exception("Cancelled by user (Before Submit)")

        # 2. Click Generate
        await self.creation_page.click_generate()
        
        # 3. NEW: Verify video was queued by checking credits decreased
        logger.info("Verifying video was queued (checking credits after submission)...")
        import asyncio
        await asyncio.sleep(3)  # Wait for UI to update
        credits_after = await self.check_credits()
        
        if credits_before != -1 and credits_after != -1:
            credit_used = credits_before - credits_after
            if credit_used == 1:
                logger.info(f"✅ Video queued confirmed! Credits: {credits_before} → {credits_after} (used: {credit_used})")
            elif credit_used == 0:
                logger.warning(f"⚠️ Credits unchanged ({credits_before} → {credits_after}). Video may NOT have been queued!")
            else:
                logger.warning(f"⚠️ Unexpected credit change: {credits_before} → {credits_after} (diff: {credit_used})")
        else:
            logger.warning("Could not verify credit change (credits unavailable)")
        
        # 4. Wait for video completion (UI-based, not network-based)
        logger.info("Waiting for video generation to complete...")
        completed = await self.creation_page.wait_for_video_completion(max_wait=300)
        
        if not completed:
            raise Exception("Video generation timeout - video did not complete within 300 seconds")
        
        if check_cancel and await check_cancel():
             raise Exception("Cancelled by user (After Completion)")
        
        # 4. Get public link
        logger.info("Getting public link...")
        public_link = await self.creation_page.get_public_link()
        logger.info(f"Public link obtained: {public_link}")
        
        # 5. Download via third-party service
        from ..third_party_downloader import ThirdPartyDownloader
        
        downloader = ThirdPartyDownloader()
        local_path, file_size = await downloader.download_from_public_link(
            self.page,
            public_link
        )
        
        logger.info(f"✅ Video downloaded successfully: {local_path} ({file_size:,} bytes)")
        
        # Return web-accessible path
        filename = os.path.basename(local_path)
        return f"/downloads/{filename}"

    async def _download_video(self, url: str) -> str:
        """
        Legacy direct download method - DEPRECATED
        Kept for backward compatibility but should not be used
        as it's the root cause of incorrect downloads
        """
        import os
        import time
        logger.warning("⚠️ Using deprecated _download_video method - this may download incorrect video!")
        timestamp = int(time.time())
        filename = f"video_{timestamp}.mp4"
        download_dir = os.path.abspath("data/downloads")
        os.makedirs(download_dir, exist_ok=True)
        local_path = os.path.join(download_dir, filename)
        
        response = await self.page.request.get(url)
        if response.status == 200:
            body = await response.body()
            with open(local_path, "wb") as f:
                f.write(body)
            logger.info(f"✅ Video downloaded: {local_path}")
            return f"/downloads/{filename}"
        else:
            raise Exception(f"Download failed: {response.status}")
