import logging
import asyncio
from typing import Optional
from .base import BasePage
from ..selectors import SoraSelectors
from ..exceptions import VerificationRequiredException, LoginFailedException

logger = logging.getLogger(__name__)

class SoraLoginPage(BasePage):
    
    async def login(self, email: str, password: str, base_url: str):
        """
        Executes the login flow.
        """
        logger.info(f"Navigating to {base_url}...")
        try:
            await self.page.goto(base_url, timeout=30000)
            await self._snapshot("01_login_nav")
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            # Continuing as sometimes it might already be loaded or partial load works
        
        # Check if already logged in
        if await self.check_is_logged_in():
            logger.info("Already logged in.")
            return

        # Check for Cloudflare/Challenge
        try:
             content = await self.page.content()
             if "challenge" in content.lower() or "verify you are human" in content.lower():
                 logger.warning("⚠️ Cloudflare challenge detected! Waiting for user bypass or timeout...")
                 await asyncio.sleep(10) # Give it some time
                 # We could add an explicit wait loop here if needed
        except:
             pass

        # Attempt Automated Login
        try:
            logger.info("Starting automated login flow...")
            
            # Step 1: Trigger Login (Click 'Log in' button or find email input)
            email_input_visible = await self.page.is_visible(SoraSelectors.LOGIN_INPUT_EMAIL)
            
            if not email_input_visible:
                logger.info("Email input not visible, searching for Login buttons...")
                found = await self.find_first_visible(SoraSelectors.LOGIN_BTN_INIT)
                if found:
                    sel, btn = found
                    logger.info(f"Clicking login button: {sel}")
                    await btn.click()
                    await asyncio.sleep(3)
                else:
                    logger.warning("No login button found. Using current page for login...")
                    # await self.page.goto(base_url.rstrip('/') + "/login") # No longer needed with direct URL
                    await asyncio.sleep(2)

            # Step 2: Enter Email
            # The auth page might use name="username" or id="username"
            await self.page.wait_for_selector(SoraSelectors.LOGIN_INPUT_EMAIL, timeout=10000)
            
            # Find the visible email input
            email_el = await self.page.wait_for_selector(SoraSelectors.LOGIN_INPUT_EMAIL)
            if email_el:
                 await email_el.click()
                 await self.human_type(SoraSelectors.LOGIN_INPUT_EMAIL, email)
                 logger.info(f"Filled email: {email}")
            else:
                 raise Exception("Email input found but not interactable")
            
            # Step 3: Click Continue/Next
            found_cont = await self.find_first_visible(SoraSelectors.LOGIN_BTN_CONTINUE)
            if found_cont:
                _, btn = found_cont
                await btn.click()
                await asyncio.sleep(5)
                
                # Double check if still visible (sometimes first click is ignored)
                if await btn.is_visible():
                     await btn.click()
                     await asyncio.sleep(5)
            else:
                logger.warning("Continue button not found, pressing Enter")
                await self.page.press(SoraSelectors.LOGIN_INPUT_EMAIL, "Enter")
                await asyncio.sleep(5)

            # Step 4: Enter Password
            pass_sel = SoraSelectors.LOGIN_INPUT_PASSWORD
            # Handle list of selectors split by comma for playwright locator if needed, or iterate
            # SoraSelectors.LOGIN_INPUT_PASSWORD is a string with commas, which query_selector supports directly? 
            # Actually standard CSS doesn't support comma in simple 'input[name=x], input[name=y]' for all methods
            # But Playwright wait_for_selector DOES support comma separated list.
            
            try:
                await self.page.wait_for_selector(pass_sel, timeout=10000)
                await self.page.fill(pass_sel, password)
                logger.info("Filled password.")
            except:
                logger.warning("Password field not found immediately. Pressing global Enter to retry...")
                await self.page.keyboard.press("Enter")
                await asyncio.sleep(3)
                if await self.page.is_visible(pass_sel):
                     await self.page.fill(pass_sel, password)

            # Step 5: Submit
            found_sub = await self.find_first_visible(SoraSelectors.LOGIN_BTN_SUBMIT)
            if found_sub:
                _, btn = found_sub
                await btn.click()
                logger.info("Clicked submit credentials.")
                await asyncio.sleep(8)
            else:
                logger.warning("Submit button not found!")

        except Exception as e:
            logger.error(f"Automated login encountered error: {e}")
            await self._snapshot("login_auto_error")
        
        # Verified Logged In
        if await self.check_is_logged_in():
            logger.info("Login Successful!")
        else:
            await self.check_login_errors()
            await self.manual_login_fallback()

    async def check_is_logged_in(self) -> bool:
        try:
            # 1. Check URL
            url = self.page.url
            if "/login" in url or "/auth" in url:
                return False
                
            # 2. Check for "Create" button which appears in studio
            visible = await self.page.is_visible(SoraSelectors.LOGIN_SUCCESS_INDICATOR, timeout=2000)
            if visible: 
                return True
                
            # 3. Check for specific user elements (Avatar/Profile) or Prompt Input
            # If we see a textarea and simple URL, likely logged in
            if await self.page.is_visible("textarea"):
                 logger.info("Found textarea, assuming logged in.")
                 return True
            
            return False
        except:
            return False

    async def check_login_errors(self):
        for ind in SoraSelectors.ERROR_INDICATORS:
            if await self.page.is_visible(ind):
                await self._snapshot("login_error_page")
                raise Exception(f"Login Failed: Error page detected ({ind})")
        
        for ind in SoraSelectors.VERIFICATION_INDICATORS:
            if await self.page.is_visible(ind):
                 await self._snapshot("login_verification_needed")
                 raise VerificationRequiredException("Login Failed: Verification Code / 2FA Required")

    async def manual_login_fallback(self):
        logger.info("Initiating Manual Fallback - Waiting for user to login...")
        
        # Wait up to 120 seconds (increased from 60)
        max_wait = 120 
        check_interval = 5
        
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < max_wait:
            remaining = int(max_wait - (asyncio.get_event_loop().time() - start_time))
            if remaining % 20 == 0:
                 logger.info(f"Still waiting for manual login... ({remaining}s remaining)")
            
            if await self.check_is_logged_in():
                logger.info("Manual Login Verified Success!")
                return
                
            await asyncio.sleep(check_interval)

        raise Exception("Login Timeout: User did not login manually.")
