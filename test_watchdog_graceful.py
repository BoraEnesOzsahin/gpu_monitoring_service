"""
Test Suite for Watchdog Graceful Shutdown

Tests the new graceful shutdown mechanism instead of os.execv().
"""

import sys
import os
import time
import signal
import threading
from unittest import mock

# Add the reckon_service directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'reckon_service'))

import watchdog


def test_watchdog_timeout_graceful_shutdown():
    """Test that watchdog triggers graceful shutdown instead of execv"""
    print("\n=== Testing Watchdog Timeout Graceful Shutdown ===")
    
    # Reset global state
    watchdog._shutdown_requested = False
    watchdog._shutdown_reason = None
    
    # Create a watchdog with very short timeout for testing
    wd = watchdog.Watchdog(timeout_seconds=2)
    
    print("1. Starting watchdog with 2 second timeout...")
    wd.start()
    
    # Wait for timeout without feeding (need to wait longer for the monitoring thread to check)
    print("2. Waiting for timeout (not feeding watchdog)...")
    # Watchdog checks every 10 seconds, so wait at least 12 seconds for it to detect timeout
    time.sleep(13)
    
    # Check if shutdown was requested
    if watchdog.should_shutdown():
        reason = watchdog.get_shutdown_reason()
        print(f"✓ PASS: Graceful shutdown triggered. Reason: {reason}")
        
        # Verify it's the correct reason
        if reason == "watchdog_timeout":
            print("✓ PASS: Correct shutdown reason")
            wd.stop()
            return True
        else:
            print(f"✗ FAIL: Expected 'watchdog_timeout', got '{reason}'")
            wd.stop()
            return False
    else:
        print("✗ FAIL: Shutdown was not triggered")
        wd.stop()
        return False


def test_watchdog_feed_prevents_shutdown():
    """Test that feeding the watchdog prevents shutdown"""
    print("\n=== Testing Watchdog Feed Prevents Shutdown ===")
    
    # Reset global state
    watchdog._shutdown_requested = False
    watchdog._shutdown_reason = None
    
    # Create a new watchdog
    wd = watchdog.Watchdog(timeout_seconds=3)
    
    print("1. Starting watchdog with 3 second timeout...")
    wd.start()
    
    # Feed the watchdog multiple times
    print("2. Feeding watchdog every 1 second for 5 seconds...")
    for i in range(5):
        time.sleep(1)
        wd.feed()
        print(f"   Fed watchdog at {i+1}s")
    
    # Check that shutdown was NOT triggered
    if not watchdog.should_shutdown():
        print("✓ PASS: Shutdown was not triggered (watchdog fed successfully)")
        wd.stop()
        return True
    else:
        reason = watchdog.get_shutdown_reason()
        print(f"✗ FAIL: Shutdown was triggered unexpectedly. Reason: {reason}")
        wd.stop()
        return False


def test_watchdog_stop():
    """Test that watchdog can be stopped gracefully"""
    print("\n=== Testing Watchdog Stop ===")
    
    # Reset global state
    watchdog._shutdown_requested = False
    watchdog._shutdown_reason = None
    
    # Create a new watchdog
    wd = watchdog.Watchdog(timeout_seconds=2)
    
    print("1. Starting watchdog...")
    wd.start()
    
    print("2. Stopping watchdog...")
    wd.stop()
    
    # Wait to see if thread stops
    time.sleep(1)
    
    if wd._thread and not wd._thread.is_alive():
        print("✓ PASS: Watchdog thread stopped (daemon thread)")
        return True
    elif wd._thread and wd._thread.is_alive():
        # Daemon threads may still be alive, check if running flag is False
        if not wd.running:
            print("✓ PASS: Watchdog running flag set to False")
            return True
        else:
            print("✗ FAIL: Watchdog still running")
            return False
    else:
        print("✓ PASS: Watchdog stopped")
        return True


