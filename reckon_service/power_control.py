"""
RECKON Client - Secure Power Control Module
Purpose: Handles GPU power limit adjustments with security safeguards
"""

import time
import json
import os
from collections import deque
from datetime import datetime

# --- CONFIGURATION ---
AUDIT_LOG_FILE = os.getenv("POWER_AUDIT_LOG", "power_audit.log")
RATE_LIMIT_MAX_CHANGES = int(os.getenv("RATE_LIMIT_MAX_CHANGES", "5"))
RATE_LIMIT_PERIOD_SECONDS = int(os.getenv("RATE_LIMIT_PERIOD_SECONDS", "300"))  # 5 minutes
ALLOW_REMOTE_POWER_CONTROL = os.getenv("ALLOW_REMOTE_POWER_CONTROL", "true").lower() == "true"

# Hardware limits
MAX_PER_GPU_W = 210
MIN_PER_GPU_W = 100

# Reasonable total power limits to prevent extreme values
MIN_TOTAL_POWER_W = 100
MAX_TOTAL_POWER_W = 2000  # Reasonable max for a mining rig


class RateLimiter:
    """
    Implements rate limiting for power adjustment commands.
    Tracks recent adjustments and prevents excessive changes.
    """
    def __init__(self, max_calls: int, period_seconds: int):
        self.max_calls = max_calls
        self.period = period_seconds
        self.calls = deque()
    
    def allow(self) -> bool:
        """
        Check if a new power adjustment is allowed.
        Returns True if allowed, False if rate limit exceeded.
        """
        now = time.time()
        
        # Remove old calls outside the time window
        while self.calls and self.calls[0] < now - self.period:
            self.calls.popleft()
        
        # Check if we're under the limit
        if len(self.calls) < self.max_calls:
            self.calls.append(now)
            return True
        
        return False
    
    def get_remaining_cooldown(self) -> int:
        """
        Returns the number of seconds until the next adjustment is allowed.
        """
        if not self.calls:
            return 0
        
        now = time.time()
        oldest_call = self.calls[0]
        time_since_oldest = now - oldest_call
        
        if time_since_oldest >= self.period:
            return 0
        
        return int(self.period - time_since_oldest)


# Global rate limiter instance
_rate_limiter = RateLimiter(RATE_LIMIT_MAX_CHANGES, RATE_LIMIT_PERIOD_SECONDS)


