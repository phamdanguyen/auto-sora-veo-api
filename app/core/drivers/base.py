from playwright.async_api import async_playwright, BrowserContext, Page
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class BaseDriver:
    def __init__(self, headless: bool = True, proxy: Optional[str] = None, user_data_dir: Optional[str] = None):
        self.headless = headless
        self.proxy = proxy
        self.user_data_dir = user_data_dir
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def start(self):
        self.playwright = await async_playwright().start()
        
        proxy_config = None
        if self.proxy:
            # Parse proxy string ip:port:user:pass
            parts = self.proxy.split(':')
            if len(parts) == 4:
                proxy_config = {
                    "server": f"http://{parts[0]}:{parts[1]}",
                    "username": parts[2],
                    "password": parts[3]
                }
            elif len(parts) == 2:
                 proxy_config = {
                    "server": f"http://{parts[0]}:{parts[1]}"
                }

        # Launch args to bypass simple detection
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--disable-gpu",
        ]
        
        # Use provided profile dir or default global one (not recommended for multi-account)
        # Better default: If None, use a TEMP directory so it is fresh every time? 
        # But for persistent bot, usually we want persistence.
        profile_path = self.user_data_dir if self.user_data_dir else "./data/browser_profile"
        print(f"DEBUG: Launching Browser with Profile Path: {profile_path}")
        logger.info(f"Launching Browser with Profile Path: {profile_path}")
        
        import os
        if not os.path.exists(profile_path):
            os.makedirs(profile_path)

        # Use launch_persistent_context for better stealth (closer to real user profile)
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=self.headless,
            args=args,
            ignore_default_args=["--enable-automation"],
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
            proxy=proxy_config,
            permissions=["geolocation"],
            geolocation={"latitude": 40.7128, "longitude": -74.0060}, # NY
            color_scheme="dark",
            viewport={"width": 1280, "height": 720}
        )
        
        # In persistent context, the browser is managed by the context
        self.browser = None 
        
        pages = self.context.pages
        if pages:
            self.page = pages[0]
        else:
            self.page = await self.context.new_page()
            
        # Additional stealth script - Safe Check
        await self.page.add_init_script("""
            if (Object.getOwnPropertyDescriptor(navigator, 'webdriver') === undefined) {
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            }
        """)

    async def stop(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def save_storage_state(self, path: str):
        if self.context:
            await self.context.storage_state(path=path)

    async def load_storage_state(self, path: str):
        # Note: Context must be created with storage_state, so this might need refactoring 
        # to be passed in start() or we create a new context.
        pass
