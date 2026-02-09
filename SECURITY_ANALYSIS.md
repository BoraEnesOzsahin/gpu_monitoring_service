# Security Analysis Report: GPU Monitoring Service

**Date:** 2026-02-09  
**Repository:** BoraEnesOzsahin/gpu_monitoring_service  
**Analysis Focus:** Hardware locking mechanisms and security vulnerabilities

---

## Executive Summary

This report investigates potential hardware locking mechanisms within the GPU monitoring service, specifically focusing on the `miner_software` directory and the `reckon_service` code. The analysis reveals **NO malicious hardware-locking code**, but identifies **several security concerns** related to remote hardware control, process management, and command execution.

### Key Findings:

✅ **No Hardware Locking Detected** - The miner software itself is legitimate and does not lock GPU hardware  
⚠️ **Remote Power Control** - Service allows remote manipulation of GPU power limits  
🔴 **Security Vulnerabilities** - Multiple security issues in the monitoring service code  
🟠 **Aggressive Restart Mechanism** - Watchdog can forcefully restart without cleanup

---

## Analysis: miner_software Directory

### Overview

The `miner_software` directory contains **lolMiner v1.98**, a legitimate open-source cryptocurrency mining application for Linux. This is GPU mining software used to mine various cryptocurrencies (Ethereum, Ergo, Beam, etc.).

### Contents

```
miner_software/
├── 1.98/
│   ├── lolMiner              (13MB binary executable)
│   ├── lolMiner.cfg          (configuration file)
│   ├── mine_*.sh             (25 mining scripts for different coins)
│   ├── emergency.sh          (placeholder recovery script)
│   ├── license.txt           (software license)
│   └── readme.txt            (documentation)
└── lolMiner_v1.98_Lin64.tar.gz (archive)
```

### Mining Scripts Analysis

All 25 shell scripts (`mine_eth.sh`, `mine_ergo.sh`, etc.) follow an identical, benign pattern:

```bash
#!/bin/bash
POOL=pool.example.com:2020
WALLET=0x155da78b788ab54bea1340c10a5422a8ae88142f.lolMinerWorker
cd "$(dirname "$0")"
./lolMiner --algo COIN --pool $POOL --user $WALLET
while [ $? -eq 42 ]; do
    sleep 10s
    ./lolMiner --algo COIN --pool $POOL --user $WALLET
done
```

**Analysis:**
- Changes to script directory
- Executes lolMiner with specified algorithm and pool
- Restarts if exit code is 42 (standard miner restart behavior)
- No system modifications, no sudo, no hardware locks

### Security Checks Performed

❌ **NOT FOUND:**
- No hardware locking mechanisms
- No `sudo`, `chmod`, or permission changes
- No data exfiltration (`wget`, `curl`)
- No system manipulation (`rm -rf`, `dd if=`, `systemctl`)
- No persistence mechanisms or backdoors
- No license restrictions preventing normal GPU use
- No hidden operations or malicious code

### emergency.sh Script

```bash
#!/bin/bash
echo "Hello World from emergency script"
```

A minimal placeholder template for users to add custom crash recovery actions.

### lolMiner.cfg Configuration

```ini
algo=ETCHASH
pool=stratum+tcp://stratum-etc.antpool.com:8008
user=0x91109d3C865971DdC7566A9D85A803a74e003ACB.AyroWorkerRig1
apiport=8081
shortstats=10
longstats=60
```

Standard mining pool configuration with no suspicious settings.

### Conclusion: miner_software

✅ **CLEAN** - This is legitimate, open-source cryptocurrency mining software with no concerning elements. No hardware locking, no backdoors, no unauthorized operations.

---

## Analysis: reckon_service (Monitoring Service)

### Overview

