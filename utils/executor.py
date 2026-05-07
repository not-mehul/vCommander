from concurrent.futures import ThreadPoolExecutor

# Shared thread pool for all async API calls across page modules.
# 4 workers covers concurrent per-item operations in commission/decommission.
_executor = ThreadPoolExecutor(max_workers=4)
