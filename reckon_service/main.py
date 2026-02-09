import sys
sys.stdout.reconfigure(line_buffering=True)
import time
import requests
import json
import os
import signal
import gpu_driver
import config_manager
import watchdog

"""
RECKON Client - Main Service
Purpose: Implements the Client State Machine (Initializing -> Running).
Reference: Protocol Doc Section 2 and 3 
"""

# --- CONSTANTS ---
DEFAULT_HEARTBEAT_INTERVAL = config_manager.DEFAULT_HEARTBEAT_INTERVAL
RETRY_DELAY = config_manager.RETRY_DELAY

# Infinite loop protection
MAX_REGISTRATION_RETRIES = 100  # Maximum attempts before giving up
MAX_CONSECUTIVE_HEARTBEAT_FAILURES = 50  # Maximum consecutive heartbeat failures
MAX_STATE_MACHINE_CYCLES = 10  # Maximum outer loop cycles before exit (prevents pathological restart loops)
STATE_MACHINE_CYCLE_DELAY = 30  # Seconds to wait between state machine cycles

# Graceful shutdown flag
_shutdown_requested = False

# Power limits for RX 5600 XT (6 GPUs)
MAX_PER_GPU_W = 150  # Stock TDP of RX 5600 XT
MIN_PER_GPU_W = 75   # Minimum to keep card stable under load
GPU_COUNT = 6
SYSTEM_MAX_POWER_W = GPU_COUNT * MAX_PER_GPU_W  # 900W
SYSTEM_MIN_POWER_W = GPU_COUNT * MIN_PER_GPU_W  # 450W

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global _shutdown_requested
    print(f"\n[SHUTDOWN] Received signal {signum}. Initiating graceful shutdown...")
    _shutdown_requested = True

def apply_power_limit(target_total_watts, gpu_count):
    """
    Distributes power but clamps it to hardware limits.
    SAFETY: Never exceeds 150W per card (RX 5600 XT TDP). Never below 75W per card.
    """
    if gpu_count == 0:
        return

    # 1. Hardware Limit (TDP of RX 5600 XT cards)
    # Constants defined at module level

    # 2. Calculate the Watt per gpu
    requested_per_card = int(target_total_watts / gpu_count)
    
    # 3. (Clamping Logic)
    # Clamp to hardware limits: max 150W, min 75W
    safe_limit = min(requested_per_card, MAX_PER_GPU_W)
    safe_limit = max(safe_limit, MIN_PER_GPU_W)
    
    print(f"--- POWER CONTROL ---")
    print(f" > EMS Target Total: {target_total_watts}W")
    print(f" > Calculated Per GPU: {requested_per_card}W")
    print(f" > APPLIED SAFE LIMIT: {safe_limit}W (Capped at {MAX_PER_GPU_W}W)")
    
    # Apply command with safe limit
    cmd = f"rocm-smi --setpowerlimit {safe_limit} -d all"
    result = gpu_driver.run_command(cmd)

