import requests
import json

BASE_URL = "http://localhost:8000/api"

accounts = [
    "lenighhoytehalt@hotmail.com",
    "bronkirafla9lu@hotmail.com",
    "rauensdoble14x4@hotmail.com",
    "halianabaanm2f8@hotmail.com",
    "brodibdermahffk@hotmail.com"
]

password = "Canhpk98@123"

def import_accounts():
    print(f"Importing {len(accounts)} accounts...")
    for email in accounts:
        payload = {
            "platform": "sora",
            "email": email,
            "password": password,
            "proxy": None # No proxy provided
        }
        try:
            response = requests.post(f"{BASE_URL}/accounts/", json=payload)
            if response.status_code == 200:
                print(f"[SUCCESS] Added {email}")
            else:
                print(f"[FAILED] Adding {email}: {response.text}")
        except Exception as e:
            print(f"[ERROR] Connection failed: {e}")

def create_test_job():
    print("\nCreating test job...")
    payload = {
        "prompt": "A serene landscape with a river flowing through a forest, cinematic lighting, 4k",
        "duration": 5,
        "aspect_ratio": "16:9"
    }
    try:
        response = requests.post(f"{BASE_URL}/jobs/", json=payload)
        if response.status_code == 200:
            print(f"[SUCCESS] Test Job created! ID: {response.json().get('id')}")
        else:
             print(f"[FAILED] Creating job: {response.text}")
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")

if __name__ == "__main__":
    import_accounts()
    create_test_job()
