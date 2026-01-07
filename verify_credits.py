import asyncio
import logging
import sys
import os

# Setup path to import app modules
sys.path.append(os.getcwd())

from app.core.drivers.sora.driver import SoraDriver
from app.core.security import decrypt_password

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

async def verify_credits_standalone():
    driver = None
    try:
        # Use account 12 (haitzohondamb8d@hotmail.com) from previous run
        email = "haitzohondamb8d@hotmail.com"
        # We need the real password. In a real scenario, we fetch from DB.
        # For this test script, assuming we can get the account from DB or hardcode for test.
        # Let's fetch from DB to be clean.
        from app.database import SessionLocal
        from app.models import Account
        
        db = SessionLocal()
        account = db.query(Account).filter(Account.email == email).first()
        db.close()
        
        if not account:
            logger.error("Account not found in DB!")
            return

        logger.info(f"🚀 Starting Credit Verification for {email}...")
        
        # Initialize Driver (Headful for debugging/bypassing)
        profile_path = os.path.abspath(f"data/profiles/acc_{account.id}")
        driver = SoraDriver(headless=False, user_data_dir=profile_path)
        
        # Login
        await driver.login(
            email=account.email,
            password=decrypt_password(account.password)
        )
        
        # Custom interaction for verification
        logger.info("👉 Attempting to click direct 'Settings' button via JS...")
        try:
             # Wait for settings button
             settings_btn = await driver.page.wait_for_selector("button[aria-label='Settings']", timeout=10000)
             if settings_btn:
                 # Use JS click (Correct Playwright Syntax)
                 await settings_btn.evaluate("node => node.click()")
                 logger.info("Clicked 'Settings' button via JS.")
                 await asyncio.sleep(5) # Wait longer for popover
             else:
                 logger.warning("Settings button not found.")
        except Exception as e:
             logger.warning(f"Could not click settings: {e}")

        # Capture screenshot for proof
        logger.info("📸 Taking screenshot of Settings Popover...")
        await driver.page.screenshot(path="data/debug/credits_proof.png", full_page=True)
        
        # Dump HTML
        content = await driver.page.content()
        with open("data/debug/settings.html", "w") as f:
            f.write(content)
        
        if credits != -1:
            logger.info(f"✅ CONFIRMED: Account has {credits} credits remaining.")
        else:
            logger.warning("❌ Could not parse credit number from text.")
            
    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        if driver:
             await driver.page.screenshot(path="data/debug/verify_error.png")
    finally:
        if driver:
            logger.info("Closing driver...")
            # await driver.stop() # Keep open briefly to see? No, close to be clean.
            await driver.stop()

if __name__ == "__main__":
    asyncio.run(verify_credits_standalone())
