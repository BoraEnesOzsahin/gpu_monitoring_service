import json
import os
import uuid
from dotenv import load_dotenv

"""
RECKON Client - Configuration & State Manager
Purpose: Handles persistent storage (tokens), hardware ID generation, and global settings.
Reference: Protocol Doc Section 4.1 (Initialization)
"""

# Load environment variables from .env file
load_dotenv()

# --- CONFIGURATION ---
# CHANGE THIS to your actual EMS Server URL
EMS_API_URL = os.getenv("EMS_API_URL", "http://127.0.0.1:8000")

# File to store the API token and Node ID securely
SECRETS_FILE = os.getenv("SECRETS_FILE", "secrets.json")

# Client configuration
DEFAULT_HEARTBEAT_INTERVAL = int(os.getenv("DEFAULT_HEARTBEAT_INTERVAL", "60"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "60"))

def get_hardware_id():
    """
    Generates a unique Hardware ID based on the machine's MAC address.
    Required for: /api/v1/nodes/initialize 
    """
    # getnode() returns the MAC address as an integer
    mac_int = uuid.getnode()
    # Convert to standard hex format: aa:bb:cc:dd:ee:ff
    mac_hex = ':'.join((['{:02x}'.format((mac_int >> ele) & 0xff)
                        for ele in range(0, 8*6, 8)][::-1]))
    return mac_hex

def load_secrets():
    """
    Tries to load the saved API Token and Node ID from disk.
    Returns: dict or None (if not found)
    """
    if os.path.exists(SECRETS_FILE):
        try:
            with open(SECRETS_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Warning: secrets file is corrupted.")
            return None
    return None

def save_secrets(node_id, api_token):
    """
    Saves the credentials received from the server to disk.
    Reference: "SECRET KEY - Save to disk!"
    """
    data = {
        "node_id": node_id,
        "api_token": api_token
    }
    with open(SECRETS_FILE, 'w') as f:
        json.dump(data, f, indent=4)
    print(f"Success: Credentials saved to {SECRETS_FILE}")

def delete_secrets():
    """
    Deletes the token file. Used when server sends 401 Unauthorized.
    Reference: 
    """
    if os.path.exists(SECRETS_FILE):
        os.remove(SECRETS_FILE)
        print("Security: Invalid token deleted.")

# --- TEST BLOCK ---
if __name__ == "__main__":
    print(f"Hardware ID: {get_hardware_id()}")
    print(f"Server URL: {EMS_API_URL}")
    
    # Simple test of save/load
    print("\n--- Testing Storage ---")
    save_secrets("test-node-001", "test-token-xyz")
    loaded = load_secrets()
    print(f"Loaded: {loaded}")
