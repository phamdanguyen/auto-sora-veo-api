import logging
import asyncio
from playwright.async_api import Page, ElementHandle
from typing import Optional, List, Union

logger = logging.getLogger(__name__)

class BasePage:
    def __init__(self, page: Page):
        self.page = page

    async def _snapshot(self, name: str):
        """Helper to save debug screenshot safely"""
        try:
            import os
            path = f"data/debug/{name}.png"
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if self.page:
                 await self.page.screenshot(path=path)
                 logger.debug(f"Saved snapshot: {path}")
        except Exception as e:
            logger.error(f"Failed to save snapshot {name}: {e}")

    async def _dump_html(self, name: str):
        """Helper to save HTML source"""
        try:
            import os
            path = f"data/debug/{name}.html"
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if self.page:
                content = await self.page.content()
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.debug(f"Saved HTML dump: {path}")
        except Exception as e:
            logger.error(f"Failed to dump HTML {name}: {e}")

    async def find_first_visible(self, selectors: List[str], timeout: int = 1000) -> Optional[tuple[str, ElementHandle]]:
        """
        Iterates through a list of selectors and returns the first one that is visible.
        Returns: tuple (selector_string, element_handle) or None
        """
        for sel in selectors:
            try:
                if await self.page.is_visible(sel, timeout=timeout):
                    el = await self.page.query_selector(sel)
                    return sel, el
            except:
                continue
        return None

    async def click_if_visible(self, selector: str, timeout: int = 500) -> bool:
        try:
            if await self.page.is_visible(selector, timeout=timeout):
                await self.page.click(selector)
                return True
        except:
            pass
    async def human_type(self, selector: str, text: str):
        """Simulate human typing with random delays"""
        import random
        import sys
        try:
            # Focus element
            await self.page.click(selector)
            
            # Clear existing content using keyboard (more robust than fill(""))
            # Mac matches 'Meta', Windows/Linux uses 'Control'
            modifier = "Meta" if sys.platform == "darwin" else "Control"
            await self.page.keyboard.press(f"{modifier}+A")
            await self.page.keyboard.press("Backspace")
            
            # Type characters with varying delays
            for char in text:
                await self.page.keyboard.type(char)
                # Random delay 20ms to 100ms
                delay = random.uniform(0.02, 0.1) 
                await asyncio.sleep(delay)
                
            return True
        except Exception as e:
            logger.warning(f"Human type failed: {e}")
            return False