The `reckon_service` is a Python-based GPU monitoring client that:
- Monitors GPU hardware status
- Reports telemetry to a remote EMS (Energy Management System) server
- Receives and executes remote commands to adjust GPU power limits
- Uses a watchdog mechanism to ensure service availability

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      SYSTEMD                                 │
│  (Restarts if process dies completely)                       │
├─────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────┐  │
│  │                 RECKON CLIENT                          │  │
│  │  ┌─────────────────┐    ┌─────────────────────────┐   │  │
│  │  │ Internal        │    │ Main Heartbeat Loop     │   │  │
│  │  │ Watchdog Thread │◄───│ (feeds watchdog)        │   │  │
│  │  │                 │    │                         │   │  │
│  │  │ If no feed for  │    │ If hung/frozen:         │   │  │
│  │  │ 120s → restart  │    │ watchdog restarts       │   │  │
│  │  └─────────────────┘    └─────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔴 Critical Security Findings

### 1. Remote Hardware Control (Power Limit Manipulation)

**File:** `reckon_service/main.py` (lines 21-49, 196-199)

**Issue:** The service allows a remote server to execute `rocm-smi --setpowerlimit` commands on GPU hardware.

**Code:**
```python
def set_power_limit(gpu_id: str, target_w: int):
    """Sets power limit on GPU using rocm-smi"""
    min_watts = 100
    max_watts = 210
    clamped_w = max(min_watts, min(target_w, max_watts))
    
    command = f"rocm-smi -d {gpu_id} --setpowerlimit {clamped_w}"
    gpu_driver.run_command(command, log_output=True)

# In main loop:
if data.get("action") == "adjust_power":
    target_w = data.get("setpoint_power_w", 1500)
    set_power_limit(gpu_id, target_w)
```

**Risk Level:** 🟠 **MEDIUM**

**Impact:**
- Remote server can reduce GPU performance to 100-210W per card
- Could be used to throttle mining operations
- Could cause hardware stress if power limits are changed rapidly
- Control happens every 60 seconds (heartbeat interval)

**Mitigations in Place:**
- Clamped to safety limits (MIN: 100W, MAX: 210W)
- Designed for legitimate power management

**Potential Issues:**
- **No authentication validation** - if server is compromised, attacker can control GPUs
- **No rate limiting** - server can change power every 60 seconds
- **No user consent** - changes happen automatically without operator approval
- **No audit logging** - power changes not logged to separate audit trail

**Does it lock hardware?** NO - it only adjusts power limits, doesn't prevent GPU access

---

### 2. Dangerous Process Restart Mechanism (execv)

**File:** `reckon_service/watchdog.py` (lines 46-49)

**Issue:** Watchdog forcefully restarts the entire Python process using `os.execv()` without graceful shutdown.

**Code:**
```python
def _check_timeout(self):
    elapsed = time.time() - self.last_feed
    if elapsed > self.timeout:
        print(f"[WATCHDOG] ALERT! No heartbeat for {elapsed:.0f}s. Restarting...")
        print("[WATCHDOG] Initiating restart...")
        os.execv(sys.executable, [sys.executable] + sys.argv)
```

**Risk Level:** 🔴 **HIGH**

**Impact:**
- **No graceful shutdown or cleanup**
- Can leave GPU processes orphaned
- Can corrupt GPU state if mining occurs during restart
- No opportunity for processes to save state
- Immediate replacement without cleanup

**Triggering Conditions:**
- No heartbeat for 120 seconds (default `WATCHDOG_TIMEOUT`)
- Network timeouts, frozen threads, deadlocks
- Long-running operations

**Could it lock hardware?** POTENTIALLY - forceful restarts without cleanup could leave GPU in inconsistent state, potentially requiring reboot to recover.

**Recommendation:**
```python
# Better approach:
import signal
import atexit

def graceful_shutdown():
    print("[WATCHDOG] Gracefully shutting down...")
    # Clean up GPU state
    # Close network connections
    # Save state
    sys.exit(1)  # Let systemd restart cleanly

signal.signal(signal.SIGTERM, lambda sig, frame: graceful_shutdown())
```

---

### 3. Unrestricted Shell Command Execution

**File:** `reckon_service/gpu_driver.py` (lines 19-32)

**Issue:** Uses `subprocess.run()` with `shell=True`, allowing shell interpretation of commands.

