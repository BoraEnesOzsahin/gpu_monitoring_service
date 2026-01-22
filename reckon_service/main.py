import time
import requests
import json
import gpu_driver
import config_manager

"""
RECKON Client - Main Service
Purpose: Implements the Client State Machine (Initializing -> Running).
Reference: Protocol Doc Section 2 and 3 
"""

# --- CONSTANTS ---
DEFAULT_HEARTBEAT_INTERVAL = 60  # Seconds
RETRY_DELAY = 60                 # Wait time when server sends 202 Accepted


def apply_power_limit(target_total_watts, gpu_count):
    """
    Distributes power but clamps it to hardware limits.
    SAFETY: Never exceeds 150W per card.
    """
    if gpu_count == 0:
        return

    # 1. Hardware Limit (TDP of Cards (right now RX5600) it could be dynamic depending on the card.)
    MAX_PER_GPU_W = 210 
    MIN_PER_GPU_W = 90  # Minimum required

    # 2. Calculate the Watt per gpu
    requested_per_card = int(target_total_watts / gpu_count)
    
    # 3. (Clamping Logic)
    # If desired > 150 ise, 150 yap.
    # If desired < 50 ise, 50 yap.
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
    """
    print("\n[STATE] INITIALIZING...")
    
    hardware_id = config_manager.get_hardware_id()
    inventory = gpu_driver.get_gpu_inventory()
    
    payload = {
        "hardware_id": hardware_id,
        "model": "RECKON_RIG_GEN1",
        "fw_version": "1.0.0",
        "capabilities": {
            "max_power_w": 900, # Physical max
            "min_power_w": 540
        },
        "gpu_inventory": inventory
    }

    url = f"{config_manager.EMS_API_URL}/api/v1/nodes/initialize"
    
    while True:
        try:
            print(f"Sending registration request to {url}...")
            response = requests.post(url, json=payload, timeout=10)
            
            # CASE 1: 200 OK -> Approved
            if response.status_code == 200:
                data = response.json()
                print("SUCCESS: Node Approved!")
                config_manager.save_secrets(data["node_id"], data["api_token"])
                return data # Return config to start running
            
            # CASE 2: 202 Accepted -> Pending Approval
            elif response.status_code == 202:
                print(f"PENDING: Waiting for admin approval. Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                
            # CASE 3: Error
            else:
                print(f"ERROR: Server returned {response.status_code}. Retrying...")
                time.sleep(30)
                
        except requests.exceptions.RequestException as e:
            print(f"NETWORK ERROR: {e}. Retrying in 30s...")
            time.sleep(30)

def start_heartbeat_loop(initial_config):
    """
    Handles the RUNNING state.
    Sends telemetry and processes commands.
    """
    print("\n[STATE] RUNNING")
    
    # Load secrets (Node ID and Token)
    secrets = config_manager.load_secrets()
    if not secrets:
        print("CRITICAL: Secrets lost. Restarting initialization.")
        return # Go back to main loop
        
    node_id = secrets["node_id"]
    token = secrets["api_token"]
    
    # Set interval from server config or default
    interval = initial_config.get("initial_command", {}).get("heartbeat_interval", DEFAULT_HEARTBEAT_INTERVAL)
    
    url = f"{config_manager.EMS_API_URL}/api/v1/nodes/heartbeat"
    headers = {"Authorization": f"Bearer {token}"}

    while True:
        try:
            # 1. Collect Telemetry
            telemetry = gpu_driver.get_gpu_telemetry()
            
            # 2. Prepare Payload [cite: 162]
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
                
                # Check for Commands [cite: 199]
                if data.get("command") == "adjust_power":
                    target_w = data.get("setpoint_power_w", 1500)
                    print(f"COMMAND RECEIVED: Adjust Power to {target_w}W")
                    apply_power_limit(target_w, len(telemetry))
                
                # Update interval if server requests
                if "next_heartbeat" in data:
                    interval = data["next_heartbeat"]

            elif response.status_code == 401:
                print("UNAUTHORIZED: Token revoked. Deleting secrets and restarting.")
                config_manager.delete_secrets()
                return # Break loop to re-initialize

            else:
                print(f"Server warning: {response.status_code}")

        except requests.exceptions.RequestException as e:
            print(f"Network Error: {e}")
        
        # Wait for next beat
        time.sleep(interval)

def main():
    """
    Main State Machine Entry Point
    """
    print("--- RECKON GPU CLIENT STARTED ---")
    
    while True:
        # Check if we are already registered
        secrets = config_manager.load_secrets()
        
        if secrets:
            # If we have a token, jump straight to RUNNING
            print("Found saved credentials. Resuming operation...")
            # We create a dummy initial config since we are resuming
            dummy_config = {"initial_command": {"heartbeat_interval": DEFAULT_HEARTBEAT_INTERVAL}}
            start_heartbeat_loop(dummy_config)
        else:
            # If no token, go to INITIALIZING
            initial_config = register_node()
            start_heartbeat_loop(initial_config)

if __name__ == "__main__":
    main()
