import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from app.core.drivers.sora.driver import SoraDriver
from app.core.drivers.sora.pages.creation import SoraCreationPage

async def test_driver():
    print("🚀 Starting Manual Driver Test...")
    
    # Use headful mode to see what's happening
    driver = SoraDriver(headless=False) 
    
    try:
        await driver.start()
        print("✅ Browser started")
        
        # Test 1: Navigation & Login Check
        print("\nTesting Navigation...")
        # Direct Login URL as requested
        login_url = "https://chatgpt.com/auth/login?next=%2Fsora%2F"
        await driver.page.goto(login_url)
        print(f"Navigated to: {login_url}")
        
        await asyncio.sleep(5)
        
        is_logged_in = await driver.login_page.check_is_logged_in()
        print(f"Login Status: {'LOGGED IN' if is_logged_in else 'NOT LOGGED IN'}")
        
        if not is_logged_in:
            print("⚠️ Please login manually in the browser window within 60 seconds...")
            # Wait for manual login
            try:
                await driver.login_page.manual_login_fallback()
                print("✅ Manual login detected!")
            except Exception as e:
                print(f"❌ Login timeout: {e}")
                return

        # Test 1.5: Check Credits (New Feature)
        print("\nTesting Credit Check...")
        credits = await driver.check_credits()
        print(f"💰 Credits Remaining: {credits}")
        
        # Test 2: Prompt Filling (Human Type)
        print("\nTesting Prompt Filling (Human Type)...")
        prompt = "A futuristic city with flying cars and neon lights, cinematic 4k"
        
        try:
            await driver.creation_page.fill_prompt(prompt)
            print("✅ Prompt filled successfully")
            
            # Verify content
            val = await driver.page.locator("textarea").input_value()
            if val == prompt:
                print(f"✅ Comparison Matched: '{val}'")
            else:
                print(f"❌ Comparison Mismatch: Expected '{prompt}', got '{val}'")
                
        except Exception as e:
             print(f"❌ Prompt fill failed: {e}")

        # Test 3: Generate Button Check (Don't actually click to save quota if strictly testing)
        # But user asked to test flow, so we check if button is enabled
        print("\nChecking Generate Button State...")
        btn = await driver.creation_page.find_first_visible(driver.creation_page.selectors.GENERATE_BTN)
        if btn:
            _, element = btn
            is_enabled = await element.is_enabled()
            print(f"Generate Button Found: {'ENABLED' if is_enabled else 'DISABLED'}")
        else:
            print("❌ Generate button NOT found")

        print("\n✨ Test sequence completed. Closing in 5s...")
        await asyncio.sleep(5)
        
    except Exception as e:
        print(f"❌ Test Failed: {e}")
    finally:
        await driver.stop()
        print("Browser closed")

if __name__ == "__main__":
    asyncio.run(test_driver())
