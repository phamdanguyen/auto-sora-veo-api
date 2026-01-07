"""
Deep Code Review: Concurrency Analysis
Phân tích toàn bộ code để tìm các vấn đề concurrency
"""

# ============================================================
# PHÂN TÍCH CONCURRENCY ISSUES
# ============================================================

## ISSUE #1: Global Semaphore with Event Loop ❌ CRITICAL
**File**: `third_party_downloader.py:29`
**Code**:
```python
_third_party_semaphore = asyncio.Semaphore(3)
```

**Problem**:
- Semaphore được tạo ở module level khi module được import
- Nếu event loop thay đổi (ví dụ: trong tests hoặc multiple async contexts) → lỗi "attached to different loop"
- Trong production với single event loop (worker) thì OK, nhưng không portable

**Solution**:
```python
# Option 1: Lazy initialization
_third_party_semaphore = None

def get_semaphore():
    global _third_party_semaphore
    if _third_party_semaphore is None:
        _third_party_semaphore = asyncio.Semaphore(3)
    return _third_party_semaphore

# Option 2: Instance-level semaphore (Better)
class ThirdPartyDownloader:
    _semaphore = None
    _semaphore_lock = asyncio.Lock()
    
    @classmethod
    async def get_semaphore(cls):
        if cls._semaphore is None:
            async with cls._semaphore_lock:
                if cls._semaphore is None:
                    cls._semaphore = asyncio.Semaphore(3)
        return cls._semaphore
```

**Severity**: HIGH (breaks in certain contexts)
**Impact**: Tests fail, potential production issues with multiple loops
**Fix Required**: YES

---

## ISSUE #2: Filename Collision ✅ FIXED
**File**: `third_party_downloader.py:270`
**Status**: ✅ Đã fix bằng UUID

```python
# OLD (❌):
filename = f"video_{timestamp}.mp4"

# NEW (✅):
unique_id = uuid.uuid4().hex[:8]
filename = f"video_{timestamp}_{unique_id}.mp4"
```

**Verification**: Mỗi download tạo unique filename ngay cả khi cùng timestamp
**Risk**: LOW - UUID collision probability = 1 / 2^32 ≈ 0.00000002%

---

## ISSUE #3: Download Handler Race Condition ⚠️ POTENTIAL
**File**: `third_party_downloader.py:276-283`
**Code**:
```python
page.on("download", on_download)
# ... wait for download ...
page.remove_listener("download", on_download)
```

**Analysis**:
- **Q**: Nếu 2 downloads trigger cùng lúc trong 1 page thì sao?
- **A**: Mỗi worker có page riêng → không xảy ra
- **Q**: Nếu download trigger nhiều lần?
- **A**: `download_path` chỉ set 1 lần (nonlocal), lần sau overwrite → có thể mất file

**Scenario**:
```
Download 1 starts → save to video_1.mp4 → download_path = "video_1.mp4"
Download 2 starts → save to video_2.mp4 → download_path = "video_2.mp4"  # Overwrite!
Return video_2.mp4  # Lost video_1.mp4
```

**Likelihood**: VERY LOW (third-party sites chỉ trigger 1 download)
**Severity**: MEDIUM (data loss nếu xảy ra)
**Fix**: Không cần thiết (edge case quá hiếm), nhưng có thể add guard:

```python
download_path = None
download_lock = asyncio.Lock()

async def on_download(download: Download):
    nonlocal download_path
    async with download_lock:
        if download_path is not None:
            logger.warning("Multiple downloads detected, keeping first one")
            return
        # ... save logic ...
        download_path = save_path
```

---

## ISSUE #4: Directory Creation Race Condition ✅ SAFE
**File**: `third_party_downloader.py:74`
**Code**:
```python
os.makedirs(output_dir, exist_ok=True)
```

**Analysis**:
- `os.makedirs` với `exist_ok=True` là thread-safe
- Multiple processes có thể call cùng lúc → không vấn đề
- POSIX `mkdir` syscall handles this atomically

**Status**: ✅ SAFE

---

## ISSUE #5: File Write Race Condition ✅ SAFE
**File**: `third_party_downloader.py:271`  
**Code**:
```python
await download.save_as(save_path)
```

**Analysis**:
- Mỗi file có unique filename (timestamp + UUID) → không collision
- Playwright's `save_as` writes atomically
- OS handles concurrent file writes to different files

**Status**: ✅ SAFE

---

