# RECKON GPU Monitoring Service

A lightweight monitoring and energy management service for AMD GPU mining rigs.

## ⚠️ What This Service Does (and Doesn't Do)

### ✅ What It DOES:
- **Monitors GPU metrics**: temperature, power consumption, GPU load
- **Reports telemetry** to a remote Energy Management System (EMS) server
- **Adjusts GPU power limits** remotely (within safe hardware limits: 100-210W)
- **Self-recovery**: includes watchdog for automatic service restart

### ❌ What It Does NOT Do:
- **Does NOT stop or terminate** any processes
- **Does NOT block or prevent** mining operations
- **Does NOT lock GPU devices** or restrict access
- **Does NOT interfere** with GPU compute operations
- **Does NOT kill mining software**

> **For a detailed security analysis**, see [SECURITY_ANALYSIS.md](./SECURITY_ANALYSIS.md)

## Purpose

This service is designed for **energy cost optimization** in GPU mining operations:
- Dynamic power allocation based on electricity prices
- Peak demand management
- Remote monitoring of mining rig health
- Energy efficiency optimization

**Key Feature**: While the service can reduce GPU power limits (which may lower hashrates), it **never stops or blocks mining processes**. Mining software continues to run at the adjusted power levels.

## Architecture

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
│  │  │ If no feed for  │    │ Sends telemetry         │   │  │
│  │  │ 120s → restart  │    │ Receives commands       │   │  │
│  │  └─────────────────┘    └─────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   EMS Server     │
                    │  (Remote Cloud)  │
                    └──────────────────┘
```

## Components

- **main.py**: Core service logic, state machine, heartbeat loop
- **gpu_driver.py**: Hardware interface (uses `rocm-smi` and `lspci`)
- **config_manager.py**: Configuration and credential management
- **watchdog.py**: Internal process monitoring for self-recovery

## System Requirements

- Linux with systemd
- Python 3.7+
- AMD GPUs with ROCm drivers
- `rocm-smi` utility installed
- Network access to EMS server

## Quick Start

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd gpu_monitoring_service
   ```

2. **Configure the service**
   ```bash
   cp .env.example .env
   nano .env  # Edit with your EMS server URL
   ```

3. **Install dependencies**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Test manually**
   ```bash
   cd reckon_service
   python main.py
   ```

5. **Install as systemd service**
   ```bash
   sudo ./scripts/install-service.sh
   sudo systemctl start reckon-client
   ```

For detailed installation instructions, see [INSTALL.md](./INSTALL.md)

## Configuration

Create a `.env` file with these settings:

```bash
# EMS Server Configuration
EMS_API_URL=http://your-ems-server:8000

# Client Configuration
DEFAULT_HEARTBEAT_INTERVAL=60      # Seconds between heartbeats
RETRY_DELAY=60                     # Seconds to wait before retrying

# Watchdog Configuration
WATCHDOG_TIMEOUT=120               # Seconds before considering service hung

# Secrets file path
SECRETS_FILE=secrets.json          # Path to store API credentials
```

## GPU Power Management

The service can adjust GPU power limits via the `rocm-smi --setpowerlimit` command.

**Safety features:**
- Hardware maximum: 210W per GPU (for RX5600)
- Hardware minimum: 100W per GPU
- All requested values are clamped to this safe range
- Never exceeds hardware TDP

**Impact on mining:**
- Mining processes continue to run
- Reducing power limits may decrease hashrate
- This is performance throttling, NOT process blocking

## Commands

### Service Management

```bash
# Start the service
sudo systemctl start reckon-client

# Stop the service
sudo systemctl stop reckon-client

# Restart the service
sudo systemctl restart reckon-client

# Check status
sudo systemctl status reckon-client

# Enable on boot
sudo systemctl enable reckon-client
```

### Viewing Logs

```bash
# View recent logs
sudo journalctl -u reckon-client

# Follow logs in real-time
sudo journalctl -u reckon-client -f

# View logs since last boot
sudo journalctl -u reckon-client -b
```

## API Protocol

The service implements a simple HTTP API protocol:

### 1. Node Registration (Initialization)
```http
POST /api/v1/nodes/initialize
```
Sends GPU inventory and receives authentication token.

### 2. Heartbeat (Running State)
```http
POST /api/v1/nodes/heartbeat
Authorization: Bearer <token>
```
Sends telemetry and receives commands.

### Commands Supported

- `adjust_power`: Adjusts GPU power limits
  ```json
  {
    "command": "adjust_power",
    "setpoint_power_w": 900
  }
  ```

