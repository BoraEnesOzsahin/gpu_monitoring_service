import threading
import time
import os
import sys

"""
RECKON Client - Internal Watchdog
Purpose: Monitors the main service and restarts if unresponsive.
"""

class Watchdog:
    # SAFETY: Configuration constants
    MAX_TIMEOUT_MULTIPLIER = 10  # Maximum allowed timeout multiplier
    STARTUP_GRACE_PERIOD_SECONDS = 60  # Grace period for initialization
    
    def __init__(self, timeout_seconds=120):
        self.timeout = timeout_seconds
        self.last_heartbeat = time.time()
        self.running = True
        self._lock = threading.Lock()
        self._thread = None
        # SAFETY: start_time is set once during __init__ and only read afterward
        # This is thread-safe as it's written before the monitoring thread starts
        self.start_time = time.time()
    
    def start(self):
        """Start the watchdog monitoring thread."""
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()
        print(f"[WATCHDOG] Started with {self.timeout}s timeout")
    
    def feed(self):
        """Call this regularly to indicate the service is alive."""
        with self._lock:
            self.last_heartbeat = time.time()
    
    def stop(self):
        """Stop the watchdog."""
        self.running = False
    
    def _monitor(self):
        """Internal monitoring loop."""
        while self.running:
            # SAFETY: Sleep at start of loop to prevent CPU burn
            # This ensures we never spin even if time calculations fail
            time.sleep(10)  # Check every 10 seconds
            
            try:
                # SAFETY: Skip watchdog checks during startup grace period
                time_since_start = time.time() - self.start_time
                if time_since_start < self.STARTUP_GRACE_PERIOD_SECONDS:
                    print(f"[WATCHDOG] Startup grace period: {int(self.STARTUP_GRACE_PERIOD_SECONDS - time_since_start)}s remaining")
                    continue
                
                with self._lock:
                    elapsed = time.time() - self.last_heartbeat
                
                # SAFETY: Validate elapsed is reasonable (positive and not too large)
                if elapsed < 0 or elapsed > (self.timeout * self.MAX_TIMEOUT_MULTIPLIER):
                    print(f"[WATCHDOG] WARNING: Suspicious elapsed time: {elapsed}s. Resetting.")
                    with self._lock:
                        self.last_heartbeat = time.time()
                    continue
                
                if elapsed > self.timeout:
                    print(f"[WATCHDOG] ALERT! No heartbeat for {int(elapsed)}s. Restarting...")
                    self._restart_service()
            except Exception as e:
                print(f"[WATCHDOG] Error in monitor loop: {e}. Continuing...")
                # Continue monitoring even if one iteration fails
    
    def _restart_service(self):
        """Restart the Python process."""
        print("[WATCHDOG] Initiating restart...")
        
        # SAFETY: Cooldown prevents rapid restart loop
        # This ensures we don't hammer the CPU if restart keeps failing
        print("[WATCHDOG] Waiting 10 seconds before restart...")
        time.sleep(10)
        
        os.execv(sys.executable, [sys.executable] + sys.argv)


# Global watchdog instance
_watchdog = None

def init_watchdog(timeout_seconds=120):
    """Initialize and start the global watchdog."""
    global _watchdog
    _watchdog = Watchdog(timeout_seconds)
    _watchdog.start()
    return _watchdog

def feed_watchdog():
    """Feed the global watchdog (call this in your heartbeat loop)."""
    global _watchdog
    if _watchdog:
        _watchdog.feed()
