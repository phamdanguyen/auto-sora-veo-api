import asyncio
import os
import logging
from app.core.drivers.sora.driver import SoraDriver
from app.core.drivers.sora.selectors import SoraSelectors
from app.database import SessionLocal
from app.models import Account
from app.core.security import decrypt_password

# Console logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def dump_settings_dialog():
    driver = None
    try:
        db = SessionLocal()
        account = db.query(Account).filter(Account.status == 'live').first()
        db.close()
        
        if not account:
            logger.error("No account found")
            return

        logger.info(f"Dumping Settings for {account.email}")
        
        profile_path = os.path.abspath(f"data/profiles/acc_{account.id}")
        driver = SoraDriver(headless=False, user_data_dir=profile_path)
        
        await driver.login(
            email=account.email, 
            password=decrypt_password(account.password)
        )
        
        page = driver.page
        
        # 1. Click Settings Button
        logger.info("Clicking Settings button...")
        await page.wait_for_selector(SoraSelectors.SETTINGS_BTN_DIRECT, timeout=10000)
        await page.click(SoraSelectors.SETTINGS_BTN_DIRECT)
        await asyncio.sleep(2)
        
        # 2. Click inner Settings (the menu item)
        for sel in SoraSelectors.SETTINGS_MENU_ITEM:
            if await page.is_visible(sel):
                logger.info(f"Clicking inner: {sel}")
                await page.click(sel)
                await asyncio.sleep(3)
                break
        
        # 3. Dump dialog content
        logger.info("--- SETTINGS DIALOG DUMP ---")
        
        # Try multiple containers
        containers = [
            "div[role='dialog']",
            "[class*='modal']",
            "[class*='Dialog']",
            "main",
            "[id*='settings']"
        ]
        
        for sel in containers:
            try:
                if await page.is_visible(sel):
                    text = await page.inner_text(sel)
                    if len(text) > 50:
                        logger.info(f"=== Container: {sel} ===")
                        logger.info(text[:2000])
            except:
                pass
        
        # Fallback: full body text lines with numbers
        logger.info("=== Lines with numbers ===")
        body_text = await page.inner_text("body")
        for line in body_text.split('\n'):
            line = line.strip()
            if line and any(c.isdigit() for c in line):
                logger.info(line)
        
        # Save page HTML
        content = await page.content()
        with open("data/debug/settings_dialog.html", "w") as f:
            f.write(content)
        logger.info("Saved HTML to data/debug/settings_dialog.html")
        
        # Screenshot
        await page.screenshot(path="settings_dialog.png")
        logger.info("Screenshot saved to settings_dialog.png")

    except Exception as e:
        logger.error(f"Dump failed: {e}")
    finally:
        if driver:
            await driver.stop()

if __name__ == "__main__":
    asyncio.run(dump_settings_dialog())
