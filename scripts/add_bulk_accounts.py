from app.database import SessionLocal
from app.models import Account
from app.core.security import encrypt_password

def add_accounts():
    db = SessionLocal()
    
    accounts_data = [
        "zidelhsilmi1z3y@hotmail.com",
        "dantombroek24xv@hotmail.com",
        "guelixdoris1cr@hotmail.com",
        "reinabeigelsz0@hotmail.com",
        "rubeliogdon8g45qu@hotmail.com"
    ]
    
    default_password = "Canhpk98@123"
    
    print(f"Adding {len(accounts_data)} accounts...")
    
    for email in accounts_data:
        # Check if exists
        existing = db.query(Account).filter(Account.email == email).first()
        if existing:
            print(f"Skip existing: {email}")
            continue
            
        new_account = Account(
            platform="sora",
            email=email,
            password=encrypt_password(default_password),
            status="live",
            proxy=None, # User didn't provide proxy, assuming none or default handling
            credits_remaining=0 
        )
        db.add(new_account)
        print(f"Added: {email}")
        
    db.commit()
    db.close()
    print("Done.")

if __name__ == "__main__":
    add_accounts()
