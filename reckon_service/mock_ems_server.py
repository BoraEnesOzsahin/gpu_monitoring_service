from flask import Flask, request, jsonify
import uuid
import datetime
import os
from dotenv import load_dotenv

"""
RECKON Project - Mock EMS Server (For Testing)
Purpose: Simulates an EMS server to test the Client software.
"""

# Load environment variables from .env file
load_dotenv()

# Server configuration
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))

app = Flask(__name__)

# Simple in-memory database (persists only in RAM, cleared on restart)
REGISTERED_NODES = {}

# --- 1. INITIALIZATION ENDPOINT [Source: 100] ---
@app.route('/api/v1/nodes/initialize', methods=['POST'])
def initialize_node():
    data = request.json
    hw_id = data.get('hardware_id')
    model = data.get('model')
    gpu_count = len(data.get('gpu_inventory', []))
    
    print(f"\n[SERVER] New Registration Request Received!")
    print(f" > Device: {hw_id} ({model})")
    print(f" > GPU Count: {gpu_count}")
    
    # Simulation: Auto-approve immediately (Normally would wait for Admin approval)
    # Generate a random ID and Token
    new_node_id = f"cn-{uuid.uuid4().hex[:6]}"
    new_token = f"sk_test_{uuid.uuid4().hex[:16]}"
    
    # Save to "Database"
    REGISTERED_NODES[new_token] = new_node_id
    
    response_payload = {
        "status": "active",
        "node_id": new_node_id,
        "api_token": new_token, # [Source: 151]
        "initial_command": {
            "target_power_w": 600,   # Start with 1000W
            "heartbeat_interval": 5   # 5 seconds for faster testing
        }
    }
    
    print(f" > APPROVED. Node ID: {new_node_id}")
    return jsonify(response_payload), 200

# --- 2. HEARTBEAT ENDPOINT [Source: 158] ---
@app.route('/api/v1/nodes/heartbeat', methods=['POST'])
def receive_heartbeat():
    # Security Check: Is Token present?
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "Missing Token"}), 401
    
    token = auth_header.replace("Bearer ", "")
    
    if token not in REGISTERED_NODES:
        print(f"\n[SERVER] ERROR: Access attempt with Invalid Token!")
        return jsonify({"error": "Invalid Token"}), 401
        
    # Read Data
    data = request.json
    node_id = data.get('node_id')
    metrics = data.get('metrics', {})
    gpu_telemetry = data.get('gpu_telemetry', [])
    
    # Calculate total power draw (For visualization)
    total_watts = sum(g['power_draw_w'] for g in gpu_telemetry)
    avg_temp = sum(g['temp_c'] for g in gpu_telemetry) / len(gpu_telemetry) if gpu_telemetry else 0
    
    print(f"[HEARTBEAT] {node_id} | Power: {int(total_watts)}W | Avg Temp: {int(avg_temp)}°C")
    
    # --- COMMAND CENTER ---
    # Here we return a command to the Rig.
    # For Testing: Check time and change power (To observe dynamic control)
    # Logic: Toggle between 1200W and 800W every 10 seconds based on time.
    
    import time
    seconds = int(time.time())
    target_power = 600 
#if seconds % 20 < 10 else 600
    
    response_command = {
        "command": "adjust_power",      # [Source: 199]
        "setpoint_power_w": target_power, 
        "next_heartbeat": 5
    }
    
    return jsonify(response_command), 200

if __name__ == '__main__':
    # Start server on port 8000
    print(f"--- MOCK EMS SERVER STARTING (Host: {SERVER_HOST}, Port: {SERVER_PORT}) ---")
    app.run(host=SERVER_HOST, port=SERVER_PORT)
