"""
Test Suite for Power Control Security Features

Tests validation, rate limiting, audit logging, and secure command execution.
"""

import sys
import os
import time
import json
from unittest import mock

# Add the reckon_service directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'reckon_service'))

import power_control


def test_validation():
    """Test input validation for power values"""
    print("\n=== Testing Input Validation ===")
    
    test_cases = [
        # (value, value_name, should_pass, description)
        (1200, "total power", True, "Valid total power"),
        (150, "per-GPU power", True, "Valid per-GPU power"),
        (-100, "total power", False, "Negative power (invalid)"),
        (5000, "total power", False, "Excessive power (invalid)"),
        ("invalid", "total power", False, "Non-numeric value (invalid)"),
        (150.7, "total power", True, "Float value (should convert to int)"),
        (50, "per-GPU power", False, "Below minimum per-GPU (invalid)"),
        (300, "per-GPU power", False, "Above maximum per-GPU (invalid)"),
        (100, "per-GPU power", True, "Minimum per-GPU (valid)"),
        (210, "per-GPU power", True, "Maximum per-GPU (valid)"),
    ]
    
    passed = 0
    failed = 0
    
    for value, value_name, should_pass, description in test_cases:
        is_valid, validated, error = power_control.validate_power_value(value, value_name)
        
        if should_pass:
            if is_valid:
                print(f"✓ PASS: {description} - {value} -> {validated}W")
                passed += 1
            else:
                print(f"✗ FAIL: {description} - Expected valid, got error: {error}")
                failed += 1
        else:
            if not is_valid:
                print(f"✓ PASS: {description} - Correctly rejected: {error}")
                passed += 1
            else:
                print(f"✗ FAIL: {description} - Expected invalid, got valid: {validated}")
                failed += 1
    
    print(f"\nValidation Tests: {passed} passed, {failed} failed")
    return failed == 0


def test_rate_limiting():
    """Test rate limiting functionality"""
    print("\n=== Testing Rate Limiting ===")
    
    # Create a rate limiter with tight limits for testing
    limiter = power_control.RateLimiter(max_calls=3, period_seconds=5)
    
    print("Rate limit: 3 calls per 5 seconds")
    
    # Test normal operation
    print("\n1. Testing normal operation (should allow 3 calls):")
    results = []
    for i in range(3):
        allowed = limiter.allow()
        results.append(allowed)
        print(f"   Call {i+1}: {'ALLOWED' if allowed else 'BLOCKED'}")
    
    if not all(results):
        print("✗ FAIL: First 3 calls should be allowed")
        return False
    
    # Test rate limit enforcement
    print("\n2. Testing rate limit enforcement (4th call should be blocked):")
    allowed = limiter.allow()
    print(f"   Call 4: {'ALLOWED' if allowed else 'BLOCKED'}")
    
    if allowed:
        print("✗ FAIL: 4th call should be blocked")
        return False
    
    # Check cooldown
    cooldown = limiter.get_remaining_cooldown()
    print(f"\n3. Cooldown period: {cooldown}s (should be 1-5 seconds)")
    
    if cooldown < 1 or cooldown > 5:
        print(f"✗ FAIL: Cooldown should be 1-5 seconds, got {cooldown}")
        return False
    
    # Test time window sliding
    print("\n4. Testing time window (waiting 6 seconds)...")
    time.sleep(6)
    
    allowed = limiter.allow()
    print(f"   After cooldown: {'ALLOWED' if allowed else 'BLOCKED'}")
    
    if not allowed:
        print("✗ FAIL: Should be allowed after cooldown period")
        return False
    
    print("\n✓ Rate limiting tests passed")
    return True


def test_audit_logging():
    """Test audit logging functionality"""
    print("\n=== Testing Audit Logging ===")
    
    # Use a test log file
    test_log = "/tmp/test_power_audit.log"
    
    # Clean up any existing test log
    if os.path.exists(test_log):
        os.remove(test_log)
    
    # Temporarily override the log file
    original_log = power_control.AUDIT_LOG_FILE
    power_control.AUDIT_LOG_FILE = test_log
    
    try:
        # Log some test events
        power_control.log_power_adjustment("test_event", {
            "test_field": "test_value",
            "number": 123
        })
        
        power_control.log_power_adjustment("validation_error", {
            "reason": "test_error",
            "value": 999
        })
        
        # Check that log file was created
        if not os.path.exists(test_log):
            print("✗ FAIL: Audit log file was not created")
            return False
        
        # Read and validate log entries
        with open(test_log, 'r') as f:
            lines = f.readlines()
        
        if len(lines) != 2:
            print(f"✗ FAIL: Expected 2 log entries, got {len(lines)}")
            return False
        
        # Validate JSON format
        for i, line in enumerate(lines):
            try:
                entry = json.loads(line)
                if "timestamp" not in entry or "event" not in entry or "details" not in entry:
                    print(f"✗ FAIL: Log entry {i+1} missing required fields")
                    return False
                print(f"   Entry {i+1}: {entry['event']} - {entry['details']}")
            except json.JSONDecodeError as e:
                print(f"✗ FAIL: Log entry {i+1} is not valid JSON: {e}")
                return False
        
        print("\n✓ Audit logging tests passed")
        return True
        
    finally:
        # Restore original log file setting
        power_control.AUDIT_LOG_FILE = original_log
        
        # Clean up test log
        if os.path.exists(test_log):
            os.remove(test_log)


