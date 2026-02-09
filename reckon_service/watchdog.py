import threading
import time
import os
import sys
import signal

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
        self._shutdown_in_progress = False
    
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
        """Stop the watchdog. Safe to call multiple times."""
        with self._lock:
            if not self.running:
                return  # Already stopped
            self.running = False
            self._shutdown_in_progress = True
    
    def _monitor(self):
        """Internal monitoring loop."""
        while self.running:
            time.sleep(10)  # Check every 10 seconds
            
            with self._lock:
                elapsed = time.time() - self.last_heartbeat
                shutdown_in_progress = self._shutdown_in_progress
            
            # Don't restart if shutdown is in progress
            if shutdown_in_progress:
                print("[WATCHDOG] Shutdown in progress, stopping monitoring")
                break
            
            if elapsed > self.timeout:
                print(f"[WATCHDOG] ALERT! No heartbeat for {int(elapsed)}s. Restarting...")
                self._restart_service()
    
    def _restart_service(self):
        """Restart the Python process."""
        print("[WATCHDOG] Initiating restart...")
        # Only restart if we're running as a service (systemd will manage it)
        # Check if INVOCATION_ID is set (systemd sets this)
        if os.getenv("INVOCATION_ID"):
            # Running under systemd - use execv to restart
            # Using os.execv here is intentional as it replaces the process
            os.execv(sys.executable, [sys.executable] + sys.argv)
        else:
            # Running manually - exit forcefully instead of restarting
            # Using os._exit() here is intentional to force termination of a hung process
            # This is appropriate because the watchdog only triggers when the service is unresponsive
            print("[WATCHDOG] Running in manual mode, exiting instead of restarting")
            print("[WATCHDOG] Please restart the service manually if needed")
            os._exit(1)

# Global watchdog instance
_watchdog = None
_watchdog_stopped = False

def init_watchdog(timeout_seconds=120):
    """Initialize and start the global watchdog."""
    global _watchdog, _watchdog_stopped
    _watchdog = Watchdog(timeout_seconds)
    _watchdog.start()
    _watchdog_stopped = False
    return _watchdog

def feed_watchdog():
    """Feed the global watchdog (call this in your heartbeat loop)."""
    global _watchdog
    if _watchdog:
        _watchdog.feed()

def stop_watchdog():
    """Stop the global watchdog (call during shutdown). Safe to call multiple times."""
    global _watchdog, _watchdog_stopped
    if _watchdog and not _watchdog_stopped:
        _watchdog.stop()
        _watchdog_stopped = True
        print("[WATCHDOG] Stopped")
