"""
Standalone download utility for video files
Extracted from driver logic for task-based architecture
"""
import os
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

async def download_from_url(page, video_url: str, download_dir: str = "data/downloads") -> tuple[str, int]:
    """
    Download video from URL using authenticated Playwright session
    
    Args:
        page: Playwright page object (for auth session)
        video_url: URL of the video to download
        download_dir: Directory to save the video
    
    Returns:
        tuple: (local_path, file_size)
    
    Raises:
        Exception: If download fails
    """
    try:
        logger.info(f"📥 Downloading video from {video_url[:80]}...")
        
        # Create download directory
        os.makedirs(download_dir, exist_ok=True)
        
        # Generate filename
        timestamp = int(time.time())
        filename = f"video_{timestamp}.mp4"
        local_path = os.path.join(download_dir, filename)
        
        # Download using Playwright's authenticated session
        response = await page.request.get(video_url)
        
        if response.status != 200:
            raise Exception(f"HTTP {response.status} when downloading video")
        
        body = await response.body()
        file_size = len(body)
        
        # Save to disk
        with open(local_path, "wb") as f:
            f.write(body)
        
        logger.info(f"✅ Downloaded video: {local_path} ({file_size:,} bytes)")
        
        return local_path, file_size
        
    except Exception as e:
        logger.error(f"❌ Download failed: {e}")
        raise
