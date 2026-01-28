import subprocess
import json

"""
RECKON GPU Rig - Hardware Interface
Purpose: Interface with the hardware to collect GPU inventory and telemetry data.
"""

# --- ETC (ETCHASH) REFERANS TABLOSU (MH/s) ---
HASHRATE_LOOKUP = {
    "RX 5700": 55.0,
    "RX 5600": 41.0,
    "Navi 10": 52.0,
    "RX 580": 30.0,
    "RX 590": 31.0,
    "Vega": 45.0
}

def run_command(command):
    """Executes a shell command and returns the output as a string."""
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            check=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None

def estimate_hashrate(gpu_name):
    """
    Kartın ismine bakarak ETC (Etchash) için tahmini hashrate çeker.
    """
    for key, value in HASHRATE_LOOKUP.items():
        if key.lower() in gpu_name.lower():
            return value
            
    if "navi 10" in gpu_name.lower():
        return 50.0
        
    return 0.0

def get_gpu_inventory():
    """
    Initialize fazı için donanım envanterini hazırlar.
    """
    output = run_command("lspci | grep -i vga")
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

def get_gpu_telemetry():
    """
    Canlı verileri okur (Sıcaklık, Güç, Yük).
    """
    def safe_float(val):
        try:
            if val in (None, "N/A", ""):
                return 0.0
            return float(val)
        except Exception:
            return 0.0

    cmd = "rocm-smi --showtemp --showuse --showpower --json"
    json_output = run_command(cmd)
    telemetry = []

    if json_output:
        try:
            data = json.loads(json_output)
            for key in sorted(data.keys()):
                gpu_data = data[key]
                gpu_index = key.replace('card', '')
                temp_c = safe_float(gpu_data.get("Temperature (Sensor edge) (C)"))
                power_w = safe_float(gpu_data.get("Average Graphics Package Power (W)"))
                load_pct = safe_float(gpu_data.get("GPU use (%)"))

                telemetry_item = {
                    "gpu_id": f"gpu_{gpu_index}",
                    "load_pct": load_pct,
                    "temp_c": temp_c,
                    "power_draw_w": power_w,
                    "current_performance": {
                        "value": 0,
                        "unit": "MH/s"
                    }
                }
                telemetry.append(telemetry_item)
        except (json.JSONDecodeError, ValueError):
            pass
    return telemetry

# --- TEST ---
if __name__ == "__main__":
    print("--- GPU INVENTORY TEST (Initialization Data) ---")
    inv = get_gpu_inventory()
    print(json.dumps(inv, indent=4))

    print("\n--- GPU TELEMETRY TEST ---")
    tel = get_gpu_telemetry()
    print(json.dumps(tel, indent=4))
