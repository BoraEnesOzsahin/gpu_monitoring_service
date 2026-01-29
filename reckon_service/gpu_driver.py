import subprocess
import json
import re
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



#def get_gpu_telemetry():
#    """
#    Reads live GPU telemetry (temperature, power, load).
#    Returns a list of GPU telemetry dictionaries.
#    Ignores empty or non-JSON output from rocm-smi.
#    """
#    def safe_float(val):
#        try:
#            if val is None or str(val).strip().lower() in ("n/a", "na", "", "undefined"):
#                return 0.0
#            return float(val)
#        except Exception:
#            return 0.0
#
#    cmd = "rocm-smi --showtemp --showuse --showpower --json"
#    json_output = run_command(cmd)
#    telemetry = []
#
#    # If output is empty or not a JSON object, skip processing
#    if not json_output or not json_output.strip().startswith("{"):
#        print("WARNING: rocm-smi returned empty or non-JSON output!")
#        print(f"rocm-smi output:\n{json_output}")
#        return []
#
#    try:
#        data = json.loads(json_output)
#        for key in sorted(data.keys()):
#            gpu_data = data[key]
#            gpu_index = key.replace('card', '')
#            temp_c = safe_float(gpu_data.get("Temperature (Sensor edge) (C)"))
#            power_w = safe_float(gpu_data.get("Average Graphics Package Power (W)"))
#            load_pct = safe_float(gpu_data.get("GPU use (%)"))
#
#            telemetry_item = {
#                "gpu_id": f"gpu_{gpu_index}",
#                "load_pct": load_pct,
#                "temp_c": temp_c,
#                "power_draw_w": power_w,
#                "current_performance": {
#                    "value": 0,
#                    "unit": "MH/s"
#                }
#            }
#            telemetry.append(telemetry_item)
#    except Exception as e:
#        print(f"JSON Decode Error in get_gpu_telemetry: {e}")
#        print(f"rocm-smi output:\n{json_output}")
#        return []
#
#    return telemetry




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
    cmd = "rocm-smi --showtemp --showuse --showpower --json"
    raw_output = run_command(cmd)
    telemetry = []

    if not raw_output:
        return []

    try:
        # 1. TEMİZLİK: Sadece '{' ile başlayıp '}' ile biten kısmı al (Warning yazılarını siler)
        start_idx = raw_output.find('{')
        end_idx = raw_output.rfind('}')
        if start_idx == -1 or end_idx == -1:
            return []
        
        json_clean = raw_output[start_idx : end_idx + 1]
        data = json.loads(json_clean)

        # 2. VERİ ÇEKME
        for key in sorted(data.keys()):
            if not key.startswith('card'):
                continue
            
            gpu_data = data[key]
            gpu_index = key.replace('card', '')
            
            # .get(anahtar, varsayılan_değer) kullanarak eksik verilerde çökmesini önlüyoruz
            temp = safe_float(gpu_data.get("Temperature (Sensor edge) (C)", 0))
            power = safe_float(gpu_data.get("Average Graphics Package Power (W)", 0))
            load = safe_float(gpu_data.get("GPU use (%)", 0))

            telemetry.append({
                "gpu_id": f"gpu_{gpu_index}",
                "load_pct": load,
                "temp_c": temp,
                "power_draw_w": power,
                "current_performance": {"value": 0, "unit": "MH/s"}
            })

    except Exception as e:
        print(f"Kritik Hata: {e}") # Heartbeat'in devam etmesi için programı durdurmuyoruz
    
    return telemetry




# --- TEST ---
if __name__ == "__main__":
    print("--- GPU INVENTORY TEST (Initialization Data) ---")
    inv = get_gpu_inventory()
    print(json.dumps(inv, indent=4))

    print("\n--- GPU TELEMETRY TEST ---")
    tel = get_gpu_telemetry()
    print(json.dumps(tel, indent=4))
