import threading
import time
import os
import sys
import signal

"""
RECKON Client - Internal Watchdog
Purpose: Monitors the main service and triggers graceful shutdown if unresponsive.
"""

# Global shutdown flag
_shutdown_requested = False
_shutdown_reason = None

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
        """Stop the watchdog gracefully."""
        self.running = False
        if self._thread and self._thread.is_alive():
            print("[WATCHDOG] Stopping monitoring thread...")
    
    def _monitor(self):
        """Internal monitoring loop."""
        while self.running:
            time.sleep(10)  # Check every 10 seconds
            
            with self._lock:
                elapsed = time.time() - self.last_heartbeat
            
            if elapsed > self.timeout:
                print(f"[WATCHDOG] ALERT! No heartbeat for {int(elapsed)}s.")
                print("[WATCHDOG] Triggering graceful shutdown...")
                self._trigger_graceful_shutdown("watchdog_timeout")
                break  # Exit monitoring loop
    
    def _trigger_graceful_shutdown(self, reason):
        """
        Trigger a graceful shutdown instead of forceful restart.
        This allows cleanup to occur and lets systemd restart the service.
        """
        global _shutdown_requested, _shutdown_reason
        _shutdown_requested = True
        _shutdown_reason = reason
        print(f"[WATCHDOG] Shutdown requested. Reason: {reason}")
        print("[WATCHDOG] Service will exit cleanly and systemd will restart it.")


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

def stop_watchdog():
    """Stop the global watchdog (call during cleanup)."""
    global _watchdog
    if _watchdog:
        _watchdog.stop()

def should_shutdown():
    """Check if a graceful shutdown has been requested."""
    global _shutdown_requested
    return _shutdown_requested

def get_shutdown_reason():
    """Get the reason for shutdown."""
    global _shutdown_reason
    return _shutdown_reason

def setup_signal_handlers(cleanup_callback):
    """
    Set up signal handlers for graceful shutdown.
    
    Args:
        cleanup_callback: Function to call before exit for cleanup
    """
    def signal_handler(signum, frame):
        signal_name = signal.Signals(signum).name
        print(f"\n[SIGNAL] Received {signal_name}. Initiating graceful shutdown...")
        
        global _shutdown_requested, _shutdown_reason
        _shutdown_requested = True
        _shutdown_reason = f"signal_{signal_name}"
        
        # Call cleanup
        if cleanup_callback:
            try:
                cleanup_callback()
            except Exception as e:
                print(f"[SIGNAL] Error during cleanup: {e}")
        
        # Stop watchdog
        stop_watchdog()
        
        print("[SIGNAL] Graceful shutdown complete. Exiting...")
        sys.exit(0)
    
    # Register handlers for SIGTERM (systemd stop) and SIGINT (Ctrl+C)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    print("[SIGNAL] Signal handlers registered (SIGTERM, SIGINT)")