def register_node():
    """
    Handles the INITIALIZING state.
    Sends inventory to server and waits for approval.
    Returns None if maximum retries exceeded.
    """
    print("\n[STATE] INITIALIZING...")
    
    hardware_id = config_manager.get_hardware_id()
    inventory = gpu_driver.get_gpu_inventory()
    
    payload = {
        "hardware_id": hardware_id,
        "model": "RECKON_RIG_GEN1",
        "fw_version": "1.0.0",
        "capabilities": {
            "max_power_w": SYSTEM_MAX_POWER_W,  # 6 GPUs × 150W max per card
            "min_power_w": SYSTEM_MIN_POWER_W   # 6 GPUs × 75W min per card
        },
        "gpu_inventory": inventory
    }

    url = f"{config_manager.EMS_API_URL}/api/v1/nodes/initialize"
    
    retry_count = 0
    while retry_count < MAX_REGISTRATION_RETRIES and not _shutdown_requested:
        try:
            # Feed watchdog during registration to prevent timeout
            watchdog.feed_watchdog()
            
            retry_count += 1
            print(f"Sending registration request to {url}... (Attempt {retry_count}/{MAX_REGISTRATION_RETRIES})")
            response = requests.post(url, json=payload, timeout=10)
            
            # CASE 1: 200 OK -> Approved
            if response.status_code == 200:
                data = response.json()
                print("SUCCESS: Node Approved!")
                config_manager.save_secrets(data["node_id"], data["api_token"])
                return data # Return config to start running            

            # CASE 2: 202 Accepted -> Pending Approval
            elif response.status_code == 202:
                print("202 body:", response.text)

                data = {}
                try:
                    data = response.json()  # server should return node_id here
                except Exception:
                    pass

                node_id = data.get("node_id")
                if node_id:
                    # save node_id locally even without token (implement this)
                    config_manager.save_pending_node_id(node_id)

                print(f"PENDING: Waiting for admin approval. Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                
            # CASE 3: Error
            else:
                print(f"ERROR: Server returned {response.status_code}. Retrying...")
                time.sleep(30)
                
        except requests.exceptions.RequestException as e:
            print(f"NETWORK ERROR: {e}. Retrying in 30s...")
            time.sleep(30)
    
    # If we reach here, we've exceeded max retries or shutdown was requested
    if _shutdown_requested:
        print("[SHUTDOWN] Registration interrupted by shutdown request.")
    else:
        print(f"[ERROR] Maximum registration attempts ({MAX_REGISTRATION_RETRIES}) exceeded. Giving up.")
    return None



def approve_node(node_id):
    """
    Approves a pending node registration using the EMS API.
    Sends an approval request to the server.
    """
    import requests

    url = f"{config_manager.EMS_API_URL}/api/v1/nodes/{node_id}/approve"

    headers = {
        "Authorization": f"Bearer {api_token}"
    }

    print(f"\n[ADMIN] Approving node {node_id}...")

    try:
        response = requests.post(url, timeout=10)
        if response.status_code == 200:
            print("SUCCESS: Node approved successfully!")
            print("Response:", response.json())
        elif response.status_code == 404:
            print("ERROR: Node not found.")
        else:
            print(f"ERROR: Server returned {response.status_code}.")
            print("Response:", response.text)
    except requests.exceptions.RequestException as e:
        print(f"NETWORK ERROR: {e}.")





def start_heartbeat_loop(initial_config):
    """
    Handles the RUNNING state.
    Sends telemetry and processes commands.
    Returns when max failures exceeded or shutdown requested.
    """
    print("\n[STATE] RUNNING")
    
    # Load secrets (Node ID and Token)
    secrets = config_manager.load_secrets()
    if not secrets:
        print("CRITICAL: Secrets lost. Restarting initialization.")
        return # Go back to main loop
        
    node_id = secrets["node_id"]
    token = secrets["api_token"]
    
    # Her zaman sadece env'den al
    interval = DEFAULT_HEARTBEAT_INTERVAL
    
    url = f"{config_manager.EMS_API_URL}/api/v1/nodes/heartbeat"
    headers = {"Authorization": f"Bearer {token}"}

    consecutive_failures = 0
    while consecutive_failures < MAX_CONSECUTIVE_HEARTBEAT_FAILURES and not _shutdown_requested:
        try:
            # 1. Collect Telemetry
            telemetry = gpu_driver.get_gpu_telemetry()
            
            # 2. Prepare Payload
            payload = {
                "node_id": node_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "metrics": {
                    "status": "working",
                    "system_temp_c": 40 # Placeholder for CPU temp
                },
                "gpu_telemetry": telemetry
            }
            
            # 3. Send Heartbeat
            print(f"Sending Heartbeat... (Gpus: {len(telemetry)})")
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            # 4. Handle Response
            if response.status_code == 200:
                data = response.json()
                watchdog.feed_watchdog()
                consecutive_failures = 0  # Reset failure counter on success
                if data.get("command") == "adjust_power":
                    target_w = data.get("setpoint_power_w", SYSTEM_MAX_POWER_W)
                    print(f"COMMAND RECEIVED: Adjust Power to {target_w}W")
                    apply_power_limit(target_w, len(telemetry))
                # Burada interval değiştirilmesin!

            elif response.status_code == 401:
                print("UNAUTHORIZED: Token revoked. Deleting secrets and restarting.")
                config_manager.delete_secrets()
                return # Break loop to re-initialize

            else:
                print(f"Server warning: {response.status_code}")
                consecutive_failures += 1
                print(f"Consecutive failures: {consecutive_failures}/{MAX_CONSECUTIVE_HEARTBEAT_FAILURES}")

        except requests.exceptions.RequestException as e:
            print(f"Network Error: {e}")
            consecutive_failures += 1
            print(f"Consecutive failures: {consecutive_failures}/{MAX_CONSECUTIVE_HEARTBEAT_FAILURES}")
        
        time.sleep(interval)
    
    # If we exit the loop, log the reason
    if _shutdown_requested:
        print("[SHUTDOWN] Heartbeat loop interrupted by shutdown request.")
    elif consecutive_failures >= MAX_CONSECUTIVE_HEARTBEAT_FAILURES:
        print(f"[ERROR] Maximum consecutive failures ({MAX_CONSECUTIVE_HEARTBEAT_FAILURES}) exceeded. Exiting heartbeat loop.")
    
    return






def main():
    """
    Main State Machine Entry Point
    """
    print("--- RECKON GPU CLIENT STARTED ---")
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Initialize watchdog
    try:
        watchdog_timeout = int(os.getenv("WATCHDOG_TIMEOUT", "120"))
    except ValueError:
        print("Warning: Invalid WATCHDOG_TIMEOUT value. Using default of 120 seconds.")
        watchdog_timeout = 120
    
    watchdog.init_watchdog(watchdog_timeout)
    
    # Prevent infinite outer loop - limit total state machine cycles
    cycle_count = 0
    
    while cycle_count < MAX_STATE_MACHINE_CYCLES and not _shutdown_requested:
        cycle_count += 1
        print(f"\n[STATE MACHINE] Cycle {cycle_count}/{MAX_STATE_MACHINE_CYCLES}")
        
        # Check if we are already registered
        secrets = config_manager.load_secrets()
        
        if secrets:
            # If we have a token, jump straight to RUNNING
            print("Found saved credentials. Resuming operation...")
            # We create a dummy initial config since we are resuming
            dummy_config = {"initial_command": {"heartbeat_interval":DEFAULT_HEARTBEAT_INTERVAL
}}
            start_heartbeat_loop(dummy_config)
        else:
            # If no token, go to INITIALIZING
            initial_config = register_node()
            if initial_config:
                start_heartbeat_loop(initial_config)
            else:
                # Registration failed, exit
                print("[ERROR] Registration failed. Service will exit.")
                break
        
        # If we exit the inner loops normally (not due to shutdown), 
        # wait a bit before cycling again to avoid tight loops
        if not _shutdown_requested:
            print(f"[INFO] Waiting {STATE_MACHINE_CYCLE_DELAY} seconds before next cycle...")
            time.sleep(STATE_MACHINE_CYCLE_DELAY)
    
    # Exit cleanly
    if _shutdown_requested:
        print("\n[SHUTDOWN] Service stopped gracefully.")
    else:
        print(f"\n[EXIT] Maximum state machine cycles ({MAX_STATE_MACHINE_CYCLES}) reached. Service exiting.")
    
    print("--- RECKON GPU CLIENT STOPPED ---")

if __name__ == "__main__":
    main()
