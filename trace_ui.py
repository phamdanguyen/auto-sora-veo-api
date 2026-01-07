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

async def trace_settings_ui():
    driver = None
    try:
        # Use a live account (Account 12 from logs: eaganzbeighnsb@hotmail.com)
        # Or just pick the first live one
        db = SessionLocal()
        account = db.query(Account).filter(Account.status == 'live').first()
        db.close()
        
        if not account:
            logger.error("No account found")
            return

        logger.info(f"Tracing UI for {account.email}")
        
        profile_path = os.path.abspath(f"data/profiles/acc_{account.id}")
        driver = SoraDriver(headless=False, user_data_dir=profile_path)
        
        await driver.login(
            email=account.email, 
            password=decrypt_password(account.password)
        )
        
        page = driver.page
        
        # 1. Click Settings (New Direct Button)
        logger.info("Clicking Settings button...")
        try:
            # Force wait for hydration
            await page.wait_for_selector(SoraSelectors.SETTINGS_BTN_DIRECT, timeout=10000)
            await page.click(SoraSelectors.SETTINGS_BTN_DIRECT)
            await asyncio.sleep(3) # Wait for animation/portal
        except Exception as e:
            logger.error(f"Failed to click settings: {e}")
            
        # 2. Dump all text in the potential menu/dialog
        # Often these are in div[role='menu'] or div[role='dialog']
        logger.info("--- TEXT DUMP START ---")
        
        # Determine likely containers for the menu
        containers = [
            "div[role='menu']",
            "div[role='dialog']",
            "div[data-radix-popper-content-wrapper]"
        ]
        
        found_container = False
        for sel in containers:
            if await page.is_visible(sel):
                logger.info(f"Found visible container: {sel}")
                text = await page.inner_text(sel)
                logger.info(f"Container Text:\n{text}")
                found_container = True
        
        if not found_container:
            logger.warning("No standard menu/dialog container found. Dumping body text.")
            # Fallback: dump body text but truncated
            text = await page.inner_text("body")
            # Log lines containing numbers
            for line in text.split('\n'):
                if any(char.isdigit() for char in line):
                    logger.info(f"Line with numbers: {line}")
                    
        logger.info("--- TEXT DUMP END ---")
        
        # 3. Check for blocking popups (Create character etc)
        # Just log if we see them
        content = await page.content()
        if "Create your character" in content:
            logger.info("ALERT: 'Create your character' popup text detected in DOM")
        if "app" in content.lower():
             logger.info("ALERT: 'app' text detected (possible banner)")

        # Take screenshot for visual confirmation
        await page.screenshot(path="trace_settings.png")
        logger.info("Screenshot saved to trace_settings.png")

    except Exception as e:
        logger.error(f"Trace failed: {e}")
    finally:
        if driver:
            await driver.stop()

if __name__ == "__main__":
    asyncio.run(trace_settings_ui())
