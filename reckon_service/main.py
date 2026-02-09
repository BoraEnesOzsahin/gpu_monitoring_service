import sys
sys.stdout.reconfigure(line_buffering=True)
import time
import requests
import json
import os
import gpu_driver
import config_manager
import watchdog
import power_control

"""
RECKON Client - Main Service
Purpose: Implements the Client State Machine (Initializing -> Running).
Reference: Protocol Doc Section 2 and 3 
"""

# --- CONSTANTS ---
DEFAULT_HEARTBEAT_INTERVAL = config_manager.DEFAULT_HEARTBEAT_INTERVAL
RETRY_DELAY = config_manager.RETRY_DELAY

def apply_power_limit(target_total_watts, gpu_count):
    """
    DEPRECATED: Use power_control.apply_power_limit_secure() instead.
    This function is kept for backward compatibility but delegates to the secure implementation.
    
    Distributes power but clamps it to hardware limits.
    SAFETY: Never exceeds 210W per card, minimum 100W per card.
    """
    print(f"[DEPRECATED] apply_power_limit called, delegating to secure implementation")
    
    # Delegate to the secure power control module
    success, message = power_control.apply_power_limit_secure(
        target_total_watts, 
        gpu_count, 
        gpu_driver
    )
    
    if not success:
        print(f"[POWER] Failed: {message}")
    
    return success

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
            # Feed watchdog during registration to prevent timeout
            watchdog.feed_watchdog()
            
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

    while True:
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
                
                # Handle power adjustment command
                if data.get("command") == "adjust_power":
                    target_w = data.get("setpoint_power_w")
                    
                    # Validate that setpoint_power_w is present and valid
                    if target_w is None:
                        print(f"[WARNING] Power adjustment command missing 'setpoint_power_w' field")
                    else:
                        print(f"[COMMAND] Received: Adjust Power to {target_w}W total")
                        
                        # Apply power limit securely
                        success = apply_power_limit(target_w, len(telemetry))
                        
                        if success:
                            print(f"[POWER] Successfully adjusted power")
                            # Log rate limit status
                            rate_status = power_control.get_rate_limit_status()
                            print(f"[POWER] Rate limit: {rate_status['current_count']}/{rate_status['max_allowed']} "
                                  f"in last {rate_status['period_seconds']}s")
                        else:
                            print(f"[POWER] Power adjustment rejected or failed")
                # Burada interval değiştirilmesin!

            elif response.status_code == 401:
                print("UNAUTHORIZED: Token revoked. Deleting secrets and restarting.")
                config_manager.delete_secrets()
                return # Break loop to re-initialize

            else:
                print(f"Server warning: {response.status_code}")

        except requests.exceptions.RequestException as e:
            print(f"Network Error: {e}")
        
        time.sleep(interval)






def main():
    """
    Main State Machine Entry Point
    """
    print("--- RECKON GPU CLIENT STARTED ---")
    
    # Initialize watchdog
    try:
        watchdog_timeout = int(os.getenv("WATCHDOG_TIMEOUT", "120"))
    except ValueError:
        print("Warning: Invalid WATCHDOG_TIMEOUT value. Using default of 120 seconds.")
        watchdog_timeout = 120
    
    watchdog.init_watchdog(watchdog_timeout)
    
    while True:
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
            start_heartbeat_loop(initial_config)

if __name__ == "__main__":
    main()
