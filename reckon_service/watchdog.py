import threading
import time
import os
import sys

"""
RECKON Client - Internal Watchdog
Purpose: Monitors the main service and restarts if unresponsive.
"""

class Watchdog:
    def __init__(self, timeout_seconds=120):
        self.timeout = timeout_seconds
        self.last_heartbeat = time.time()
        self.running = True
        self._lock = threading.Lock()
        self._thread = None
    
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
            time.sleep(10)  # Check every 10 seconds
            
            with self._lock:
                elapsed = time.time() - self.last_heartbeat
            
            if elapsed > self.timeout:
                print(f"[WATCHDOG] ALERT! No heartbeat for {int(elapsed)}s. Restarting...")
                self._restart_service()
    
    def _restart_service(self):
        """Restart the Python process."""
        print("[WATCHDOG] Initiating restart...")
        os.execv(sys.executable, ['python'] + sys.argv)


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