def test_secure_power_adjustment():
    """Test the secure power adjustment function with mocked GPU driver"""
    print("\n=== Testing Secure Power Adjustment ===")
    
    # Create a mock GPU driver module
    mock_gpu_driver = mock.MagicMock()
    mock_gpu_driver.set_power_limit_safe = mock.MagicMock(return_value=True)
    
    # Temporarily enable remote power control for testing
    original_allow = power_control.ALLOW_REMOTE_POWER_CONTROL
    power_control.ALLOW_REMOTE_POWER_CONTROL = True
    
    # Create a fresh rate limiter to avoid interference from previous tests
    power_control._rate_limiter = power_control.RateLimiter(
        power_control.RATE_LIMIT_MAX_CHANGES,
        power_control.RATE_LIMIT_PERIOD_SECONDS
    )
    
    try:
        # Test 1: Valid power adjustment
        print("\n1. Testing valid power adjustment:")
        success, message = power_control.apply_power_limit_secure(1200, 6, mock_gpu_driver)
        
        if not success:
            print(f"✗ FAIL: Valid adjustment should succeed: {message}")
            return False
        
        # Check that the GPU driver was called with correct parameters
        if not mock_gpu_driver.set_power_limit_safe.called:
            print("✗ FAIL: GPU driver was not called")
            return False
        
        # Get the call arguments
        call_args = mock_gpu_driver.set_power_limit_safe.call_args
        per_gpu_watts = call_args[0][0]
        
        print(f"   ✓ Adjustment succeeded, per-GPU: {per_gpu_watts}W")
        
        if per_gpu_watts < 100 or per_gpu_watts > 210:
            print(f"✗ FAIL: Per-GPU power {per_gpu_watts}W outside safe range (100-210W)")
            return False
        
        # Test 2: Invalid power value
        print("\n2. Testing invalid power value (negative):")
        mock_gpu_driver.reset_mock()
        success, message = power_control.apply_power_limit_secure(-500, 6, mock_gpu_driver)
        
        if success:
            print("✗ FAIL: Negative power should be rejected")
            return False
        
        print(f"   ✓ Correctly rejected: {message}")
        
        # Test 3: Zero GPUs
        print("\n3. Testing with zero GPUs:")
        mock_gpu_driver.reset_mock()
        success, message = power_control.apply_power_limit_secure(1200, 0, mock_gpu_driver)
        
        if success:
            print("✗ FAIL: Zero GPUs should be rejected")
            return False
        
        print(f"   ✓ Correctly rejected: {message}")
        
        # Test 4: Remote control disabled
        print("\n4. Testing with remote control disabled:")
        power_control.ALLOW_REMOTE_POWER_CONTROL = False
        mock_gpu_driver.reset_mock()
        success, message = power_control.apply_power_limit_secure(1200, 6, mock_gpu_driver)
        
        if success:
            print("✗ FAIL: Should be rejected when remote control is disabled")
            return False
        
        print(f"   ✓ Correctly rejected: {message}")
        
        print("\n✓ Secure power adjustment tests passed")
        return True
        
    finally:
        # Restore original setting
        power_control.ALLOW_REMOTE_POWER_CONTROL = original_allow


def test_rate_limit_status():
    """Test rate limit status reporting"""
    print("\n=== Testing Rate Limit Status ===")
    
    status = power_control.get_rate_limit_status()
    
    required_keys = ["current_count", "max_allowed", "period_seconds", "cooldown_seconds", "enabled"]
    
    for key in required_keys:
        if key not in status:
            print(f"✗ FAIL: Missing required key: {key}")
            return False
    
    print(f"   Status: {status}")
    print("✓ Rate limit status test passed")
    return True


def run_all_tests():
    """Run all test suites"""
    print("=" * 70)
    print("POWER CONTROL SECURITY TEST SUITE")
    print("=" * 70)
    
    tests = [
        ("Input Validation", test_validation),
        ("Rate Limiting", test_rate_limiting),
        ("Audit Logging", test_audit_logging),
        ("Secure Power Adjustment", test_secure_power_adjustment),
        ("Rate Limit Status", test_rate_limit_status),
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
