"""
RECKON Client - Configuration & State Manager
Purpose: Handles persistent storage (tokens), hardware ID generation, and global settings.
Reference: Protocol Doc Section 4.1 (Initialization)
"""
import json
import os
import uuid
from dotenv import load_dotenv

# Load environment variables from .env file (search from project root)
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(dotenv_path=os.path.join(_BASE_DIR, '.env'))

# --- CONFIGURATION ---
def _normalize_url(url):
    """
    Ensures the URL has a proper HTTP/HTTPS scheme.
    If the URL is missing a scheme (e.g. '192.168.1.1:8000'), prepends 'http://'.
    A missing scheme causes requests to raise 'Max retries exceeded with url'
    because no transport adapter can be found for the bare host:port string.
    """
    if url and not url.startswith(("http://", "https://")):
        print(f"Warning: EMS_API_URL '{url}' has no scheme. Prepending 'http://'.")
        url = f"http://{url}"
    return url

EMS_API_URL = _normalize_url(os.getenv("EMS_API_URL", "http://127.0.0.1:8000"))

# File to store the API token and Node ID securely
SECRETS_FILE = os.getenv("SECRETS_FILE", "secrets.json")

# Client configuration
DEFAULT_HEARTBEAT_INTERVAL = int(os.getenv("DEFAULT_HEARTBEAT_INTERVAL", "60"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "60"))

# Redaction configuration
NODE_ID_REDACTION_LENGTH = 8  # Number of characters to show when redacting node IDs

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
    Returns: dict or None (if not found or if api_token is invalid)
    
    SAFETY: Rejects null/empty api_token to prevent infinite loop.
    If api_token is None, empty string, or missing, returns None.
    """
    if os.path.exists(SECRETS_FILE):
        try:
            with open(SECRETS_FILE, 'r') as f:
                data = json.load(f)
                
            # SAFETY: Validate api_token exists and is not null/empty
            # This prevents infinite restart loop if token is missing
            if not data:
                return None
            
            api_token = data.get("api_token")
            if not api_token:
                print("Warning: api_token is null or empty. Rejecting secrets.")
                return None
            
            return data
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




def save_pending_node_id(node_id):
    """
    Logs the pending node_id received during registration.
    
    SAFETY: Does not persist to disk to avoid restart loops.
    If we saved a null token, load_secrets() would reject it and trigger
    an immediate restart. Instead, we only log and continue waiting for approval.
    """
    # Redact node_id for security
    # - For None: show "None"
    # - For empty string: show "(empty)"
    # - For IDs > NODE_ID_REDACTION_LENGTH chars: show first NODE_ID_REDACTION_LENGTH chars + "..."
    # - For shorter IDs: show "***" (to avoid revealing full ID)
    if node_id is None:
        redacted_id = "None"
    elif node_id == "":
        redacted_id = "(empty)"
    elif len(node_id) > NODE_ID_REDACTION_LENGTH:
        redacted_id = f"{node_id[:NODE_ID_REDACTION_LENGTH]}..."
    else:
        # ID is NODE_ID_REDACTION_LENGTH chars or shorter - fully redact
        redacted_id = "***"
    
    print(f"PENDING: node_id '{redacted_id}' received (not saved to disk yet)")
    print("Waiting for admin approval before saving credentials...")





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
