import logging
import asyncio
import sys
from .base import BasePage
from ..selectors import SoraSelectors
from ..exceptions import QuotaExhaustedException

logger = logging.getLogger(__name__)

class SoraCreationPage(BasePage):
    
    async def handle_blocking_popups(self):
        """
        Aggressively closes known blocking popups.
        """
        # CSS/JS Suppression
        await self._suppress_popups_js()
        
        # Check specific popup text
        for txt_ind in SoraSelectors.POPUP_TEXTS:
            if await self.page.is_visible(txt_ind, timeout=1000):
                logger.info(f"Popup detected ({txt_ind}). Attempting to close...")
                
                # Try close buttons
                found = await self.find_first_visible(SoraSelectors.POPUP_CLOSE_BTNS)
                if found:
                    _, btn = found
                    await btn.click()
                    await asyncio.sleep(1)
                else:
                    # Click outside or Escape
                    await self.page.keyboard.press("Escape")
    
    async def _suppress_popups_js(self):
        try:
            # We inject keywords to nuke elements containing them
            js_code = """(keywords) => {
                try {
                    function nuke(text) {
                        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
                        let node;
                        while (node = walker.nextNode()) {
                            if (node.textContent.includes(text)) {
                                let current = node.parentElement;
                                let depth = 0;
                                while (current && depth < 10) {
                                    const style = window.getComputedStyle(current);
                                    if (style.position === 'fixed' || style.position === 'absolute' || current.getAttribute('role') === 'dialog') {
                                        console.log('Nuking popup with text:', text);
                                        current.style.display = 'none';
                                        current.style.visibility = 'hidden';
                                        // Also try to remove pointer-events to prevent blocking
                                        current.style.pointerEvents = 'none';
                                        break;
                                    }
                                    current = current.parentElement;
                                    depth++;
                                }
                            }
                        }
                    }
                    keywords.forEach(k => nuke(k));
                } catch (e) {
                     console.error("Popup nuke failed", e);
                }
            }"""
            await self.page.evaluate(js_code, SoraSelectors.POPUP_KEYWORDS)
        except Exception as e:
            logger.debug(f"JS Popup suppression benign error: {e}")

    async def human_type(self, selector: str, text: str):
        """Simulate human typing with random delays"""
        import random
        try:
            # Focus element
            await self.page.click(selector)
            
            # Clear existing content using keyboard (more robust than fill(""))
            # Mac matches 'Meta', Windows/Linux uses 'Control'
            modifier = "Meta" if sys.platform == "darwin" else "Control"
            await self.page.keyboard.press(f"{modifier}+A")
            await self.page.keyboard.press("Backspace")
            
            # Type characters with varying delays
            for char in text:
                await self.page.keyboard.type(char)
                # Random delay 20ms to 100ms
                delay = random.uniform(0.02, 0.1) 
                await asyncio.sleep(delay)
                
            return True
        except Exception as e:
            logger.warning(f"Human type failed: {e}")
            return False

    async def fill_prompt(self, prompt: str):
        logger.info("Attempting to fill prompt...")
        await self.handle_blocking_popups()
        
        found = await self.find_first_visible(SoraSelectors.PROMPT_INPUT)
        if not found:
             # Retry once with aggressive cleanup
             logger.warning("Prompt input not found initially. Retrying with popup cleanup...")
             await self.handle_blocking_popups()
             await asyncio.sleep(2)
             found = await self.find_first_visible(SoraSelectors.PROMPT_INPUT)
             
        if found:
            sel, el = found
            logger.info(f"Found prompt input: {sel}")
            
            # Use human typing for better stability and undetectability
            success = await self.human_type(sel, prompt)
            
            if not success:
                # Fallback to standard fill if human typing crashes
                logger.warning("Human typing failed, falling back to standard fill...")
                await el.fill(prompt)
            
            # Verify value
            await asyncio.sleep(0.5)
            value = await el.input_value()
            if not value:
                # Last resort fallback
                logger.warning("Input empty after typing, forcing fill...")
                await el.fill(prompt)
                
            logger.info("Prompt filled successfully.")
            
            # Wait a bit for validation to trigger
            await asyncio.sleep(1)
        else:
            await self._snapshot("no_prompt_input")
            raise Exception("Could not find prompt input field")

    async def check_quota_exhausted(self) -> bool:
        """Check if account has run out of video generations"""
        for indicator in SoraSelectors.QUOTA_EXHAUSTED_INDICATORS:
            try:
                if await self.page.is_visible(indicator, timeout=1000):
                    logger.warning(f"Quota exhausted indicator found: {indicator}")
                    return True
            except:
                continue
        return False

    async def handle_blocking_overlay(self):
        """Detect and close blocking overlays/dialogs"""
        try:
            # Common overlay selectors
            overlays = [
                ".z-dialog", 
                "[role='dialog']", 
                "div[class*='overlay']",
                "div[class*='modal']"
            ]
            
            for selector in overlays:
                if await self.page.is_visible(selector, timeout=500):
                    logger.warning(f"Blocking overlay detected: {selector}")
                    await self._snapshot("blocking_overlay_detected")
                    
                    # Try to get text content to understand what it is
                    try:
                        el = await self.page.query_selector(selector)
                        text = await el.text_content()
                        logger.info(f"Overlay text: {text[:100]}...")
                    except:
                        pass

                    # Attempt 1: Press Escape
                    logger.info("Attempting to close overlay via Escape key...")
                    await self.page.keyboard.press("Escape")
                    await asyncio.sleep(1)
                    
                    if not await self.page.is_visible(selector, timeout=500):
                        logger.info("Overlay closed via Escape.")
                        return

                    # Attempt 2: Click Close button
                    close_btns = [
                        f"{selector} button[aria-label='Close']",
                        f"{selector} button:has-text('Close')",
                        f"{selector} button:has-text('Maybe later')",
                        f"{selector} button:has-text('X')",
                        "button[class*='close']"
                    ]
                    
                    for btn_sel in close_btns:
                        if await self.click_if_visible(btn_sel):
                            logger.info(f"Clicked close button: {btn_sel}")
                            await asyncio.sleep(1)
                            if not await self.page.is_visible(selector, timeout=500):
                                return

                    logger.warning("Failed to dismiss overlay.")
                    await self._snapshot("overlay_dismiss_fail")
        except Exception as e:
            logger.warning(f"Error handling overlay: {e}")

    async def check_is_generating(self) -> bool:
        """
        Check if any video is currently generating/processing in the list.
        Returns true if indicators found.
        """
        try:
            for ind in SoraSelectors.VIDEO_GENERATING_INDICATORS:
                if await self.page.is_visible(ind, timeout=1000):
                    logger.info(f"✅ Found generating video indicator: {ind}")
                    return True
        except Exception as e:
            logger.debug(f"Generation check failed (benign): {e}")
        return False

    async def click_generate(self, prompt: str = "") -> bool:
        """
        Robustly click Generate button:
        1. Handle blocking overlays
        2. Try Enter Key
        3. Fallback to Click
        
        Returns:
            bool: True if submission was successful (based on UI state change), False otherwise.
        """
        await self.handle_blocking_popups()

        # Check quota BEFORE clicking
        if await self.check_quota_exhausted():
            await self._snapshot("quota_exhausted_before_generate")
            raise QuotaExhaustedException("Account has exhausted video generation quota")

        # 0. Handle potential blocking overlays first
        await self.handle_blocking_overlay()

        found = await self.find_first_visible(SoraSelectors.GENERATE_BTN)
        if found:
            _, btn = found
            
            # Debug: Snapshot before starting
            await self._snapshot("debug_before_submission")

            # Wait for button to be enabled
            if await btn.is_disabled():
                logger.info("Generate button is disabled, waiting...")
                try:
                    # Wait up to 10s for it to become enabled (e.g. valid prompt)
                    await btn.wait_for_element_state("enabled", timeout=10000)
                except Exception:
                    logger.warning("Generate button remained disabled after wait.")
                    await self._snapshot("generate_btn_disabled")
                    raise Exception("Generate button is disabled (invalid prompt?)")

            # === PRIMARY METHOD: ENTER KEY ===
            logger.info("Attempting submission via ENTER key (Primary)...")
            try:
                # Focus prompt input
                prompt_input = await self.find_first_visible(SoraSelectors.PROMPT_INPUT)
                if prompt_input:
                    _, el = prompt_input
                    await el.click() # Focus
                    await asyncio.sleep(0.5)
                    await self.page.keyboard.press("Enter")
                    logger.info("Sent ENTER key.")
                    
                    # Snapshot after Enter
                    await asyncio.sleep(1)
                    await self._snapshot("debug_after_enter_1s")

                    # Verify if it worked (wait up to 5s for state change)
                    for _ in range(5):
                        await asyncio.sleep(1)
                        
                        # Check button state
                        if not await btn.is_visible():
                             logger.info("✅ ENTER key success: Generate button disappeared")
                             return True
                        
                        if await btn.is_disabled():
                             logger.info("✅ ENTER key success: Generate button disabled")
                             return True

                        # Check button text
                        btn_text = await btn.text_content()
                        if btn_text and ("generat" in btn_text.lower() or "creating" in btn_text.lower()):
                             logger.info("✅ ENTER key success: Button text changed to 'Generating'")
                             return True
                             
                    logger.warning("ENTER key did not trigger generation (no state change).")
                    await self._snapshot("debug_enter_failed")
                else:
                    logger.warning("Prompt input not found for Enter key submission.")
            except Exception as e:
                logger.warning(f"Enter key submission failed: {e}")

            # === FALLBACK METHOD: CLICKING ===
            logger.info("Falling back to Click method...")
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        logger.info(f"Retry click attempt {attempt + 1}/{max_retries}...")
                        
                    # SAFETY: Check if generation started (e.g. from previous attempt or delayed Enter)
                    if await self.check_is_generating():
                         logger.info("✅ Generation already in progress (detected indicator). Stopping retries.")
                         return True
                    
                    # Check for overlay FIRST (before finding button, as closing overlay might refresh DOM)
                    await self.handle_blocking_overlay()

                    # RE-FIND BUTTON to avoid "Element is not attached to the DOM"
                    # The button often re-renders after blocking overlays or state changes
                    found_retry = await self.find_first_visible(SoraSelectors.GENERATE_BTN)
                    if not found_retry:
                        logger.warning("Generate button not found during retry loop.")
                        continue
                    _, btn_current = found_retry
                    
                    # Check Enabled State & Prompt Integrity
                    try:
                        is_disabled = await btn_current.is_disabled()
                    except Exception as e:
                        logger.warning(f"Could not check disabled state (detached?): {e}. Assuming enabled and trying click...")
                        is_disabled = False

                    if is_disabled:
                        # CRITICAL FIX: "Disabled" often means "Generating" (Success), not "Empty Prompt" (Failure).
                        # We must differentiate.
                        
                        # 1. Check visual indicators of generation
                        if await self.check_is_generating():
                             logger.info("✅ Generation confirmed (while checking disabled button).")
                             return True
                             
                        # 2. Check button text for "Generating..."
                        try:
                            txt = await btn_current.text_content()
                            if txt and ("generating" in txt.lower() or "creating" in txt.lower() or "processing" in txt.lower()):
                                 logger.info(f"✅ Generation confirmed via button text: '{txt}'")
                                 return True
                        except:
                            pass

                        # 3. ONLY now, if we are NOT generating, check prompt
                        logger.warning(f"Generate button disabled in retry {attempt+1}. Checking if prompt is empty...")
                        
                        should_refill = False
                        if prompt:
                            # Check prompt input
                            p_found = await self.find_first_visible(SoraSelectors.PROMPT_INPUT)
                            if p_found:
                                 _, p_input = p_found
                                 val = await p_input.input_value()
                                 # If prompt is suspiciously short or empty...
                                 if not val or len(val) < 5:
                                     # CRITICAL CHANGE: Empty prompt + Disabled button usually means the system cleared it because it IS generating!
                                     # Refilling causing the "Double Generation" (write -> click -> write -> click).
                                     logger.info("✅ Generation confirmed: Prompt was cleared and button is disabled. Assuming success.")
                                     return True
                                 else:
                                     # Prompt still there? Then it's just disabled. Failed?
                                     logger.warning(f"Prompt is present ({len(val)} chars). Button disabled. NOT refilling to be safe.")
                        
                        # Wait for enable
                        try:
                            await btn_current.wait_for_element_state("enabled", timeout=5000)
                        except:
                            logger.warning("Button still disabled after wait.")

                    await btn_current.click(timeout=3000)
                    logger.info("Clicked Generate.")

                    # CRITICAL SAFETY: Post-click Wait (Increased to 10s to ensure UI updates)
                    # We MUST wait long enough for "Generating..." to appear or button to disable.
                    await asyncio.sleep(10)
                    await self._snapshot(f"debug_after_click_{attempt+1}")
                    
                    # 1. Check if ANY generation indicator appeared during wait
                    if await self.check_is_generating():
                         logger.info("✅ Generation confirmed (indicator appearing after click).")
                         return True

                    # 2. Check Immediate error
                    error_el = await self.page.query_selector("div[class*='error'], [role='alert'], .text-red-500")
                    if error_el and await error_el.is_visible():
                        text = await error_el.text_content()
                        if text and text.strip(): 
                            logger.warning(f"Error after generate: {text}")
                            await self._snapshot(f"debug_error_msg_{attempt+1}")
                            if "quota" in text.lower() or "limit" in text.lower():
                                raise QuotaExhaustedException(f"Quota exhausted: {text}")
                            # If it's a transient error, we might retry. If unknown, we fail.
                            if "unable" in text.lower() or "failed" in text.lower():
                                 pass # Retry allowed
                            else:
                                 raise Exception(f"Submission error: {text}")

                    # 3. Verify Button State
                    # If we clicked, and 10s later it's STILL enabled and NO error and NO generating text...
                    # It's suspicious. But retrying blindly causes double-generation.
                    
                    try:
                        is_disabled = await btn_current.is_disabled()
                        is_visible = await btn_current.is_visible()
                    except:
                        is_disabled = False # Assuming detached = processed? No, safest is to Assume Success if element gone
                        is_visible = False

                    if not is_visible:
                         logger.info("✅ Click success: Generate button disappeared/detached.")
                         return True
                         
                    if is_disabled:
                         logger.info("✅ Click success: Generate button became disabled.")
                         return True

                    # If here, button is Visible AND Enabled after 10s.
                    logger.warning(f"⚠️ Generate button still enabled after 10s. Text: {await btn_current.text_content()}")
                    
                    # Prevent aggressive retry if we've already done 1 retry
                    if attempt >= 1:
                        logger.warning("🛑 Stopping retries to prevent double-generation. Assuming potential silent success.")
                        return True
                    
                    logger.warning(f"Retry click attempt {attempt + 1} failed (Button active). Retrying ONE more time...")
                    
                    if not is_visible:
                         logger.info("✅ Click success: Generate button disappeared.")
                         return True
                         
                    if is_disabled:
                         logger.info("✅ Click success: Generate button became disabled.")
                         return True

                    btn_text = await btn_current.text_content()
                    if btn_text and ("generat" in btn_text.lower() or "creating" in btn_text.lower()):
                         logger.info("✅ Click success: Button text changed.")
                         return True

                    logger.warning(f"Generate button still enabled and visible attempt {attempt+1}. Click might have failed.")
                    
                except QuotaExhaustedException:
                    raise
                except Exception as e:
                    logger.warning(f"Click attempt {attempt + 1} failed: {e}")
                
                await asyncio.sleep(1)
                
            await self._snapshot("debug_final_failure")
            raise Exception("Failed to submit video request after multiple attempts (Enter + Clicks)")
            
        else:
            await self._snapshot("debug_no_gen_btn")
            raise Exception("Generate button not found")

    async def wait_for_video_completion(self, max_wait: int = 300) -> bool:
        """
        Wait for video generation to complete by checking UI indicators
        
        Args:
            max_wait: Maximum seconds to wait
            
        Returns:
            bool: True if video completed, False if timeout
        """
        logger.info(f"Waiting for video completion (max {max_wait}s)...")
        start_time = asyncio.get_event_loop().time()
        
        check_interval = 4  # Check every 4 seconds
        
        while (asyncio.get_event_loop().time() - start_time) < max_wait:
            # Check for completion indicators
            for indicator in SoraSelectors.VIDEO_COMPLETION_INDICATORS:
                try:
                    if await self.page.is_visible(indicator, timeout=1000):
                        logger.info(f"✅ Video completion detected: {indicator}")
                        return True
                except:
                    continue
            
            await asyncio.sleep(check_interval)
        
        logger.warning(f"⏱️ Video completion timeout after {max_wait}s")
        return False

    async def get_public_link(self) -> str:
        """
        Click Public/Share button and retrieve the public link
        
        Returns:
            str: Public link (e.g., https://sora.chatgpt.com/share/xxx)
            
        Raises:
            PublicLinkNotFoundException: If public button not found or link not retrieved
        """
        from ..third_party_downloader import PublicLinkNotFoundException
        
        logger.info("Attempting to get public link...")
        
        # Close any blocking popups first
        await self.handle_blocking_popups()
        
        # Find and click Public/Share button
        found = await self.find_first_visible(SoraSelectors.PUBLIC_BUTTON)
        if not found:
            await self._snapshot("public_button_not_found")
            raise PublicLinkNotFoundException("Public/Share button not found")
        
        _, btn = found
        await btn.click()
        logger.info("Clicked Public/Share button")
        
        # Wait for share dialog to appear
        await asyncio.sleep(2)
        
        # Try to find the public link in various ways
        public_link = None
        
        # Method 1: Look for input field with link
        for selector in SoraSelectors.PUBLIC_LINK_INPUT:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    value = await element.get_attribute("value")
                    if value and "/share/" in value:
                        public_link = value
                        logger.info(f"Found public link in input: {public_link}")
                        break
            except:
                continue
        
        # Method 2: Look for text containing the link
        if not public_link:
            try:
                # Get all text content
                page_content = await self.page.content()
                import re
                match = re.search(r'https://sora\.chatgpt\.com/share/[a-zA-Z0-9-]+', page_content)
                if match:
                    public_link = match.group(0)
                    logger.info(f"Found public link in page content: {public_link}")
            except Exception as e:
                logger.debug(f"Regex search failed: {e}")
        
        # Method 3: Try to copy from clipboard (if copy button exists)
        if not public_link:
            try:
                copy_btn_found = await self.find_first_visible(SoraSelectors.COPY_LINK_BUTTON)
                if copy_btn_found:
                    _, copy_btn = copy_btn_found
                    await copy_btn.click()
                    await asyncio.sleep(1)
                    
                    # Try to get clipboard content (platform specific)
                    clipboard_text = await self.page.evaluate("""
                        async () => {
                            try {
                                return await navigator.clipboard.readText();
                            } catch (e) {
                                return null;
                            }
                        }
                    """)
                    
                    if clipboard_text and "/share/" in clipboard_text:
                        public_link = clipboard_text
                        logger.info(f"Found public link from clipboard: {public_link}")
            except Exception as e:
                logger.debug(f"Clipboard method failed: {e}")
        
        if not public_link:
            await self._snapshot("public_link_not_found")
            raise PublicLinkNotFoundException("Could not retrieve public link from UI")
        
        if not public_link:
            await self._snapshot("public_link_not_found")
            raise PublicLinkNotFoundException("Could not retrieve public link from UI")
        
        return public_link.strip()

    async def check_credits(self) -> int:
        """
        Check available video credits by navigating to settings or scanning page.
        Returns:
            int: Number of credits remaining, or -1 if could not determine.
        """
        import re
        logger.info("Checking credits...")
        
        credits = -1
        
        # Method 1: Check via Settings UI (Proven flow from test_direct.py)
        try:
             # Step 1: Click Settings button
             logger.info("Clicking Settings button...")
             await self.page.click("button[aria-label='Settings']")
             await asyncio.sleep(2)
             
             # Step 2: Click Settings menu item inside dropdown
             logger.info("Clicking Settings menu item...")
             await self.page.click("div[role='menuitem']:has-text('Settings')")
             await asyncio.sleep(3)
             
             # Step 3: Click Usage tab
             logger.info("Clicking Usage tab...")
             usage_btn = await self.page.query_selector("button[role='tab'][id*='trigger-usage']")
             if usage_btn:
                 await usage_btn.click()
                 await asyncio.sleep(2)
             else:
                 # Fallback: text match
                 await self.page.click("button:has-text('Usage')")
                 await asyncio.sleep(2)
             
             # Step 4: Get page content and search for credits
             content = await self.page.content()
             
             # Scan for patterns (prioritize "N free" pattern)
             for pattern in SoraSelectors.CREDIT_TEXT_PATTERNS:
                 match = re.search(pattern, content, re.IGNORECASE)
                 if match:
                     credits = int(match.group(1))
                     logger.info(f"💰 Found credits UI: {credits}")
                     break
                     
             # Close dialog
             await self.page.keyboard.press("Escape")
             await asyncio.sleep(0.5)
             
        except Exception as e:
            logger.warning(f"UI Credit check failed: {e}")
            
        # Method 2: Direct URL Fallback (as per automation script)
        if credits == -1:
            try:
                logger.info("Trying direct Settings URL...")
                # Open new tab or reuse? Reuse is safer for session
                await self.page.goto("https://sora.chatgpt.com/settings")
                await asyncio.sleep(3)
                
                content = await self.page.content()
                for pattern in SoraSelectors.CREDIT_TEXT_PATTERNS:
                     match = re.search(pattern, content, re.IGNORECASE)
                     if match:
                         credits = int(match.group(1))
                         logger.info(f"💰 Found credits DirectURL: {credits}")
                         break
                         
                # Go back to home
                await self.page.goto("https://sora.chatgpt.com")
                
            except Exception as e:
                 logger.error(f"Direct URL Credit check failed: {e}")

        if credits == -1:
            logger.warning("Could not determine credits.")
            
        return credits
