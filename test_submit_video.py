import asyncio
import logging
import os
import sys

# Add project root
sys.path.append(os.getcwd())

from app.core.drivers.sora.driver import SoraDriver

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

async def test_submit_video():
    # Use acc_15_test as profile
    email = "acc_15_test" 
    profile_path = os.path.abspath(f"data/profiles/{email}")
    COMMON_PASSWORD = "Canhpk98@123"
    
    if not os.path.exists(profile_path):
        logger.error(f"Profile not found: {profile_path}")
        # Try to find any profile
        profiles = [d for d in os.listdir("data/profiles") if os.path.isdir(os.path.join("data/profiles", d))]
        if profiles:
            email = profiles[0] # assume folder name is email or simple name
            if "@" not in email and "acc_" in email:
                pass
            profile_path = os.path.abspath(f"data/profiles/{email}")
            logger.info(f"Falling back to profile: {profile_path}")
        else:
            logger.error("No profiles found to test with.")
            return

    logger.info(f"Testing submit_video for {email}")
    
    # Use headless=False to see what's happening if possible, or True if on server
    # Since user is on Linux with X forwarding or potential headless, let's try headless=True first if we can't see it, 
    # but existing script used headless=False.
    driver = SoraDriver(headless=False, user_data_dir=profile_path)
    
    try:
        await driver.start()
        logger.info("Driver started")
        
        # Login
        await driver.login(email, COMMON_PASSWORD)
        
        # Check login
        if not await driver.login_page.check_is_logged_in():
            logger.error("Failed to login (cookies might be expired and password failed)")
            # Try to continue primarily to test logic even if login check fails? No, useless.
            return
            
        logger.info("Logged in successfully. Preparing to submit video...")
        
        # Test Prompt Submission
        prompt = "A close up of a futuristic circuit board, glowing blue lines, macro shot"
        logger.info(f"Prompt: {prompt}")
        
        logger.info("Calling submit_video()...")
        result = await driver.submit_video(prompt)
        
        logger.info("submit_video() returned:")
        logger.info(result)
        
        if result["submitted"]:
            logger.info("✅ TEST PASSED: Video submission was verified (credits dropped or visual confirmation).")
        else:
            logger.error("❌ TEST FAILED: Video submission returned false.")

    except Exception as e:
        logger.error(f"❌ Test Exception: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await driver.stop()
        logger.info("Driver stopped")

if __name__ == "__main__":
    asyncio.run(test_submit_video())