def test_signal_handler_setup():
    """Test that signal handlers can be set up"""
    print("\n=== Testing Signal Handler Setup ===")
    
    cleanup_called = {"value": False}
    
    def test_cleanup():
        cleanup_called["value"] = True
        print("   Cleanup callback called")
    
    try:
        # Set up signal handlers
        print("1. Setting up signal handlers...")
        watchdog.setup_signal_handlers(test_cleanup)
        
        # Check that SIGTERM handler is set
        sigterm_handler = signal.getsignal(signal.SIGTERM)
        sigint_handler = signal.getsignal(signal.SIGINT)
        
        if sigterm_handler != signal.SIG_DFL and sigint_handler != signal.SIG_DFL:
            print("✓ PASS: Signal handlers registered")
            return True
        else:
            print("✗ FAIL: Signal handlers not registered properly")
            return False
            
    except Exception as e:
        print(f"✗ FAIL: Error setting up signal handlers: {e}")
        return False


def test_no_execv_used():
    """Verify that os.execv is not used in the watchdog module"""
    print("\n=== Testing No os.execv Usage ===")
    
    # Read the watchdog.py file
    watchdog_file = os.path.join(os.path.dirname(__file__), 'reckon_service', 'watchdog.py')
    
    with open(watchdog_file, 'r') as f:
        content = f.read()
    
    # Check that os.execv is not present
    if 'os.execv' in content:
        print("✗ FAIL: os.execv still found in watchdog.py")
        return False
    else:
        print("✓ PASS: os.execv not found in watchdog.py (good!)")
        return True


def test_shutdown_functions():
    """Test shutdown helper functions"""
    print("\n=== Testing Shutdown Helper Functions ===")
    
    # Reset global state
    watchdog._shutdown_requested = False
    watchdog._shutdown_reason = None
    
    # Initially should not be shutdown
    if watchdog.should_shutdown():
        print("✗ FAIL: should_shutdown() returned True when not shutdown")
        return False
    
    # Trigger shutdown
    watchdog._shutdown_requested = True
    watchdog._shutdown_reason = "test_reason"
    
    # Now should be shutdown
    if not watchdog.should_shutdown():
        print("✗ FAIL: should_shutdown() returned False when shutdown")
        return False
    
    # Check reason
    reason = watchdog.get_shutdown_reason()
    if reason != "test_reason":
        print(f"✗ FAIL: Expected 'test_reason', got '{reason}'")
        return False
    
    print("✓ PASS: Shutdown helper functions work correctly")
    return True


def test_global_watchdog_functions():
    """Test global watchdog initialization and feed functions"""
    print("\n=== Testing Global Watchdog Functions ===")
    
    # Reset global state
    watchdog._shutdown_requested = False
    watchdog._shutdown_reason = None
    watchdog._watchdog = None
    
    # Initialize watchdog
    print("1. Initializing global watchdog...")
    wd = watchdog.init_watchdog(timeout_seconds=5)
    
    if wd is None:
        print("✗ FAIL: init_watchdog returned None")
        return False
    
    if watchdog._watchdog is None:
        print("✗ FAIL: Global watchdog not set")
        return False
    
    # Feed watchdog
    print("2. Feeding global watchdog...")
    watchdog.feed_watchdog()
    
    # Stop watchdog
    print("3. Stopping global watchdog...")
    watchdog.stop_watchdog()
    
    print("✓ PASS: Global watchdog functions work correctly")
    return True


def run_all_tests():
    """Run all test suites"""
    print("=" * 70)
    print("WATCHDOG GRACEFUL SHUTDOWN TEST SUITE")
    print("=" * 70)
    
    tests = [
        ("No execv Usage", test_no_execv_used),
        ("Shutdown Helper Functions", test_shutdown_functions),
        ("Global Watchdog Functions", test_global_watchdog_functions),
        ("Signal Handler Setup", test_signal_handler_setup),
        ("Watchdog Stop", test_watchdog_stop),
        ("Watchdog Feed Prevents Shutdown", test_watchdog_feed_prevents_shutdown),
        ("Watchdog Timeout Graceful Shutdown", test_watchdog_timeout_graceful_shutdown),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n✗ EXCEPTION in {test_name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # Print summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed_count = sum(1 for _, passed in results if passed)
    failed_count = len(results) - passed_count
    
    for test_name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed_count}/{len(results)} tests passed")
    
    if failed_count == 0:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n❌ {failed_count} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
