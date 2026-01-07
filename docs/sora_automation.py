import asyncio
import os
import sys
import logging

# Add project root to path to allow importing app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.drivers.sora.driver import SoraDriver

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("automation.log")
    ]
)
logger = logging.getLogger(__name__)

# Constants
INPUT_FILE = "emails.txt"
OUTPUT_FILE = "valid_accounts.txt"
CREDITS_FILE = "credits.txt"
COMMON_PASSWORD = "Canhpk98@123"

async def process_accounts():
    # Read emails
    if not os.path.exists(INPUT_FILE):
        logger.error(f"Input file {INPUT_FILE} not found!")
        return

    with open(INPUT_FILE, 'r') as f:
        emails = [line.strip() for line in f if line.strip()]

    # Load existing processed
    processed = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r') as f:
            processed = set(line.strip() for line in f)

    logger.info(f"Loaded {len(emails)} accounts. Already processed: {len(processed)}")

    # Initialize Driver (Headful for local execution)
    # Note: SoraDriver handles browser lifecycle internally usually, but we might want to keep it open or restart per account?
    # The driver.start() creates a new context. To share browser we might need to adjust, but safer to restart per account to avoid stale sessions.
    
    for i, email in enumerate(emails):
        if email in processed:
            continue

        logger.info(f"Processing [{i+1}/{len(emails)}]: {email}")
        
        driver = SoraDriver(headless=False, user_data_dir=f"data/profiles/{email}")
        
        try:
            # Login
            cookies = await driver.login(email=email, password=COMMON_PASSWORD)
            
            # Check Credits
            credits = await driver.check_credits()
            
            if credits != -1:
                logger.info(f"✅ Success: {email} | Credits: {credits}")
                
                # Save to Valid
                with open(OUTPUT_FILE, "a") as f:
                    f.write(f"{email}\n")
                
                # Save to Credits
                with open(CREDITS_FILE, "a") as f:
                    f.write(f"{email}|{credits}\n")
            else:
                logger.warning(f"⚠️ Logged in but could not determine credits for {email}")
                # Still count as valid login? Maybe.
                with open(OUTPUT_FILE, "a") as f:
                    f.write(f"{email}\n")

        except Exception as e:
            logger.error(f"❌ Failed {email}: {e}")
            # Do not add to valid
            
        finally:
            await driver.stop()
            await asyncio.sleep(2) # Cooldown

if __name__ == "__main__":
    try:
        asyncio.run(process_accounts())
    except KeyboardInterrupt:
        logger.info("Automation stopped by user.")