**Code:**
```python
def run_command(command: str, log_output: bool = False) -> Dict:
    try:
        result = subprocess.run(
            command,
            shell=True,  # ⚠️ DANGEROUS
            check=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        return {
            "success": True,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
```

**Risk Level:** 🔴 **HIGH**

**Attack Vector:**
If the remote server is compromised or malicious, it could inject arbitrary commands:

```json
{
  "action": "adjust_power",
  "setpoint_power_w": "100; rm -rf /; echo 100"
}
```

While `setpoint_power_w` is used as an integer in the current code, the `shell=True` parameter creates a general vulnerability in the command execution system.

**Commands Executed:**
- `lspci | grep -i vga` (read-only - safe)
- `rocm-smi -d {gpu_id} --setpowerlimit {watts}` (hardware control - dangerous if exploited)

**Recommendation:**
```python
# Use argument list instead of shell=True
result = subprocess.run(
    ["rocm-smi", "-d", str(gpu_id), "--setpowerlimit", str(clamped_w)],
    shell=False,  # ✅ SAFE
    check=True,
    capture_output=True,
    text=True,
    timeout=30
)
```

---

### 4. Hardcoded Paths & Missing Validation

**File:** `reckon_service/config_manager.py` (line 14)

**Issue:**
```python
load_dotenv(dotenv_path='/home/radmin/scripts/.env')
```

**Risk Level:** 🟠 **LOW-MEDIUM**

**Impact:**
- Fails if directory structure changes
- Hardcoded username (`radmin`)
- Not portable across systems

**Recommendation:**
```python
import os
from pathlib import Path

# Use relative path from script location
script_dir = Path(__file__).parent.parent
dotenv_path = script_dir / '.env'
load_dotenv(dotenv_path=dotenv_path)
```

---

### 5. Exposed API Tokens in Plaintext

**File:** `reckon_service/secrets.json`

**Issue:** Contains unencrypted JWT token

**Content:**
```json
{
  "api_token": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjbi0x..."
}
```

**Risk Level:** 🟠 **MEDIUM**

**Impact:**
- If file permissions not set to `600`, any user can read GPU control credentials
- Token visible in plaintext
- No encryption at rest

**Recommendation:**
```bash
# Set restrictive permissions
chmod 600 secrets.json

# Or use encrypted storage
pip install cryptography
# Encrypt with AES-256
```

---

### 6. No Input Validation on Server Responses

**File:** `reckon_service/main.py` (lines 196-199)

**Issue:**
```python
if data.get("action") == "adjust_power":
    target_w = data.get("setpoint_power_w", 1500)  # No type checking
    set_power_limit(gpu_id, target_w)
```

**Risk Level:** 🟡 **LOW**

**Impact:**
- Malformed server response could crash with type error
- Default value (1500W) is outside clamped range (100-210W)

**Recommendation:**
```python
if data.get("action") == "adjust_power":
    target_w = data.get("setpoint_power_w")
    if not isinstance(target_w, (int, float)):
        print(f"[ERROR] Invalid power value: {target_w}")
        return
    set_power_limit(gpu_id, int(target_w))
```

---

### 7. Missing Rate Limiting

**Issue:** No throttling or rate limiting on power adjustment commands

**Risk Level:** 🟠 **MEDIUM**

**Impact:**
- Server can send unlimited power adjustment commands
- Rapid power changes could stress hardware
- No exponential backoff for network failures

**Recommendation:**
```python
import time
from collections import deque

class RateLimiter:
    def __init__(self, max_calls: int, period: int):
        self.max_calls = max_calls
        self.period = period
        self.calls = deque()
    
    def allow(self) -> bool:
        now = time.time()
        # Remove old calls
        while self.calls and self.calls[0] < now - self.period:
            self.calls.popleft()
        
        if len(self.calls) < self.max_calls:
            self.calls.append(now)
            return True
        return False

# Usage: max 5 power changes per 300 seconds
power_limiter = RateLimiter(max_calls=5, period=300)

if data.get("action") == "adjust_power":
    if not power_limiter.allow():
        print("[WARNING] Rate limit exceeded for power adjustments")
        return
    # ... proceed with power adjustment
```

