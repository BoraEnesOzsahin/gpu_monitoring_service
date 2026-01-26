# RECKON GPU Monitoring Service - Installation Guide

## Overview

This guide explains how to set up and run the RECKON GPU monitoring service with the comprehensive watchdog system for maximum reliability.

## Architecture

The RECKON client uses a dual-layer watchdog system for maximum reliability:

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

### Components

1. **Internal Watchdog** (`reckon_service/watchdog.py`)
   - Monitors the service from within the Python process
   - Detects frozen threads, infinite loops, deadlocks
   - Automatically restarts the process if no heartbeat received within timeout
   - Default timeout: 120 seconds

2. **Systemd Service** (`reckon-client.service`)
   - External process monitoring
   - Restarts service on crashes, OOM kills, or unexpected exits
   - Automatic restart on system reboot
   - Logs to systemd journal

## Prerequisites

- Linux system with systemd
- Python 3.7+
- GPU hardware with drivers installed
- Network access to the EMS server

## Step-by-Step Installation

### 1. Configure Environment Variables

Copy the example configuration file:

```bash
cp .env.example .env
```

Edit `.env` and update the values:

```bash
# EMS Server Configuration
EMS_API_URL=http://your-ems-server:8000

# Client Configuration
DEFAULT_HEARTBEAT_INTERVAL=60
RETRY_DELAY=60

# Watchdog Configuration
WATCHDOG_TIMEOUT=120

# Secrets file path
SECRETS_FILE=secrets.json
```

**Configuration Options:**

- `EMS_API_URL`: URL of your EMS server
- `DEFAULT_HEARTBEAT_INTERVAL`: Seconds between heartbeats (default: 60)
- `RETRY_DELAY`: Seconds to wait before retrying failed operations (default: 60)
- `WATCHDOG_TIMEOUT`: Seconds before watchdog considers service unresponsive (default: 120)
- `SECRETS_FILE`: Path to store authentication credentials (default: secrets.json)

### 2. Install Python Dependencies

Create a virtual environment and install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Test the Service Manually

Before installing as a systemd service, test the service manually:

```bash
cd reckon_service
python main.py
```

You should see output like:

```
--- RECKON GPU CLIENT STARTED ---
[WATCHDOG] Started with 120s timeout
[STATE] INITIALIZING...
Sending registration request to http://your-ems-server:8000/api/v1/nodes/initialize...
```

Press `Ctrl+C` to stop the test run.

### 4. Install the Systemd Service

**Important:** Before running the installer, edit the `reckon-client.service` file to match your system paths:

```ini
[Service]
User=your-username
WorkingDirectory=/path/to/your/gpu_monitoring_service/reckon_service
EnvironmentFile=/path/to/your/gpu_monitoring_service/.env
ExecStart=/path/to/your/gpu_monitoring_service/venv/bin/python main.py
```

Then run the installer:

```bash
sudo ./scripts/install-service.sh
```

The installer will:
1. Copy the service file to `/etc/systemd/system/`
2. Reload the systemd daemon
3. Enable the service to start on boot

### 5. Start the Service

```bash
sudo systemctl start reckon-client
```

### 6. Verify the Service is Running

Check the service status:

```bash
sudo systemctl status reckon-client
```

You should see:

```
● reckon-client.service - RECKON GPU Monitoring Client
     Loaded: loaded (/etc/systemd/system/reckon-client.service; enabled)
     Active: active (running) since ...
```

## Managing the Service

### Start the Service

```bash
sudo systemctl start reckon-client
```

### Stop the Service

```bash
sudo systemctl stop reckon-client
```

### Restart the Service

```bash
sudo systemctl restart reckon-client
```

### Check Service Status

```bash
sudo systemctl status reckon-client
```

### Enable Service on Boot

```bash
sudo systemctl enable reckon-client
```

### Disable Service on Boot

```bash
sudo systemctl disable reckon-client
```

## Viewing Logs

### View Recent Logs

```bash
sudo journalctl -u reckon-client
```

### Follow Logs in Real-Time

```bash
sudo journalctl -u reckon-client -f
```

### View Logs Since Last Boot

```bash
sudo journalctl -u reckon-client -b
```

### View Logs with Timestamps

```bash
sudo journalctl -u reckon-client --since "1 hour ago"
```

## Watchdog System

### How It Works

The watchdog system uses two layers of protection:

#### Internal Watchdog

- Runs as a daemon thread within the Python process
- Requires regular "feed" calls from the main service loop
- If not fed within `WATCHDOG_TIMEOUT` seconds, it restarts the process
- Protects against:
  - Frozen threads
  - Infinite loops
  - Deadlocks
  - Network timeouts that hang the application

#### Systemd Watchdog

- Monitors the entire process from outside
- Automatically restarts if the process crashes or exits unexpectedly
- Protects against:
  - Segmentation faults
  - Out of memory errors
  - Unexpected process termination
  - System reboots

### Tuning the Watchdog

The watchdog timeout can be adjusted in `.env`:

```bash
# For faster detection of hangs (more aggressive)
WATCHDOG_TIMEOUT=60

# For slower networks or longer operations (more tolerant)
WATCHDOG_TIMEOUT=180
```

**Recommendation:** Keep the timeout at least 2x your `DEFAULT_HEARTBEAT_INTERVAL` to avoid false positives.

### Watchdog Events in Logs

When the watchdog triggers, you'll see log entries like:

```
[WATCHDOG] ALERT! No heartbeat for 125s. Restarting...
[WATCHDOG] Initiating restart...
--- RECKON GPU CLIENT STARTED ---
[WATCHDOG] Started with 120s timeout
```

## Troubleshooting

### Service Fails to Start

1. Check the service status:
   ```bash
   sudo systemctl status reckon-client
   ```

2. View detailed logs:
   ```bash
   sudo journalctl -u reckon-client -n 50
   ```

3. Common issues:
   - Incorrect paths in service file
   - Missing `.env` file
   - Python virtual environment not created
   - Missing dependencies

### Service Keeps Restarting

If the service continuously restarts:

1. Check for configuration errors in `.env`
2. Verify EMS server is accessible
3. Check if watchdog timeout is too aggressive
4. Review logs for error patterns

### Cannot Connect to EMS Server

1. Verify `EMS_API_URL` in `.env`
2. Check network connectivity:
   ```bash
   ping your-ems-server
   curl http://your-ems-server:8000
   ```
3. Ensure firewall allows outbound connections

### Watchdog Triggering Too Often

If the internal watchdog restarts too frequently:

1. Increase `WATCHDOG_TIMEOUT` in `.env`
2. Check if network operations are taking too long
3. Review heartbeat interval vs. timeout ratio

## Uninstalling

To remove the service:

```bash
# Stop the service
sudo systemctl stop reckon-client

# Disable from boot
sudo systemctl disable reckon-client

# Remove service file
sudo rm /etc/systemd/system/reckon-client.service

# Reload systemd
sudo systemctl daemon-reload
```

## Security Notes

- The `secrets.json` file contains authentication tokens - keep it secure
- Run the service with minimal privileges (non-root user)
- Ensure `.env` file is not world-readable
- Consider using systemd's `ProtectSystem=` and `PrivateTmp=` options for additional security

## Support

For issues or questions:
1. Check the logs first
2. Review this documentation
3. Consult the main project README
4. Open an issue on the project repository