## ISSUE #6: Worker Concurrency Limits ✅ PROPERLY CONFIGURED
**File**: `worker_v2.py:23-26`
**Code**:
```python
MAX_CONCURRENT_GENERATE = 3
MAX_CONCURRENT_DOWNLOAD = 5
generate_semaphore = asyncio.Semaphore(MAX_CONCURRENT_GENERATE)
download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOAD)
```

**Analysis**:
- Worker-level semaphores limit concurrent tasks ✅
- Generate: max 3 concurrent (limited by accounts)
- Download: max 5 concurrent

**Potential Issue**: 
- Download semaphore = 5
- Third-party semaphore = 3
- → 2 workers sẽ bị block chờ third-party semaphore

**Recommendation**: 
```python
MAX_CONCURRENT_DOWNLOAD = 3  # Match third-party limit
```

**Severity**: LOW (performance suboptimal, not correctness issue)

---

## ISSUE #7: Driver/Page Isolation ✅ SAFE
**File**: `worker_v2.py:70-77`
**Code**:
```python
driver = SoraDriver(
    headless=False,
    proxy=account.proxy,
    user_data_dir=profile_path
)
await driver.start()  # Creates new browser context
```

**Analysis**:
- Mỗi task tạo driver mới
- Mỗi driver có browser context riêng
- Mỗi context có page riêng
- Không share state giữa workers

**Status**: ✅ PERFECTLY ISOLATED

---

## ISSUE #8: Retry Logic Thread Safety ✅ SAFE
**File**: `worker_v2.py:83-118`
**Code**:
```python
result = None
retry_public_count = 0
while not result and retry_public_count <= max_retry_public:
    try:
        result = await driver.create_video(...)
    except PublicLinkNotFoundException:
        retry_public_count += 1
        ...
```

**Analysis**:
- Local variables (`result`, `retry_public_count`) → thread-safe
- No shared state between workers
- Each worker has own stack

**Status**: ✅ SAFE

---

## ISSUE #9: Job/Database Updates ⚠️ NEEDS REVIEW
**File**: `worker_v2.py:120-130`
**Code**:
```python
await task_manager.complete_generate(job, ...)
await task_manager.complete_download(job, ...)
db.commit()
```

**Analysis**: Cần check `task_manager` implementation

**Questions**:
1. Database transactions có được handle đúng không?
2. Có lock row khi update không?
3. Multiple workers update cùng job → race condition?

**Action**: Review `task_manager.py`

---

# ============================================================
# SUMMARY & RECOMMENDATIONS
# ============================================================

## Critical Issues (Cần Fix Ngay)
1. ❌ **Global Semaphore Event Loop Issue** → Fix by lazy init or class-level

## Medium Issues (Nên Fix)
2. ⚠️ **MAX_CONCURRENT_DOWNLOAD mismatch** → Giảm từ 5 xuống 3

## Low Priority (Edge Cases)
3. ⚠️ **Multiple download handler** → Hiếm, có thể bỏ qua

## Already Fixed ✅
4. ✅ **Filename collision** → Fixed with UUID
5. ✅ **Directory creation** → Safe with exist_ok
6. ✅ **Driver isolation** → Perfect
7. ✅ **Retry logic** → Safe

## Needs Further Review
8. ⚠️ **Database/Task Manager** → Cần review task_manager.py

---

# RECOMMENDED FIXES

## Fix #1: Global Semaphore (CRITICAL)
```python
# In third_party_downloader.py

class ThirdPartyDownloader:
    _semaphore_lock = None
    _semaphore = None
    
    def __init__(self):
        self.services = [...]
        # Lazy init semaphore
        if ThirdPartyDownloader._semaphore is None:
            ThirdPartyDownloader._semaphore = asyncio.Semaphore(3)
    
    async def download_from_public_link(self, ...):
        async with ThirdPartyDownloader._semaphore:
            # ... rest of code
```

## Fix #2: Worker Download Limit
```python
# In worker_v2.py
MAX_CONCURRENT_DOWNLOAD = 3  # Was 5, reduce to match third-party limit
```

---

# FINAL VERDICT

**Overall Concurrency Safety**: 85/100

**Breakdown**:
- ✅ Core logic: SAFE (driver isolation, filename uniqueness)
- ❌ Infrastructure: NEEDS FIX (global semaphore)
- ⚠️ Optimization: SUBOPTIMAL (worker limits mismatch)
- ❓ Database: UNKNOWN (needs review)

**Action Items**:
1. Fix global semaphore → lazy initialization
2. Adjust MAX_CONCURRENT_DOWNLOAD = 3
3. Review task_manager.py for database race conditions
4. Re-run tests after fixes