---

## What It DOESN'T Do (Reassuring)

✅ **NOT found:**
- ❌ No code to lock/disable miners
- ❌ No code to prevent other processes from accessing GPUs
- ❌ No hardware-locking mechanisms
- ❌ No permanent hardware modifications
- ❌ No rootkit/backdoor patterns
- ❌ No data exfiltration beyond telemetry
- ❌ No cryptocurrency wallet stealing
- ❌ No unauthorized mining
- ❌ No file encryption (ransomware)

---

## Systemd Service Configuration

**File:** `reckon-client.service`

```ini
[Unit]
Description=RECKON GPU Monitoring Client
After=network.target

[Service]
Type=simple
User=radmin
WorkingDirectory=/home/radmin/scripts/gpu_monitoring_service/reckon_service
EnvironmentFile=/home/radmin/scripts/gpu_monitoring_service/.env
ExecStart=/home/radmin/scripts/gpu_monitoring_service/venv/bin/python main.py

# Watchdog and restart settings
Restart=always
RestartSec=10
WatchdogSec=120

[Install]
WantedBy=multi-user.target
```

**Analysis:**
- Runs as non-root user `radmin` (✅ good security practice)
- `Restart=always` means systemd will always restart the service (⚠️ persistent)
- `WatchdogSec=120` means systemd expects watchdog notifications
- Dual-layer watchdog (systemd + internal) ensures high availability

**Security Note:** The `Restart=always` policy means the service will persistently restart, making it difficult to stop without `systemctl stop`. This is by design for reliability but could be concerning if the service is compromised.

---

## Answer to Primary Question

### "Is there something to get the hardware locked for some reason?"

**Short Answer:** NO direct hardware locking mechanism exists in the code.

**Detailed Answer:**

1. **Miner Software (lolMiner):** 
   - ✅ Clean, legitimate mining software
   - ❌ No hardware locking code
   - ❌ No unauthorized operations

2. **Monitoring Service (reckon_service):**
   - ⚠️ Can remotely adjust GPU power limits (100-210W)
   - 🔴 Aggressive watchdog restart could potentially leave GPU in inconsistent state
   - ❌ Does NOT lock GPU access or prevent other processes from using GPUs
   - ❌ Does NOT disable hardware

3. **Potential "Locking" Scenarios:**
   - **Power Throttling:** Remote server could reduce GPU power to minimum (100W), severely limiting mining performance - but this is **throttling, not locking**
   - **Restart Issues:** Watchdog's forceful `os.execv()` restart without cleanup could potentially leave GPU processes orphaned, requiring manual intervention - this is a **bug, not intentional locking**
   - **Service Persistence:** `Restart=always` in systemd makes the monitoring service persistent, but doesn't prevent GPU usage

4. **What Would Constitute "Hardware Locking":**
   - Disabling GPU drivers (not present)
   - Blocking GPU access via permissions (not present)
   - Crashing GPU firmware (not present)
   - Encrypting/corrupting GPU state (not present)
   - Setting exclusive process locks (not present)

**Conclusion:** There is NO malicious hardware-locking mechanism. The service can throttle performance via power limits, but this is transparent and reversible.

---

## Risk Assessment

### Overall Risk Level: 🟠 MEDIUM

| Risk Category | Level | Rationale |
|--------------|-------|-----------|
| **Hardware Locking** | 🟢 LOW | No locking mechanisms found |
| **Performance Throttling** | 🟠 MEDIUM | Remote power control possible |
| **System Stability** | 🔴 HIGH | Aggressive restart without cleanup |
| **Command Injection** | 🔴 HIGH | `shell=True` vulnerability |
| **Data Security** | 🟠 MEDIUM | Plaintext tokens, no encryption |
| **Authentication** | 🟠 MEDIUM | Token-based, no validation |
| **Availability** | 🟢 LOW | High availability by design |

---

## Recommendations

### High Priority (Address Immediately)

