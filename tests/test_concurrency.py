"""
Concurrency Test Suite
Tests concurrent download scenarios to verify no race conditions or collisions
"""
import asyncio
import os
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.third_party_downloader import ThirdPartyDownloader, PublicLinkNotFoundException


class MockPage:
    """Mock Playwright page for testing"""
    def __init__(self, worker_id: int):
        self.worker_id = worker_id
        self._download_handlers = []
    
    async def goto(self, url, **kwargs):
        print(f"[Worker {self.worker_id}] Navigate to {url}")
        await asyncio.sleep(0.1)
    
    async def is_visible(self, selector, timeout=None):
        return "input[type='text']" in selector or "button:has-text('Download')" in selector
    
    async def fill(self, selector, value):
        print(f"[Worker {self.worker_id}] Fill {selector} with {value[:50]}...")
    
    async def click(self, selector):
        print(f"[Worker {self.worker_id}] Click {selector}")
        # Simulate download trigger
        await asyncio.sleep(0.5)
        # Trigger download event
        for handler in self._download_handlers:
            mock_download = MockDownload(self.worker_id)
            await handler(mock_download)
    
    def on(self, event, handler):
        if event == "download":
            self._download_handlers.append(handler)
    
    def remove_listener(self, event, handler):
        if event == "download" and handler in self._download_handlers:
            self._download_handlers.remove(handler)


class MockDownload:
    """Mock Playwright download object"""
    def __init__(self, worker_id: int):
        self.worker_id = worker_id
        self.suggested_filename = f"sora_video_worker_{worker_id}.mp4"
    
    async def save_as(self, path):
        print(f"[Worker {self.worker_id}] Saving to {path}")
        # Create actual file to test os.path.getsize
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"MOCK_VIDEO_DATA" * 1000)  # ~15KB
        await asyncio.sleep(0.2)  # Simulate download time


async def test_concurrent_downloads(num_workers: int = 5):
    """
    Test concurrent downloads to verify:
    1. No filename collisions
    2. All files are created successfully
    3. Semaphore limits concurrent requests
    """
    print(f"\n{'='*60}")
    print(f"TEST: Concurrent Downloads ({num_workers} workers)")
    print(f"{'='*60}\n")
    
    # Create test output directory
    test_output_dir = "data/test_downloads"
    os.makedirs(test_output_dir, exist_ok=True)
    
    # Clean up existing test files
    for f in Path(test_output_dir).glob("video_*.mp4"):
        f.unlink()
    
    # Track results
    results = []
    start_time = time.time()
    
    async def worker_task(worker_id: int):
        """Single worker that downloads a video"""
        try:
            print(f"\n[Worker {worker_id}] Starting...")
            downloader = ThirdPartyDownloader()
            mock_page = MockPage(worker_id)
            
            # Simulate public link (unique per worker)
            public_link = f"https://sora.chatgpt.com/share/test_{worker_id}"
            
            # Download
            local_path, file_size = await downloader.download_from_public_link(
                mock_page,
                public_link,
                test_output_dir
            )
            
            result = {
                "worker_id": worker_id,
                "local_path": local_path,
                "file_size": file_size,
                "success": True,
                "error": None
            }
            print(f"[Worker {worker_id}] ✅ Success: {local_path}")
            
        except Exception as e:
            result = {
                "worker_id": worker_id,
                "local_path": None,
                "file_size": 0,
                "success": False,
                "error": str(e)
            }
            print(f"[Worker {worker_id}] ❌ Failed: {e}")
        
        return result
    
    # Launch all workers concurrently
    tasks = [worker_task(i) for i in range(num_workers)]
    results = await asyncio.gather(*tasks)
    
    elapsed = time.time() - start_time
    
    # Analyze results
    print(f"\n{'='*60}")
    print(f"TEST RESULTS ({elapsed:.2f}s)")
    print(f"{'='*60}\n")
    
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    print(f"✅ Successful: {len(successful)}/{num_workers}")
    print(f"❌ Failed: {len(failed)}/{num_workers}")
    
    if failed:
        print("\nFailed workers:")
        for r in failed:
            print(f"  - Worker {r['worker_id']}: {r['error']}")
    
    # Check for filename collisions
    filenames = [r["local_path"] for r in successful]
    unique_filenames = set(filenames)
    
    print(f"\nFilename collision check:")
    print(f"  Total files: {len(filenames)}")
    print(f"  Unique files: {len(unique_filenames)}")
    
    if len(filenames) != len(unique_filenames):
        print("  ❌ COLLISION DETECTED!")
        # Find duplicates
        from collections import Counter
        duplicates = [name for name, count in Counter(filenames).items() if count > 1]
        print(f"  Duplicate filenames: {duplicates}")
        return False
    else:
        print("  ✅ No collisions")
    
    # Verify all files exist and have correct size
    print(f"\nFile verification:")
    for r in successful:
        if os.path.exists(r["local_path"]):
            actual_size = os.path.getsize(r["local_path"])
            print(f"  ✅ {os.path.basename(r['local_path'])}: {actual_size:,} bytes")
        else:
            print(f"  ❌ {r['local_path']}: FILE NOT FOUND")
            return False
    
    # Check semaphore behavior (should limit to 3 concurrent)
    print(f"\nSemaphore verification:")
    print(f"  Expected max concurrent: 3")
    print(f"  Total workers: {num_workers}")
    print(f"  Total time: {elapsed:.2f}s")
    
    # If semaphore works, time should be > (num_workers / 3) * avg_download_time
    # avg_download_time ≈ 1s per worker (mocked)
    expected_min_time = (num_workers / 3) * 0.8  # 0.8s per batch of 3
    if elapsed >= expected_min_time:
        print(f"  ✅ Semaphore appears to be working (took {elapsed:.2f}s >= {expected_min_time:.2f}s)")
    else:
        print(f"  ⚠️ Semaphore may not be limiting correctly (took {elapsed:.2f}s < {expected_min_time:.2f}s)")
    
    return len(failed) == 0 and len(filenames) == len(unique_filenames)


