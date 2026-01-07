"""
Direct Credit Check Test - Uses known good account (acc_3) 
to verify credit parsing logic works.
"""
import asyncio
import os
import logging
from app.core.drivers.sora.driver import SoraDriver
from app.core.drivers.sora.selectors import SoraSelectors
from app.database import SessionLocal
from app.models import Account
from app.core.security import decrypt_password
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_credit_check():
    driver = None
    try:
        # Use Account 3 - worked earlier
        db = SessionLocal()
        account = db.query(Account).filter(Account.id == 3).first()
        db.close()
        
        if not account:
            logger.error("Account 3 not found")
            return

        logger.info(f"Testing credit check for {account.email}")
        
        profile_path = os.path.abspath(f"data/profiles/acc_{account.id}")
        driver = SoraDriver(headless=False, user_data_dir=profile_path)
        
        await driver.login(
            email=account.email, 
            password=decrypt_password(account.password)
        )
        
        # Now call the actual check_credits method
        logger.info("=== CALLING check_credits() ===")
        credits = await driver.check_credits()
        
        logger.info(f"=== RESULT: credits = {credits} ===")
        
        if credits != -1:
            logger.info(f"SUCCESS! Credits found: {credits}")
        else:
            logger.error("FAILED: Could not parse credits")
            
    except Exception as e:
        logger.error(f"Test failed: {e}")
    finally:
        if driver:
            await driver.stop()

if __name__ == "__main__":
    asyncio.run(test_credit_check())
