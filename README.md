# GPU Monitoring Service

A GPU monitoring and management service for mining operations with remote power control capabilities.

## ⚠️ Security Notice

**Before deploying this service, please read [SECURITY_ANALYSIS.md](SECURITY_ANALYSIS.md) for important security information.**

### Quick Security Summary

✅ **Good News:**
- No malicious hardware-locking mechanisms detected
- Miner software (lolMiner) is legitimate and clean
- Service runs as non-root user

⚠️ **Areas of Concern:**
- Remote power control of GPUs (100-210W range)
- Shell command execution vulnerability (`shell=True`)
- Aggressive process restart without cleanup
- Plaintext authentication tokens

🔴 **Action Required:**
- Review and implement security recommendations in SECURITY_ANALYSIS.md
- Harden subprocess calls (remove `shell=True`)
- Implement graceful shutdown mechanism
- Encrypt secrets.json file

## Components

### 1. miner_software/
Contains lolMiner v1.98 cryptocurrency mining software:
- **Binary:** `lolMiner` (legitimate GPU mining software)
- **Scripts:** 25+ mining scripts for various cryptocurrencies
- **Status:** ✅ Clean, no malicious code detected

### 2. reckon_service/
Python-based GPU monitoring client:
- **main.py:** Main service loop with heartbeat and power control
- **gpu_driver.py:** GPU hardware interaction via rocm-smi
- **watchdog.py:** Process monitoring and auto-restart
- **config_manager.py:** Configuration and environment management

### 3. systemd Integration
- **reckon-client.service:** Systemd service for automatic startup
- **Dual-layer watchdog:** Internal (Python) + External (systemd)

## Installation

See [INSTALL.md](INSTALL.md) for detailed installation instructions.

Quick start:
```bash
# 1. Configure environment
cp .env.example .env
vim .env

# 2. Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Test manually
cd reckon_service
python main.py

# 4. Install as service
sudo ./scripts/install-service.sh
sudo systemctl start reckon-client
```

## Features

- 📊 Real-time GPU monitoring
- ⚡ Remote power limit adjustment (100-210W)
- 🔄 Automatic restart on failures
- 📡 Heartbeat-based health monitoring
- 🛡️ Dual-layer watchdog protection

## Architecture

```
┌─────────────────────────────────────────┐
│          Remote EMS Server               │
│  (sends power adjustment commands)       │
└──────────────────┬──────────────────────┘
                   │ HTTPS
                   │
┌──────────────────▼──────────────────────┐
│       RECKON GPU Client (systemd)        │
│  ┌────────────────────────────────────┐ │
│  │  Watchdog Thread (120s timeout)    │ │
│  └─────────────┬──────────────────────┘ │
│                │                         │
│  ┌─────────────▼──────────────────────┐ │
│  │  Main Loop:                        │ │
│  │  - Send heartbeat to server        │ │
│  │  - Receive power adjustment cmds   │ │
│  │  - Execute rocm-smi commands       │ │
│  │  - Feed watchdog                   │ │
│  └─────────────┬──────────────────────┘ │
└────────────────┼────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│         GPU Hardware (AMD)               │
│  - rocm-smi adjusts power limits        │
│  - Reports telemetry                    │
└─────────────────────────────────────────┘
```

## Configuration

Environment variables in `.env`:

```bash
# Server
EMS_API_URL=http://your-server:8000

# Heartbeat
DEFAULT_HEARTBEAT_INTERVAL=60
RETRY_DELAY=60

# Watchdog
WATCHDOG_TIMEOUT=120

# Authentication
SECRETS_FILE=secrets.json

# Power Control Security (NEW)
ALLOW_REMOTE_POWER_CONTROL=true    # Enable/disable remote power control
RATE_LIMIT_MAX_CHANGES=5           # Max power changes in time period
RATE_LIMIT_PERIOD_SECONDS=300      # Time period (5 minutes)
POWER_AUDIT_LOG=power_audit.log    # Audit log location
```

**Power Control Settings:**
- `ALLOW_REMOTE_POWER_CONTROL` - Master switch for remote power control (true/false)
- `RATE_LIMIT_MAX_CHANGES` - Maximum power adjustments allowed (default: 5)
- `RATE_LIMIT_PERIOD_SECONDS` - Time window for rate limiting (default: 300 = 5 minutes)
- `POWER_AUDIT_LOG` - Path to audit log file

See [POWER_SECURITY_GUIDE.md](POWER_SECURITY_GUIDE.md) for detailed configuration guide.

## Monitoring

```bash
# View logs
sudo journalctl -u reckon-client -f

# Check status
sudo systemctl status reckon-client

# Monitor GPU power
watch -n 1 rocm-smi --showpower
```

## Security

### Current Security Measures
- Non-root execution
- Power limit clamping (100-210W)
- Command timeout (30s)
- JWT token authentication
- **NEW: Comprehensive input validation**
- **NEW: Rate limiting (5 changes per 5 minutes)**
- **NEW: Audit logging for all power adjustments**
- **NEW: Secure command execution (no shell injection)**
- **NEW: Feature toggle to disable remote power control**

### Security Improvements (Implemented ✅)

