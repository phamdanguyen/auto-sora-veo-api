class SoraSelectors:
    # Login & Auth
    LOGIN_INPUT_EMAIL = "input[type='email'], input[name='email'], input[name='username']"
    LOGIN_INPUT_PASSWORD = "input[name='Passwd'], input[name='password'], input[type='password']"
    
    LOGIN_BTN_INIT = [
        "a[href*='login']",
        "a[href*='/auth/login']", 
        "button:has-text('Log in')", 
        "div[role='button']:has-text('Log in')"
    ]
    
    LOGIN_BTN_CONTINUE = [
        "button:text-is('Continue')", 
        "button:text-is('Next')",
        "div[role='button']:text-is('Next')",
        "div[role='button']:text-is('Continue')",
        "button:has-text('Next')"
    ]
    
    LOGIN_BTN_SUBMIT = [
        "button[type='submit']", 
        "button:has-text('Log in')", 
        "button:has-text('Sign in')",
        "div[role='button']:has-text('Next')", 
        "div[role='button']:has-text('Log in')",
        "div[role='button']:has-text('Sign in')"
    ]

    # Indicators
    LOGIN_SUCCESS_INDICATOR = "button:has-text('Create')"
    ERROR_INDICATORS = [
        "div[class*='error']", 
        "text='Access denied'", 
        "text='Not found'", 
        "text='Wrong password'", 
        "text='could not find account'"
    ]
    VERIFICATION_INDICATORS = [
        "input[name='code']", 
        "input[placeholder*='code']", 
        "input[autocomplete='one-time-code']",
        "text='Enter code'",
        "text='Verify your identity'"
    ]

    # Popups & Dialogs
    POPUP_TEXTS = [
        "text='Create your character'", 
        "text='Sora mobile app'",
        "text='Download the Sora mobile app'"
    ]
    POPUP_CLOSE_BTNS = [
        "button:has-text('Close')", 
        "button[aria-label='Close']",
        "div[role='button']:has-text('Close')",
        ".lucide-x", 
        "svg.lucide-x"
    ]
    POPUP_KEYWORDS = ["Create your character", "Get the Sora mobile app", "Download the Sora mobile app", "Experience Sora on the go"]

    # Creation / Studio
    PROMPT_INPUT = [
        "textarea[placeholder*='Describe']",
        "textarea",
        "[role='textbox']",
        "div[contenteditable='true']"
    ]
    
    GENERATE_BTN = [
        "button:has-text('Generate')",
        "button:has-text('Create')",
        "button:has-text('Create Video')",
        "button[type='submit']"
    ]
    
    GENERATE_ERROR_IMMEDIATE = "text='Unable to create'"

    # Quota / Limit Errors
    QUOTA_EXHAUSTED_INDICATORS = [
        "text='You\\'re out of video gens'",
        "text='out of video gens'",
        "text='Add more now'",
        "text='wait until free access resets'",
        "text='You have reached your limit'",
        "text='generation limit'",
    ]

    # Download & Gallery
    DOWNLOAD_BTN = [
        "button[aria-label='Download']", 
        "a[download]", 
        "button:has-text('Download')",
        "div[role='button']:has-text('Download')",
        "button[data-testid='download-button']"
    ]
    
    MENU_BTN = [
        "button[aria-label='More options']", 
        "button[aria-label='Menu']", 
        ".context-menu-trigger",
        "button:has(svg.lucide-more-horizontal)" 
    ]

    # Video Completion Indicators
    VIDEO_COMPLETION_INDICATORS = [
        "text=/Your video is ready/i",
        "text=/Video generated/i",
        "text=/Generation complete/i",
        "button:has-text('Download')",
        "button:has-text('Public')",
        "button:has-text('Share')",
        "[data-state='completed']",
        ".video-ready-indicator"
    ]

    VIDEO_GENERATING_INDICATORS = [
        "text='Generating'",
        "text='Creating video'",
        "text='Processing'",
        "div[data-status='generating']",
        "div:has-text('Generating') >> visible=true"
    ]

    # Public/Share Button
    PUBLIC_BUTTON = [
        "button:has-text('Public')",
        "button:has-text('Share')",
        "button[aria-label*='public' i]",
        "button[aria-label*='share' i]",
        "div[role='button']:has-text('Public')",
        "div[role='button']:has-text('Share')"
    ]

    # Public Link Input/Display
    PUBLIC_LINK_INPUT = [
        "input[value*='sora.chatgpt.com/share']",
        "input[value*='/share/']",
        "text=/https:\\/\\/sora\\.chatgpt\\.com\\/share\\//",
        "[data-testid='share-link']",
        "input[readonly][value*='http']"
    ]

    # Copy Link Button (trong share dialog)
    COPY_LINK_BUTTON = [
        "button:has-text('Copy link')",
        "button:has-text('Copy')",
        "button[aria-label*='copy' i]"
    ]

    # Settings & Credits
    SETTINGS_MENU_ITEM = [
        "div[role='menuitem']:has-text('Settings')",
        "a[href='/settings']",
        "button:has-text('Settings')"
    ]
    
    SETTINGS_BTN_DIRECT = "button[aria-label='Settings']"
    
    USAGE_TAB = [
        "button[role='tab'][id*='trigger-usage']",  # Exact Radix structure from dump
        "[id*='trigger-usage']",                     # Fallback any element
        "button:has-text('Usage')",
    ]
    
    CREDIT_TEXT_PATTERNS = [
        r"(\d+)\s*free",                   # e.g. "9 free" - MAIN PATTERN
        r"(\d+)\s*video gens left",
        r"(\d+)\s*videos? left",
        r"(\d+)\s*gens left",
        r"(\d+)\s*/\s*\d+\s*videos?",      # e.g. "15/50 videos"
        r"Videos?\s*:\s*(\d+)",            # e.g. "Videos: 15"
        r"Remaining\s*:\s*(\d+)",
        r"(\d+)\s*remaining",
    ]