1. **Remove `shell=True` from subprocess calls**
   ```python
   # Change from:
   subprocess.run(command, shell=True, ...)
   
   # To:
   subprocess.run(["rocm-smi", "-d", gpu_id, "--setpowerlimit", str(watts)], shell=False, ...)
   ```

2. **Implement graceful shutdown in watchdog**
   ```python
   # Add cleanup before restart
   def graceful_shutdown():
       cleanup_gpu_state()
       close_network_connections()
       save_state()
       sys.exit(1)  # Let systemd restart
   ```

3. **Add rate limiting for power adjustments**
   - Max 5 changes per 5 minutes
   - Log all power adjustment attempts

4. **Validate all server responses**
   ```python
   # Type checking and range validation
   if not isinstance(target_w, (int, float)) or target_w < 0:
       raise ValueError("Invalid power value")
   ```

### Medium Priority (Address Soon)

5. **Encrypt secrets.json**
   - Use AES-256 encryption at rest
   - Or use system keyring (e.g., `keyring` Python library)

6. **Set proper file permissions**
   ```bash
   chmod 600 secrets.json
   chmod 600 .env
   ```

7. **Fix hardcoded paths**
   - Use relative paths from script location
   - Make paths configurable via environment variables

8. **Add command authentication**
   - Sign commands from server
   - Verify signatures before execution

### Low Priority (Nice to Have)

9. **Add audit logging**
   - Log all power adjustments to separate file
   - Include timestamp, previous value, new value, requester

10. **Implement command throttling**
    - Exponential backoff for network failures
    - Configurable rate limits per command type

11. **Add systemd security hardening**
    ```ini
    [Service]
    ProtectSystem=strict
    ProtectHome=true
    PrivateTmp=true
    NoNewPrivileges=true
    ReadOnlyPaths=/
    ReadWritePaths=/home/radmin/scripts/gpu_monitoring_service
    ```

12. **Document watchdog timeout behavior**
    - Add warnings about aggressive restart
    - Recommend timeout values based on use case

---

## Monitoring and Detection

### Signs of Compromise or Issues

Monitor logs for these patterns:

1. **Rapid power adjustments:**
   ```
   [POWER] Setting power limit: 210W
   [POWER] Setting power limit: 100W
   [POWER] Setting power limit: 210W
   ```

2. **Frequent watchdog restarts:**
   ```
   [WATCHDOG] ALERT! No heartbeat for 125s. Restarting...
   ```

3. **Unusual power values in requests:**
   ```
   [ERROR] Invalid power value: -1
   [ERROR] Invalid power value: "malicious"
   ```

4. **Failed command execution:**
   ```
   [ERROR] Command failed: rocm-smi -d 0 --setpowerlimit 100
   ```

### Recommended Monitoring

```bash
# Watch for power adjustments
journalctl -u reckon-client -f | grep -i power

# Watch for watchdog restarts
journalctl -u reckon-client -f | grep -i watchdog

# Monitor GPU power in real-time
watch -n 1 rocm-smi --showpower
```

---

## Conclusion

This GPU monitoring service does **NOT contain malicious hardware-locking code**. However, it does have several security vulnerabilities that should be addressed:

1. ✅ **Miner software is clean** - lolMiner is legitimate, no backdoors
2. ⚠️ **Remote power control exists** - but clamped to safe limits
3. 🔴 **Security improvements needed** - command injection, restart mechanism, authentication
4. 🟠 **Not a security disaster** - but needs hardening before production use

The service appears to be designed for legitimate GPU monitoring and power management in a mining operation, with room for security improvements.

---

## References

- lolMiner: https://github.com/Lolliedieb/lolMiner-releases
- ROCm SMI: https://github.com/RadeonOpenCompute/rocm_smi_lib
- Python subprocess security: https://docs.python.org/3/library/subprocess.html#security-considerations
- Systemd service hardening: https://www.freedesktop.org/software/systemd/man/systemd.exec.html

---

**Report Generated:** 2026-02-09  
**Analyst:** GitHub Copilot Security Analysis  
**Version:** 1.0
