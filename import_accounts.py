from app.database import SessionLocal
from app.models import Account
import sys

# List from user request
EMAILS = [
    "lenighhoytehalt@hotmail.com",
    "bronkirafla9lu@hotmail.com",
    "rauensdoble14x4@hotmail.com",
    "halianabaanm2f8@hotmail.com",
    "brodibdermahffk@hotmail.com",
    "vierawluker1s3m@hotmail.com",
    "baykoanaksh4bow@hotmail.com",
    "yueliqmorosw2kv07@hotmail.com",
    "paraskbeppuwuwk8t@hotmail.com",
    "zottihlicht0jkw@hotmail.com",
    "eaganzbeighnsb@hotmail.com",
    "haitzohondamb8d@hotmail.com",
    "platifimadah3zzqd@hotmail.com",
    "quailhscalo6v1@hotmail.com",
    "kocursriehsti2whd@hotmail.com",
    "stefldaldingtb@hotmail.com",
    "korinorubiafb5sc@hotmail.com",
    "perouakemme5xpzy@hotmail.com",
    "wigetidoskimxi4@hotmail.com",
    "bazuapdirircz8aa@hotmail.com"
]

PASSWORD = "Canhpk98@123"
PLATFORM = "sora"

def import_accounts():
    db = SessionLocal()
    count_added = 0
    count_skipped = 0
    
    print(f"Starting import of {len(EMAILS)} accounts...")
    
    for email in EMAILS:
        email = email.lower().strip()
        # Check if exists
        existing = db.query(Account).filter(Account.email == email).first()
        if existing:
            print(f"[SKIP] {email} already exists.")
            count_skipped += 1
            continue
        
        # Create new
        new_acc = Account(
            platform=PLATFORM,
            email=email,
            password=PASSWORD,
            status="live"
        )
        db.add(new_acc)
        print(f"[ADD] {email}")
        count_added += 1
    
    try:
        db.commit()
        print(f"\nImport Finished!")
        print(f"Added: {count_added}")
        print(f"Skipped: {count_skipped}")
    except Exception as e:
        print(f"Error committing to DB: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    import_accounts()
