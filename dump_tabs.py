"""
Dump all tab-related elements in the Settings dialog.
"""
import asyncio
import os
import logging
from app.core.drivers.sora.driver import SoraDriver
from app.core.drivers.sora.selectors import SoraSelectors
from app.database import SessionLocal
from app.models import Account
from app.core.security import decrypt_password

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def dump_tabs():
    driver = None
    try:
        db = SessionLocal()
        account = db.query(Account).filter(Account.id == 3).first()
        db.close()
        
        logger.info(f"Dumping tab elements for {account.email}")
        
        profile_path = os.path.abspath(f"data/profiles/acc_{account.id}")
        driver = SoraDriver(headless=False, user_data_dir=profile_path)
        
        await driver.login(
            email=account.email, 
            password=decrypt_password(account.password)
        )
        
        page = driver.page
        
        # Click Settings Button
        await page.wait_for_selector(SoraSelectors.SETTINGS_BTN_DIRECT, timeout=10000)
        await page.click(SoraSelectors.SETTINGS_BTN_DIRECT)
        await asyncio.sleep(2)
        
        # Click inner Settings
        for sel in SoraSelectors.SETTINGS_MENU_ITEM:
            try:
                if await page.is_visible(sel):
                    await page.click(sel)
                    await asyncio.sleep(3)
                    break
            except:
                pass
        
        # Now dump all tabs
        logger.info("=== DUMPING TAB ELEMENTS ===")
        
        # Get all elements with role="tab" 
        tabs = await page.query_selector_all("[role='tab']")
        logger.info(f"Found {len(tabs)} elements with role='tab'")
        for tab in tabs:
            text = await tab.inner_text()
            html = await tab.evaluate("el => el.outerHTML.substring(0, 500)")
            logger.info(f"Tab: '{text}' -> {html}")
        
        # Try specific pattern
        usage_elements = await page.query_selector_all("[id*='usage']")
        logger.info(f"Found {len(usage_elements)} elements with id containing 'usage'")
        for el in usage_elements:
            html = await el.evaluate("el => el.outerHTML.substring(0, 300)")
            logger.info(f"Usage element: {html}")
            
        # Take screenshot
        await page.screenshot(path="tabs_debug.png")
        logger.info("Screenshot saved to tabs_debug.png")

    except Exception as e:
        logger.error(f"Dump failed: {e}")
    finally:
        if driver:
            await driver.stop()

if __name__ == "__main__":
    asyncio.run(dump_tabs())
