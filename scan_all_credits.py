"""
Batch Credit Scanner - Check credits for ALL accounts and update DB.
Skips accounts that fail login (2FA issues).
"""
import asyncio
import os
import logging
from datetime import datetime
from app.core.drivers.sora.driver import SoraDriver
from app.database import SessionLocal
from app.models import Account
from app.core.security import decrypt_password

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def scan_all_accounts():
    db = SessionLocal()
    accounts = db.query(Account).all()
    db.close()
    
    logger.info(f"Found {len(accounts)} accounts to scan")
    
    results = []
    
    for acc in accounts:
        logger.info(f"\n{'='*50}")
        logger.info(f"Scanning Account #{acc.id}: {acc.email}")
        logger.info(f"{'='*50}")
        
        driver = None
        try:
            profile_path = os.path.abspath(f"data/profiles/acc_{acc.id}")
            driver = SoraDriver(headless=False, user_data_dir=profile_path)
            
            # Try to login
            await driver.login(
                email=acc.email, 
                password=decrypt_password(acc.password)
            )
            
            # Check if logged in
            if not await driver.login_page.check_is_logged_in():
                logger.warning(f"⚠️ Account #{acc.id} - Login failed or requires 2FA")
                results.append({'id': acc.id, 'email': acc.email, 'credits': None, 'error': 'login_failed'})
                continue
            
            # Check credits
            credits = await driver.check_credits()
            
            if credits != -1:
                # Update DB - credits and status
                db = SessionLocal()
                db_acc = db.query(Account).filter(Account.id == acc.id).first()
                db_acc.credits_remaining = credits
                db_acc.credits_last_checked = datetime.utcnow()
                # Set status based on credits
                if credits > 0:
                    db_acc.status = 'live'
                else:
                    db_acc.status = 'cooldown'
                db.commit()
                db.close()
                
                logger.info(f"✅ Account #{acc.id} - Credits: {credits}")
                results.append({'id': acc.id, 'email': acc.email, 'credits': credits, 'error': None})
            else:
                logger.warning(f"⚠️ Account #{acc.id} - Could not parse credits")
                results.append({'id': acc.id, 'email': acc.email, 'credits': None, 'error': 'parse_failed'})
                
        except Exception as e:
            logger.error(f"❌ Account #{acc.id} - Error: {e}")
            results.append({'id': acc.id, 'email': acc.email, 'credits': None, 'error': str(e)})
        finally:
            if driver:
                await driver.stop()
        
        # Small delay between accounts
        await asyncio.sleep(2)
    
    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("SUMMARY")
    logger.info(f"{'='*60}")
    
    total_credits = 0
    successful = 0
    for r in results:
        if r['credits'] is not None:
            logger.info(f"Account #{r['id']} ({r['email'][:20]}...): {r['credits']} credits")
            total_credits += r['credits']
            successful += 1
        else:
            logger.info(f"Account #{r['id']} ({r['email'][:20]}...): FAILED - {r['error']}")
    
    logger.info(f"\nTotal: {successful}/{len(accounts)} accounts scanned")
    logger.info(f"Total Credits Available: {total_credits}")
    
    return results

if __name__ == "__main__":
    asyncio.run(scan_all_accounts())