def log_power_adjustment(event_type: str, details: dict):
    """
    Logs power adjustment events to audit log.
    
    Args:
        event_type: Type of event (e.g., "adjustment", "validation_error", "rate_limit")
        details: Dictionary with event details
    """
    try:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        log_entry = {
            "timestamp": timestamp,
            "event": event_type,
            "details": details
        }
        
        with open(AUDIT_LOG_FILE, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
            
    except Exception as e:
        print(f"[WARNING] Failed to write audit log: {e}")


def validate_power_value(value, value_name: str = "power value") -> tuple:
    """
    Validates a power value for type and range.
    
    Args:
        value: The value to validate
        value_name: Description of the value for error messages
        
    Returns:
        (is_valid: bool, validated_value: int or None, error_message: str or None)
    """
    # Type validation
    if not isinstance(value, (int, float)):
        error = f"Invalid {value_name}: must be numeric, got {type(value).__name__}"
        return False, None, error
    
    # Convert to int
    try:
        int_value = int(value)
    except (ValueError, OverflowError):
        error = f"Invalid {value_name}: cannot convert to integer"
        return False, None, error
    
    # Range validation for total power
    if value_name == "total power":
        if int_value < MIN_TOTAL_POWER_W:
            error = f"Invalid {value_name}: {int_value}W is below minimum {MIN_TOTAL_POWER_W}W"
            return False, None, error
        
        if int_value > MAX_TOTAL_POWER_W:
            error = f"Invalid {value_name}: {int_value}W exceeds maximum {MAX_TOTAL_POWER_W}W"
            return False, None, error
    
    # Range validation for per-GPU power
    elif value_name == "per-GPU power":
        if int_value < MIN_PER_GPU_W:
            error = f"Invalid {value_name}: {int_value}W is below minimum {MIN_PER_GPU_W}W"
            return False, None, error
        
        if int_value > MAX_PER_GPU_W:
            error = f"Invalid {value_name}: {int_value}W exceeds maximum {MAX_PER_GPU_W}W"
            return False, None, error
    
    return True, int_value, None


def apply_power_limit_secure(target_total_watts, gpu_count, gpu_driver_module):
    """
    Securely applies power limits to GPUs with validation, rate limiting, and audit logging.
    
    Args:
        target_total_watts: Target total power in watts (from server)
        gpu_count: Number of GPUs
        gpu_driver_module: The gpu_driver module (passed to avoid circular import)
        
    Returns:
        (success: bool, message: str)
    """
    # Check if remote power control is enabled
    if not ALLOW_REMOTE_POWER_CONTROL:
        error_msg = "Remote power control is disabled in configuration"
        log_power_adjustment("rejected", {
            "reason": "feature_disabled",
            "target_total_watts": target_total_watts
        })
        return False, error_msg
    
    # Validate GPU count
    if gpu_count == 0:
        error_msg = "No GPUs detected"
        log_power_adjustment("validation_error", {
            "reason": "no_gpus",
            "target_total_watts": target_total_watts
        })
        return False, error_msg
    
    # Validate target total power
    is_valid, validated_total, error = validate_power_value(target_total_watts, "total power")
    if not is_valid:
        log_power_adjustment("validation_error", {
            "reason": "invalid_total_power",
            "raw_value": str(target_total_watts),
            "error": error
        })
        return False, error
    
    # Check rate limiting
    if not _rate_limiter.allow():
        cooldown = _rate_limiter.get_remaining_cooldown()
        error_msg = f"Rate limit exceeded. Too many power adjustments. Cooldown: {cooldown}s"
        log_power_adjustment("rate_limit_exceeded", {
            "target_total_watts": validated_total,
            "cooldown_seconds": cooldown,
            "limit": f"{RATE_LIMIT_MAX_CHANGES} changes per {RATE_LIMIT_PERIOD_SECONDS}s"
        })
        print(f"[SECURITY] {error_msg}")
        return False, error_msg
    
    # Calculate per-GPU power
    requested_per_card = int(validated_total / gpu_count)
    
    # Apply safety clamping
    safe_limit = min(requested_per_card, MAX_PER_GPU_W)
    safe_limit = max(safe_limit, MIN_PER_GPU_W)
    
    # Validate the final per-GPU value
    is_valid, validated_per_gpu, error = validate_power_value(safe_limit, "per-GPU power")
    if not is_valid:
        log_power_adjustment("validation_error", {
            "reason": "invalid_per_gpu_power",
            "raw_value": safe_limit,
            "error": error
        })
        return False, error
    
    print(f"--- SECURE POWER CONTROL ---")
    print(f" > Server Request: {validated_total}W total")
    print(f" > Calculated Per GPU: {requested_per_card}W")
    print(f" > APPLIED SAFE LIMIT: {validated_per_gpu}W per GPU (Range: {MIN_PER_GPU_W}-{MAX_PER_GPU_W}W)")
    print(f" > Rate Limit Status: {len(_rate_limiter.calls)}/{RATE_LIMIT_MAX_CHANGES} in last {RATE_LIMIT_PERIOD_SECONDS}s")
    
    # Execute the power limit command securely
    try:
        success = gpu_driver_module.set_power_limit_safe(validated_per_gpu, gpu_count)
        
        if success:
            log_power_adjustment("adjustment_success", {
                "target_total_watts": validated_total,
                "calculated_per_gpu": requested_per_card,
                "applied_per_gpu": validated_per_gpu,
                "gpu_count": gpu_count,
                "total_applied": validated_per_gpu * gpu_count
            })
            return True, f"Power limit set to {validated_per_gpu}W per GPU"
        else:
            log_power_adjustment("adjustment_failed", {
                "target_total_watts": validated_total,
                "applied_per_gpu": validated_per_gpu,
                "reason": "command_execution_failed"
            })
            return False, "Failed to execute power limit command"
            
    except Exception as e:
        error_msg = f"Exception during power adjustment: {str(e)}"
        log_power_adjustment("adjustment_error", {
            "target_total_watts": validated_total,
            "applied_per_gpu": validated_per_gpu,
            "error": str(e)
        })
        return False, error_msg


def get_rate_limit_status() -> dict:
    """
    Returns current rate limiting status for monitoring/debugging.
    """
    return {
        "current_count": len(_rate_limiter.calls),
        "max_allowed": RATE_LIMIT_MAX_CHANGES,
        "period_seconds": RATE_LIMIT_PERIOD_SECONDS,
        "cooldown_seconds": _rate_limiter.get_remaining_cooldown(),
        "enabled": ALLOW_REMOTE_POWER_CONTROL
    }


# --- TEST BLOCK ---
if __name__ == "__main__":
    print("--- Power Control Security Module Test ---")
    print(f"Remote control enabled: {ALLOW_REMOTE_POWER_CONTROL}")
    print(f"Rate limit: {RATE_LIMIT_MAX_CHANGES} changes per {RATE_LIMIT_PERIOD_SECONDS}s")
    print(f"Hardware limits: {MIN_PER_GPU_W}W - {MAX_PER_GPU_W}W per GPU")
    print(f"Audit log: {AUDIT_LOG_FILE}")
    
    # Test validation
    print("\n--- Testing Validation ---")
    test_cases = [
        (1200, "valid total power"),
        (-100, "negative power"),
        (5000, "excessive power"),
        ("invalid", "non-numeric value"),
        (150.5, "float value (should convert)"),
    ]
    
    for value, description in test_cases:
        is_valid, validated, error = validate_power_value(value, "total power")
        status = "✓ PASS" if is_valid else "✗ FAIL"
        print(f"{status} {description}: {value} -> {validated if is_valid else error}")
    
    # Test rate limiting
    print("\n--- Testing Rate Limiter ---")
    limiter = RateLimiter(3, 10)  # 3 calls per 10 seconds
    
    for i in range(5):
        allowed = limiter.allow()
        print(f"Attempt {i+1}: {'ALLOWED' if allowed else 'BLOCKED'}")
    
    print(f"Cooldown: {limiter.get_remaining_cooldown()}s")
