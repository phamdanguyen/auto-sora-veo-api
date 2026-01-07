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

async def test_generation():
    # Use acc_15 as profile
    email = "acc_15" 
    profile_path = os.path.abspath(f"data/profiles/{email}")
    COMMON_PASSWORD = "Canhpk98@123"
    
    if not os.path.exists(profile_path):
        logger.error(f"Profile not found: {profile_path}")
        # Try to find any profile
        profiles = [d for d in os.listdir("data/profiles") if os.path.isdir(os.path.join("data/profiles", d))]
        if profiles:
            email = profiles[0] # assume folder name is email or simple name
            if "@" not in email and "acc_" in email:
                # It's an acc_X folder, we might not know the email but login might need it? 
                # SoraDriver.login uses email for typing?
                pass
            profile_path = os.path.abspath(f"data/profiles/{email}")
            logger.info(f"Falling back to profile: {profile_path}")
        else:
            return

    logger.info(f"Testing generation for {email}")
    
    # Use headless=True for safer execution in this shell
    driver = SoraDriver(headless=False, user_data_dir=profile_path)
    
    try:
        await driver.start()
        logger.info("Driver started")
        
        # Login
        await driver.login(email, COMMON_PASSWORD)
        
        # Check login
        if not await driver.login_page.check_is_logged_in():
            logger.error("Failed to login (cookies might be expired and password failed)")
            return
            
        logger.info("Logged in successfully")
        
        # Test Prompt Submission
        prompt = "A close up of a red robot eye, 4k, cinematic lighting"
        logger.info(f"Attempting to create video with prompt: {prompt}")
        
        # We use create_video to test full cycle
        video_path = await driver.create_video(prompt)
        logger.info(f"✅ Success! Video downloaded at: {video_path}")
        
    except Exception as e:
        logger.error(f"❌ Test Failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await driver.stop()
        logger.info("Driver stopped")

if __name__ == "__main__":
    asyncio.run(test_generation())
