import requests
import time
import json

BASE_URL = "http://localhost:8000/api"

def test_create_and_run_job():
    print("1. Creating Job...")
    payload = {
        "prompt": "A futuristic city with flying cars, cinematic lighting, 8k",
        "duration": 5,
        "aspect_ratio": "16:9"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/jobs/", json=payload)
        response.raise_for_status()
        job = response.json()
        job_id = job["id"]
        print(f"   Job created: ID #{job_id} (Status: {job['status']})")
    except Exception as e:
        print(f"❌ Failed to create job: {e}")
        return

    print("2. Starting Job (Bulk Action)...")
    start_payload = {
        "action": "start_selected",
        "job_ids": [job_id]
    }
    
    try:
        response = requests.post(f"{BASE_URL}/jobs/bulk_action", json=start_payload)
        response.raise_for_status()
        print("   Job started successfully.")
    except Exception as e:
        print(f"❌ Failed to start job: {e}")
        return

    print("3. Polling Status...")
    for i in range(10):
        try:
            r = requests.get(f"{BASE_URL}/jobs/{job_id}")
            current_job = r.json()
            status = current_job['status']
            account_id = current_job.get('account_id')
            
            print(f"   [{i}s] Status: {status}, Account: {account_id}")
            
            if status in ["processing", "completed", "failed"]:
                if account_id:
                    print(f"✅ Job picked up by account #{account_id}")
                    # check task state
                    task_state = json.loads(current_job.get('task_state', '{}'))
                    current_task = task_state.get('current_task')
                    print(f"   Current Task Step: {current_task}")
                    break
        except Exception as e:
            print(f"   Error polling: {e}")
        
        time.sleep(2)

if __name__ == "__main__":
    test_create_and_run_job()
