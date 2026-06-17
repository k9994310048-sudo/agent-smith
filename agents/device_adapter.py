"""
Device Adapter v1.0 — Сканирование железа и подбор оптимальных параметров.
Используется при запуске и для self-upgrade (LHR 2.3).
"""
import json
import os
import subprocess
import logging

logger = logging.getLogger("device-adapter")

PROJECT_ROOT = "/home/mac/.agent-smith"
DEVICE_PROFILE_PATH = os.path.join(PROJECT_ROOT, "data", "device_profile.json")


def scan_hardware():
    """Полное сканирование железа."""
    info = {}

    # CPU
    try:
        result = subprocess.run(
            "cat /proc/cpuinfo | grep 'model name' | head -1 | cut -d: -f2",
            shell=True, capture_output=True, text=True, timeout=5
        )
        info["cpu_model"] = result.stdout.strip()
    except:
        info["cpu_model"] = "unknown"

    try:
        info["cpu_cores"] = os.cpu_count() or 2
    except:
        info["cpu_cores"] = 2

    try:
        with open("/proc/cpuinfo") as f:
            mhz = []
            for line in f:
                if "MHz" in line or "GHz" in line or "mhz" in line:
                    try:
                        val = float(line.split(":")[-1].strip().split()[0])
                        mhz.append(val)
                    except:
                        pass
        if not mhz:
            result = subprocess.run(
                "lscpu | grep 'CPU MHz' | awk '{print $NF}'",
                shell=True, capture_output=True, text=True, timeout=5
            )
            mhz = [float(result.stdout.strip())]
        info["cpu_mhz"] = int(max(mhz)) if mhz else 2400
    except:
        info["cpu_mhz"] = 2400

    try:
        load = os.getloadavg()
        info["load_1m"] = round(load[0], 2)
    except:
        info["load_1m"] = 0.0

    # RAM
    try:
        with open("/proc/meminfo") as f:
            meminfo = f.read()
        total_kb = avail_kb = 0
        for line in meminfo.split("\n"):
            if line.startswith("MemTotal:"):
                total_kb = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                avail_kb = int(line.split()[1])
        info["ram_total_gb"] = round(total_kb / 1024 / 1024, 1)
        info["ram_free_gb"] = round(avail_kb / 1024 / 1024, 1)
        info["ram_used_pct"] = round((1 - avail_kb / total_kb) * 100, 0)
    except:
        info["ram_total_gb"] = 16.0
        info["ram_free_gb"] = 12.0
        info["ram_used_pct"] = 25

    # Disk
    try:
        stat = os.statvfs("/")
        info["disk_total_gb"] = round(stat.f_blocks * stat.f_frsize / 1024 / 1024 / 1024, 1)
        info["disk_free_gb"] = round(stat.f_bavail * stat.f_frsize / 1024 / 1024 / 1024, 1)
        info["disk_used_pct"] = round((1 - stat.f_bavail / stat.f_blocks) * 100, 0)
    except:
        info["disk_total_gb"] = 100
        info["disk_free_gb"] = 30
        info["disk_used_pct"] = 70

    # GPU
    info["gpu"] = None
    try:
        result = subprocess.run(
            "lspci | grep -i vga | head -1",
            shell=True, capture_output=True, text=True, timeout=5
        )
        vga = result.stdout.lower()
        if "nvidia" in vga:
            info["gpu"] = "nvidia"
        elif "amd" in vga or "radeon" in vga:
            info["gpu"] = "amd"
        elif "intel" in vga:
            info["gpu"] = "intel"
        else:
            info["gpu"] = vga.strip()[:30] or None
    except:
        pass

    # Temperature
    try:
        result = subprocess.run(
            "cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null",
            shell=True, capture_output=True, text=True, timeout=3
        )
        temp = int(result.stdout.strip()) / 1000
        info["cpu_temp_c"] = round(temp, 0)
    except:
        info["cpu_temp_c"] = None

    return info


def determine_optimal_params(hw):
    """Подбор оптимальных параметров на основе железа."""
    params = {}

    # Размер модели по RAM
    ram = hw.get("ram_total_gb", 8)
    if ram >= 12:
        params["model_size"] = "7B"
        params["n_ctx"] = 4096
    elif ram >= 6:
        params["model_size"] = "3B"
        params["n_ctx"] = 2048
    else:
        params["model_size"] = "1.5B"
        params["n_ctx"] = 2048

    # Количество потоков по CPU
    cores = hw.get("cpu_cores", 2)
    params["n_threads"] = max(1, cores - 1)

    # Размер контекста по RAM
    free_ram = hw.get("ram_free_gb", 4)
    if free_ram >= 6:
        params["max_context"] = 4096
    elif free_ram >= 3:
        params["max_context"] = 2048
    else:
        params["max_context"] = 1024

    # Частота фоновых задач по нагрузке
    load = hw.get("load_1m", 1.0)
    if load < 1.0:
        params["background_interval_s"] = 60
    elif load < 3.0:
        params["background_interval_s"] = 300
    else:
        params["background_interval_s"] = 600

    # Температурные пороги
    temp = hw.get("cpu_temp_c", 40) or 40
    params["temp_warn_c"] = 80
    params["temp_crit_c"] = 90

    return params


def save_profile(hw, params, path=DEVICE_PROFILE_PATH):
    """Сохранить профиль устройства."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    profile = {
        "hardware": hw,
        "optimal_params": params,
        "device_name": os.uname().nodename
    }
    with open(path, "w") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
    logger.info(f"Device profile saved to {path}")


def load_profile(path=DEVICE_PROFILE_PATH):
    """Загрузить профиль устройства."""
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load device profile: {e}")
        return None


def get_recommended_model(hw=None):
    """Вернуть рекомендованную модель для текущего железа."""
    if hw is None:
        hw = scan_hardware()
    params = determine_optimal_params(hw)
    ram = hw.get("ram_total_gb", 8)

    models = []
    if ram >= 10:
        models.append({"name": "7B_Q4", "ram_gb": 4.5, "priority": 1})
    if ram >= 4:
        models.append({"name": "3B_Q4", "ram_gb": 2.5, "priority": 2})
    if ram >= 2:
        models.append({"name": "1.5B_Q4", "ram_gb": 1.5, "priority": 3})
    models.append({"name": "0.5B_Q4", "ram_gb": 0.5, "priority": 4})

    return models


if __name__ == "__main__":
    print("Scanning hardware...")
    hw = scan_hardware()
    params = determine_optimal_params(hw)
    save_profile(hw, params)
    print(f"Hardware: {hw.get('cpu_model', '?')}, {hw.get('ram_total_gb', '?')}GB RAM")
    print(f"Recommended model: {params['model_size']}, ctx={params['n_ctx']}")
    print(f"Max concurrent: {params['n_threads']} threads")
