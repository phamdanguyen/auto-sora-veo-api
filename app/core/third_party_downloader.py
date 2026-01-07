"""
Third-party video downloader module
Downloads Sora videos from public links using external services (dyysy.com, soravdl.com)
to remove watermark and ensure correct video is downloaded
"""
import os
import time
import logging
import asyncio
import uuid
from typing import Optional, Tuple
from playwright.async_api import Page, Download

logger = logging.getLogger(__name__)


class PublicLinkNotFoundException(Exception):
    """Raised when public link cannot be found or obtained"""
    pass


class ThirdPartyDownloaderError(Exception):
    """Raised when all third-party services fail"""
    pass


class ThirdPartyDownloader:
    """
    Downloads Sora videos from public links using third-party services
    Supports: dyysy.com (primary), soravdl.com (fallback)
    
    Concurrency: Uses class-level semaphore to limit concurrent requests
    """
    
    # Class-level semaphore (lazy-initialized)
    _semaphore = None
    _max_concurrent = 3

    def __init__(self):
        self.services = [
            {
                "name": "dyysy",
                "url": "https://dyysy.com/",
                "download_method": self._download_via_dyysy
            },
            {
                "name": "soravdl",
                "url": "https://soravdl.com/",
                "download_method": self._download_via_soravdl
            }
        ]

    @classmethod
    def _get_semaphore(cls):
        """Lazy-init semaphore to avoid event loop issues"""
        if cls._semaphore is None:
            cls._semaphore = asyncio.Semaphore(cls._max_concurrent)
        return cls._semaphore
    
    async def download_from_public_link(
        self,
        page: Page,
        public_link: str,
        output_dir: str = "data/downloads"
    ) -> Tuple[str, int]:
        """
        Download video from Sora public link via third-party services

        Args:
            page: Playwright page object (for browser automation)
            public_link: Public link of Sora video (e.g., https://sora.chatgpt.com/share/xxx)
            output_dir: Directory to save downloaded video

        Returns:
            tuple: (local_path, file_size)

        Raises:
            ThirdPartyDownloaderError: If all services fail
        """
        os.makedirs(output_dir, exist_ok=True)

        # Use class-level semaphore
        async with self._get_semaphore():
            # Try each service in order
            last_error = None
            for service in self.services:
                try:
                    logger.info(f"Attempting download via {service['name']}...")
                    local_path, file_size = await service["download_method"](
                        page, public_link, output_dir
                    )
                    logger.info(f"✅ Successfully downloaded via {service['name']}: {local_path}")
                    return local_path, file_size

                except Exception as e:
                    logger.warning(f"❌ {service['name']} failed: {e}")
                    last_error = e
                    continue

            # All services failed
            raise ThirdPartyDownloaderError(
                f"All third-party services failed. Last error: {last_error}"
            )

    async def _download_via_dyysy(
        self,
        page: Page,
        public_link: str,
        output_dir: str
    ) -> Tuple[str, int]:
        """
        Download video using dyysy.com

        Steps:
        1. Navigate to dyysy.com
        2. Paste public link into input field
        3. Click download/process button
        4. Wait for download to start
        5. Save file
        """
        try:
            logger.info("Navigating to dyysy.com...")
            await page.goto("https://dyysy.com/", wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Find and fill input field for Sora link
            input_selectors = [
                "input[placeholder*='sora' i]",
                "input[placeholder*='link' i]",
                "input[type='text']",
                "textarea"
            ]

            input_found = False
            for selector in input_selectors:
                try:
                    if await page.is_visible(selector, timeout=2000):
                        await page.fill(selector, public_link)
                        logger.info(f"Filled public link into input: {selector}")
                        input_found = True
                        break
                except:
                    continue

            if not input_found:
                raise Exception("Could not find input field on dyysy.com")

            # Click download/submit button
            button_selectors = [
                "button:has-text('Download')",
                "button:has-text('Get')",
                "button:has-text('Submit')",
                "button[type='submit']",
                "input[type='submit']"
            ]

            button_clicked = False
            for selector in button_selectors:
                try:
                    if await page.is_visible(selector, timeout=2000):
                        await page.click(selector)
                        logger.info(f"Clicked button: {selector}")
                        button_clicked = True
                        break
                except:
                    continue

            if not button_clicked:
                raise Exception("Could not find submit/download button on dyysy.com")

            # Wait for processing and download link
            await asyncio.sleep(5)

            # Setup download handler
            download_path = await self._handle_download(page, output_dir, timeout=60)

            if not download_path:
                raise Exception("Download did not start within timeout")

            file_size = os.path.getsize(download_path)
            return download_path, file_size

        except Exception as e:
            raise Exception(f"dyysy.com download failed: {e}")

    async def _download_via_soravdl(
        self,
        page: Page,
        public_link: str,
        output_dir: str
    ) -> Tuple[str, int]:
        """
        Download video using soravdl.com

        Similar to dyysy but with different selectors
        """
        try:
            logger.info("Navigating to soravdl.com...")
            await page.goto("https://soravdl.com/", wait_until="domcontentloaded")
            await asyncio.sleep(2)

            # Find and fill input field
            input_selectors = [
                "input[placeholder*='sora' i]",
                "input[placeholder*='link' i]",
                "input[placeholder*='url' i]",
                "input[type='text']",
                "textarea"
            ]

            input_found = False
            for selector in input_selectors:
                try:
                    if await page.is_visible(selector, timeout=2000):
                        await page.fill(selector, public_link)
                        logger.info(f"Filled public link into input: {selector}")
                        input_found = True
                        break
                except:
                    continue

            if not input_found:
                raise Exception("Could not find input field on soravdl.com")

            # Click download button
            button_selectors = [
                "button:has-text('Download')",
                "button:has-text('Get Video')",
                "button:has-text('Process')",
                "button[type='submit']"
            ]

            button_clicked = False
            for selector in button_selectors:
                try:
                    if await page.is_visible(selector, timeout=2000):
                        await page.click(selector)
                        logger.info(f"Clicked button: {selector}")
                        button_clicked = True
                        break
                except:
                    continue

            if not button_clicked:
                raise Exception("Could not find download button on soravdl.com")

            # Wait for processing
            await asyncio.sleep(5)

            # Handle download
            download_path = await self._handle_download(page, output_dir, timeout=60)

            if not download_path:
                raise Exception("Download did not start within timeout")

            file_size = os.path.getsize(download_path)
            return download_path, file_size

        except Exception as e:
            raise Exception(f"soravdl.com download failed: {e}")

    async def _handle_download(
        self,
        page: Page,
        output_dir: str,
        timeout: int = 60
    ) -> Optional[str]:
        """
        Handle browser download event and save file

        Args:
            page: Playwright page
            output_dir: Directory to save file
            timeout: Max seconds to wait for download

        Returns:
            str: Path to downloaded file, or None if timeout
        """
        download_path = None

        async def on_download(download: Download):
            nonlocal download_path
            # Use timestamp + UUID to prevent filename collision in concurrent scenarios
            timestamp = int(time.time())
            unique_id = uuid.uuid4().hex[:8]  # 8-character unique ID
            filename = f"video_{timestamp}_{unique_id}.mp4"
            save_path = os.path.join(output_dir, filename)

            logger.info(f"Download started: {download.suggested_filename}")
            await download.save_as(save_path)
            logger.info(f"Download saved to: {save_path}")
            download_path = save_path

        page.on("download", on_download)

        # Wait for download to complete (or timeout)
        start_time = time.time()
        while not download_path and (time.time() - start_time) < timeout:
            await asyncio.sleep(1)

        page.remove_listener("download", on_download)
        return download_path
