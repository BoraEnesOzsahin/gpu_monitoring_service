"""
RECKON GPU Rig - Hardware Interface
Purpose: Interface with the hardware to collect GPU inventory and telemetry data.
"""
import subprocess
import json
import re
import requests

# --- COMMAND TIMEOUT CONFIGURATION ---
# rocm-smi can hang indefinitely, causing system lockup
# These timeouts prevent infinite process accumulation
COMMAND_TIMEOUT_SECONDS = 30  # Default timeout for general commands
AMD_INFO_TIMEOUT_SECONDS = 15  # Shorter timeout for amd-info (known to hang)

# --- ETC (ETCHASH) REFERANS TABLOSU (MH/s) ---
HASHRATE_LOOKUP = {
    "RX 5700": 55.0,
    "RX 5600": 41.0,
    "Navi 10": 52.0,
    "RX 580": 30.0,
    "RX 590": 31.0,
    "Vega": 45.0
}

def run_command(command, timeout=None):
    """
    Executes a shell command and returns the output as a string.
    
    SAFETY: Added timeout to prevent infinite hangs from rocm-smi.
    rocm-smi is known to hang indefinitely, which causes process accumulation
    and eventually system lockup.
    
    Args:
        command: Shell command to execute
        timeout: Maximum seconds to wait (default: COMMAND_TIMEOUT_SECONDS)
    
    Returns:
        Command output as string, or None on error/timeout
    """
    # Use amd-info specific timeout for amd-info commands
    # Check if amd-info appears as a distinct command (word boundary check)
    if timeout is None:
        is_amd_info = False
        if isinstance(command, str):
            # Match amd-info as a complete word/command name using regex
            # This handles: "amd-info", "amd-info --args", "/usr/bin/amd-info"
            is_amd_info = bool(re.search(r'(?:^|/| )amd-info(?:$| )', command))
        if is_amd_info:
            timeout = AMD_INFO_TIMEOUT_SECONDS
        else:
            timeout = COMMAND_TIMEOUT_SECONDS
    
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            check=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout  # SAFETY: Prevent infinite hang
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        print(f"WARNING: Command timed out after {timeout}s: {command}")
        return None
    except subprocess.CalledProcessError:
        return None




def estimate_hashrate(gpu_name):
    """
    Kartın ismine bakarak ETC (Etchash) için tahmini hashrate çeker.
    """
    for key, value in HASHRATE_LOOKUP.items():
        if key.lower() in gpu_name.lower():
            return value
            
    return 0.0

def get_gpu_inventory():
    """
    Initialize fazı için donanım envanterini hazırlar.
    """
    output = run_command("amd-info")
    inventory = []
    
    if not output:
        return []

    lines = output.split('\n')
    for index, line in enumerate(lines):
        # lspci çıktısını ayıkla
        parts = line.split(': ')
        full_name = parts[-1].strip() if len(parts) > 1 else "Unknown AMD GPU"
        
        # İsimdeki fazlalıkları temizle
        clean_name = full_name.replace('[', '').replace(']', '')
        
        # ETC Hashrate Tahmini Yap
        estimated_mh = estimate_hashrate(clean_name)
        
        gpu_item = {
            "gpu_id": f"gpu_{index}",
            "name": clean_name,
            "tdp_w": 210,
            "compute_capability": {
                "value": estimated_mh,
                "unit": "MH/s"
            }
        }
        inventory.append(gpu_item)
            
    return inventory






def safe_float(val):
    try:
        if val is None: return 0.0
        # "N/A", "na" gibi ifadeleri kontrol et
        clean_val = str(val).strip().lower()
        if clean_val in ("n/a", "na", "", "undefined"):
            return 0.0
        # Sadece rakam ve noktayı tut
        numeric_part = "".join(c for c in clean_val if c.isdigit() or c == '.')
        return float(numeric_part) if numeric_part else 0.0
    except:
        return 0.0




def get_gpu_telemetry():
    try:
        response = requests.get("http://127.0.0.1:44444/summary", timeout=5)
        data = response.json()

        telemetry = []

        for gpu in data.get("Session", {}).get("Workers", []):
            gpu_index = gpu.get("Index")
            speed = gpu.get("Megahashes", 0)
            power = gpu.get("Power", 0)
            temp = gpu.get("Core_Temp", 0)

            telemetry.append({
                "gpu_id": f"gpu_{gpu_index}",
                "load_pct": 100.0, # Madencilikte her zaman 100 kabul edebiliriz
                "temp_c": temp,
                "power_draw_w": power,
                "current_performance": {"value": speed, "unit": "MH/s"}
            })

        return telemetry

    except Exception as e:
        print(f"Veri çekilemedi: {e}")
        return []







# --- TEST ---
if __name__ == "__main__":
    print("--- GPU INVENTORY TEST (Initialization Data) ---")
    inv = get_gpu_inventory()
    print(json.dumps(inv, indent=4))

    print("\n--- GPU TELEMETRY TEST ---")
    tel = get_gpu_telemetry()
    print(json.dumps(tel, indent=4))
