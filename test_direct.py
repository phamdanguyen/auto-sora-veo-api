"""
Test Settings -> Usage flow with direct Playwright commands
Bypasses all wrapper code to verify core functionality.
"""
import asyncio
import os
import logging
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_direct_credits():
    async with async_playwright() as p:
        # Use existing profile
        profile = os.path.abspath("data/profiles/acc_3")
        browser = await p.chromium.launch_persistent_context(
            profile,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = browser.pages[0] if browser.pages else await browser.new_page()
        
        # Navigate to Sora
        logger.info("Navigating to Sora...")
        await page.goto("https://sora.chatgpt.com/")
        await asyncio.sleep(5)
        
        # Click Settings button
        logger.info("Clicking Settings button...")
        await page.click("button[aria-label='Settings']")
        await asyncio.sleep(2)
        
        # Click Settings menu item
        logger.info("Clicking Settings menu item...")
        await page.click("div[role='menuitem']:has-text('Settings')")
        await asyncio.sleep(3)
        
        # NOW query for Usage tab
        logger.info("=== Searching for Usage tab ===")
        usage_button = await page.query_selector("button[role='tab'][id*='trigger-usage']")
        if usage_button:
            logger.info("Found Usage tab! Clicking...")
            await usage_button.click()
            await asyncio.sleep(3)
        else:
            logger.error("Usage tab NOT FOUND with primary selector")
            # Try text
            usage_by_text = await page.query_selector("button:has-text('Usage')")
            if usage_by_text:
                logger.info("Found Usage by text. Clicking...")
                await usage_by_text.click()
                await asyncio.sleep(3)
            else:
                logger.error("Usage tab NOT FOUND by text either!")
                
        # Dump page text
        logger.info("=== Page text (tab panel) ===")
        try:
            text = await page.inner_text("div[role='tabpanel'][data-state='active']")
            logger.info(text[:1000])
        except:
            body = await page.inner_text("body")
            for line in body.split('\n'):
                if 'free' in line.lower() or 'usage' in line.lower():
                    logger.info(f"=> {line.strip()}")
        
        # Screenshot
        await page.screenshot(path="direct_settings_test.png")
        logger.info("Screenshot saved")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_direct_credits())