**That's it!** Only one command type is supported. No process control, no GPU locking, no mining blocking.

## Telemetry Data Format

Example telemetry payload:
```json
{
  "node_id": "aa:bb:cc:dd:ee:ff",
  "timestamp": "2026-02-12T06:59:15Z",
  "metrics": {
    "status": "working",
    "system_temp_c": 40
  },
  "gpu_telemetry": [
    {
      "gpu_id": "gpu_0",
      "load_pct": 100.0,
      "temp_c": 65.0,
      "power_draw_w": 150.0,
      "current_performance": {
        "value": 41.0,
        "unit": "MH/s"
      }
    }
  ]
}
```

## Security Considerations

1. **Authentication**: Service uses token-based authentication
2. **Credentials**: Stored in `secrets.json` - keep this file secure
3. **Network**: Service requires outbound access to EMS server
4. **Privileges**: May require elevated privileges for power limit adjustment
5. **Data Privacy**: Telemetry data includes GPU metrics only (no personal data)

**Important**: The service does NOT have the capability to:
- Access or modify mining software
- Terminate or control other processes
- Lock or reserve GPU resources
- Modify system configuration (beyond power limits)

## Troubleshooting

### Service won't start
- Check `.env` file exists and is valid
- Verify EMS server URL is correct
- Ensure Python dependencies are installed
- Review logs: `sudo journalctl -u reckon-client -n 50`

### GPUs not detected
- Verify ROCm drivers are installed
- Check `rocm-smi` command works: `rocm-smi --showtemp`
- Ensure user has GPU access permissions

### Watchdog keeps restarting service
- Increase `WATCHDOG_TIMEOUT` in `.env`
- Check network connectivity to EMS server
- Verify heartbeat interval is reasonable

### Power limits not applying
- Verify elevated privileges if required
- Check `rocm-smi --setpowerlimit` command works manually
- Review logs for error messages

## FAQ

**Q: Will this stop my mining?**  
A: No. The service only monitors GPUs and adjusts power limits. Mining processes continue to run.

**Q: Can someone remotely shut down my GPUs?**  
A: No. The service can only adjust power limits within safe ranges (100-210W). GPUs remain operational.

**Q: Does this interfere with my mining software?**  
A: No. The service does not interact with mining processes. It only monitors GPU metrics via `rocm-smi`.

**Q: What happens if the EMS server is unreachable?**  
A: The service continues to retry connection. Mining operations are unaffected.

**Q: Can I run this alongside mining software?**  
A: Yes. The service has minimal resource overhead and does not interfere with other GPU workloads.

**Q: How do I disable power control?**  
A: Configure your EMS server to never send power adjustment commands, or modify the code to ignore them.

## Development

### Project Structure
```
gpu_monitoring_service/
├── reckon_service/          # Main service code
│   ├── main.py             # Service entry point
│   ├── gpu_driver.py       # GPU interface
│   ├── config_manager.py   # Configuration
│   └── watchdog.py         # Self-monitoring
├── scripts/
│   └── install-service.sh  # Service installer
├── .env.example            # Example configuration
├── requirements.txt        # Python dependencies
├── reckon-client.service   # Systemd service file
├── INSTALL.md             # Installation guide
├── SECURITY_ANALYSIS.md   # Security analysis
└── README.md              # This file
```

### Running Tests

Test GPU detection:
```bash
cd reckon_service
python gpu_driver.py
```

Test configuration:
```bash
cd reckon_service
python config_manager.py
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

[Add your license here]

## Support

For issues or questions:
1. Check this README and [INSTALL.md](./INSTALL.md)
2. Review [SECURITY_ANALYSIS.md](./SECURITY_ANALYSIS.md) for security questions
3. Check logs: `sudo journalctl -u reckon-client -f`
4. Open an issue on the repository

---

## Summary: Process Interference

**To directly answer the question: "Is there anything to interrupt or lock the GPUs or block any kind of mining process?"**

**NO** - This codebase contains:
- ❌ Zero process termination logic
- ❌ Zero GPU locking mechanisms  
- ❌ Zero mining process blocking
- ❌ Zero compute resource reservation
- ✅ Only monitoring and power limit adjustment

The complete functionality is:
1. Monitor GPU metrics (read-only)
2. Report to EMS server
3. Adjust power limits when commanded (within safe ranges)

**That's all.** No mining interference, no process control, no GPU locking.

For a detailed security analysis with code examples and verification steps, see [SECURITY_ANALYSIS.md](./SECURITY_ANALYSIS.md).