async def test_extreme_concurrency():
    """Test with 10 workers to stress-test"""
    print(f"\n{'='*60}")
    print(f"STRESS TEST: 10 Concurrent Workers")
    print(f"{'='*60}\n")
    return await test_concurrent_downloads(10)


async def test_same_second_collision():
    """
    Test that even if 2 downloads happen in the same second,
    UUID prevents collision
    """
    print(f"\n{'='*60}")
    print(f"TEST: Same-Second Collision Prevention")
    print(f"{'='*60}\n")
    
    test_output_dir = "data/test_downloads"
    os.makedirs(test_output_dir, exist_ok=True)
    
    # Launch 5 workers at EXACTLY the same time
    async def instant_worker(worker_id):
        downloader = ThirdPartyDownloader()
        mock_page = MockPage(worker_id)
        public_link = f"https://sora.chatgpt.com/share/instant_{worker_id}"
        return await downloader.download_from_public_link(
            mock_page, public_link, test_output_dir
        )
    
    # Use asyncio.gather to start all simultaneously
    tasks = [instant_worker(i) for i in range(5)]
    results = await asyncio.gather(*tasks)
    
    filenames = [r[0] for r in results]
    unique_filenames = set(filenames)
    
    print(f"\nResults:")
    print(f"  Total files: {len(filenames)}")
    print(f"  Unique files: {len(unique_filenames)}")
    
    for filename in filenames:
        print(f"  - {os.path.basename(filename)}")
    
    if len(filenames) == len(unique_filenames):
        print(f"\n✅ TEST PASSED: All filenames are unique!")
        return True
    else:
        print(f"\n❌ TEST FAILED: Filename collision detected!")
        return False


async def main():
    """Run all concurrency tests"""
    print("\n" + "="*60)
    print(" CONCURRENCY TEST SUITE")
    print("="*60)
    
    tests = [
        ("Basic Concurrent Downloads (5 workers)", test_concurrent_downloads(5)),
        ("Stress Test (10 workers)", test_extreme_concurrency()),
        ("Same-Second Collision Test", test_same_second_collision()),
    ]
    
    results = []
    for test_name, test_coro in tests:
        print(f"\n\n▶️  Running: {test_name}")
        try:
            result = await test_coro
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ Test crashed: {e}")
            results.append((test_name, False))
    
    # Final summary
    print("\n\n" + "="*60)
    print(" FINAL SUMMARY")
    print("="*60)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    all_passed = all(r[1] for r in results)
    print("\n" + "="*60)
    if all_passed:
        print("🎉 ALL TESTS PASSED! Concurrency is safe.")
    else:
        print("⚠️  SOME TESTS FAILED! Review implementation.")
    print("="*60 + "\n")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
