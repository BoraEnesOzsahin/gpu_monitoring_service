import threading
import time
import os
import sys
from datetime import datetime

"""
RECKON Client - Internal Watchdog
Purpose: Monitors the main service and restarts if unresponsive.
"""

def get_restart_log_path():
    """Get the path for the restart events log file."""
    return os.getenv("RESTART_LOG_FILE", "restart_events.log")

def log_restart_event(reason, elapsed_seconds=None):
    """
    Append a restart event to persistent log.
    This log survives process restarts so we can track restart history.
    """
    try:
        log_path = get_restart_log_path()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        event = f"[{timestamp}] {reason}"
        if elapsed_seconds is not None:
            event += f" (no heartbeat for {elapsed_seconds}s)"
        event += "\n"
        
        with open(log_path, "a") as f:
            f.write(event)
            f.flush()  # Ensure written to disk before potential restart
    except Exception as e:
        print(f"[WATCHDOG] Warning: Failed to log restart event: {e}")

def get_restart_history(max_lines=10):
    """
    Read the most recent restart events from the log.
    Returns a list of log lines.
    """
    try:
        log_path = get_restart_log_path()
        if not os.path.exists(log_path):
            return []
        
        with open(log_path, "r") as f:
            lines = f.readlines()
            return lines[-max_lines:] if len(lines) > max_lines else lines
    except Exception as e:
        print(f"[WATCHDOG] Warning: Failed to read restart history: {e}")
        return []

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
        # SAFETY: start_time is initialized in __init__ (main thread)
        # and only read by the monitoring thread started via start()
        # Thread safety: happens-before relationship ensures safe visibility
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
                    self._restart_service(elapsed)
            except Exception as e:
                print(f"[WATCHDOG] Error in monitor loop: {e}. Continuing...")
                # Continue monitoring even if one iteration fails
    
    def _restart_service(self, elapsed_seconds):
        """Restart the Python process."""
        print("[WATCHDOG] Initiating restart...")
        
        # SAFETY: Log restart event to persistent file BEFORE restarting
        # This ensures we can track restart history even after process restarts
        log_restart_event("Watchdog restart triggered - detected infinite loop or frozen process", int(elapsed_seconds))
        
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
    
    # Display restart history on startup
    history = get_restart_history(max_lines=10)
    if history:
        print("[WATCHDOG] Previous restart events detected:")
        for line in history:
            print(f"  {line.rstrip()}")
    else:
        print("[WATCHDOG] No previous restart events found.")
    
    _watchdog = Watchdog(timeout_seconds)
    _watchdog.start()
    return _watchdog

def feed_watchdog():
    """Feed the global watchdog (call this in your heartbeat loop)."""
    global _watchdog
    if _watchdog:
        _watchdog.feed()