**Power Control Security** - See [POWER_SECURITY_GUIDE.md](POWER_SECURITY_GUIDE.md)

1. ✅ **Input Validation** - Comprehensive type and range checks
2. ✅ **Rate Limiting** - Maximum 5 power changes per 5 minutes
3. ✅ **Audit Logging** - All adjustments logged to `power_audit.log`
4. ✅ **Command Injection Prevention** - Secure subprocess execution
5. ✅ **Feature Toggle** - `ALLOW_REMOTE_POWER_CONTROL` setting

**Watchdog Graceful Shutdown** - See [WATCHDOG_GRACEFUL_SHUTDOWN.md](WATCHDOG_GRACEFUL_SHUTDOWN.md)

6. ✅ **Graceful Shutdown** - Replaced `os.execv()` with cleanup mechanism
7. ✅ **Signal Handlers** - Proper SIGTERM and SIGINT handling
8. ✅ **Resource Cleanup** - GPU state, connections released properly
9. ✅ **Systemd Integration** - Let systemd handle restart

See [SECURITY_FIX_SUMMARY.md](SECURITY_FIX_SUMMARY.md) for power control details.  
See [WATCHDOG_GRACEFUL_SHUTDOWN.md](WATCHDOG_GRACEFUL_SHUTDOWN.md) for watchdog details.

### Known Security Issues

See [SECURITY_ANALYSIS.md](SECURITY_ANALYSIS.md) for complete details:

1. ~~**Command Injection Risk**~~ - ✅ FIXED (secure subprocess calls)
2. ~~**Forceful Restart**~~ - ✅ FIXED (graceful shutdown with cleanup)
3. **Plaintext Secrets** - JWT tokens stored unencrypted (future work)
4. ~~**No Rate Limiting**~~ - ✅ FIXED (5 changes per 5 minutes)
5. ~~**No Command Validation**~~ - ✅ FIXED (comprehensive validation)

### Security Test Results

**Power Control Tests:**
```bash
# Run power security test suite
python test_power_security.py
```
**Latest Results:** 5/5 tests passed ✅
- ✓ Input Validation (10/10 cases)
- ✓ Rate Limiting
- ✓ Audit Logging
- ✓ Secure Power Adjustment
- ✓ Rate Limit Status

**Watchdog Tests:**
```bash
# Run watchdog graceful shutdown test suite
python test_watchdog_graceful.py
```
**Latest Results:** 7/7 tests passed ✅
- ✓ No execv Usage
- ✓ Shutdown Helper Functions
- ✓ Global Watchdog Functions
- ✓ Signal Handler Setup
- ✓ Watchdog Stop
- ✓ Feed Prevents Shutdown
- ✓ Timeout Graceful Shutdown
- ✓ Rate Limit Status

## FAQ

### Q: Does this service lock GPU hardware?

**A: NO.** The service can adjust GPU power limits (throttling performance) but does NOT lock hardware access or prevent other processes from using GPUs. See detailed analysis in [SECURITY_ANALYSIS.md](SECURITY_ANALYSIS.md).

### Q: Is lolMiner safe?

**A: YES.** lolMiner v1.98 is legitimate, open-source cryptocurrency mining software with no malicious code detected. Full analysis in [SECURITY_ANALYSIS.md](SECURITY_ANALYSIS.md).

### Q: Can the remote server damage my hardware?

**A: Unlikely, but possible.** Power limits are clamped to 100-210W (safe range for most GPUs), but rapid power changes could stress hardware. The service needs rate limiting (see security recommendations).

### Q: Why does the watchdog restart so aggressively?

**A:** The watchdog uses `os.execv()` for immediate restart to maintain high availability. However, this lacks graceful shutdown. See security recommendations for improvements.

### Q: Is the remote power control legitimate?

**A: YES, by design.** This is an intentional feature for energy management in mining operations. The service is designed to allow remote power optimization. However, ensure your EMS server is secure.

## Troubleshooting

### Service Won't Start
```bash
# Check logs
sudo journalctl -u reckon-client -n 50

# Verify configuration
cat .env

# Check Python environment
source venv/bin/activate
python -c "import requests; print('OK')"
```

### Watchdog Restarting Frequently
- Increase `WATCHDOG_TIMEOUT` in `.env`
- Check network connectivity to EMS server
- Review heartbeat interval vs. timeout ratio

### Power Adjustments Not Working
```bash
# Test rocm-smi manually
rocm-smi -d 0 --setpowerlimit 150

# Check user permissions
groups $USER | grep -i video
```

## Contributing

Before contributing, please:
1. Read [SECURITY_ANALYSIS.md](SECURITY_ANALYSIS.md)
2. Review open security issues
3. Follow secure coding practices
4. Test changes thoroughly

## License

See LICENSE file for details.

## Support

For issues or questions:
1. Check [SECURITY_ANALYSIS.md](SECURITY_ANALYSIS.md)
2. Review [INSTALL.md](INSTALL.md)
3. Search existing issues
4. Open a new issue with details

## Credits

- lolMiner by Lolliedieb: https://github.com/Lolliedieb/lolMiner-releases
- ROCm by AMD: https://github.com/RadeonOpenCompute/ROCm
