"""Como está o PC: CPU, RAM, disco, placa gráfica (temperatura), apps abertas e o que mais gasta.

- CPU/RAM/disco/processos: psutil (o mesmo que o Gestor de Tarefas mostra).
- Placa gráfica NVIDIA: nvidia-smi (temperatura, uso, memória).
- Temperatura da motherboard: sensor ACPI do Windows (a do processador em si precisa de
  permissões de administrador, por isso não aparece).
"""

import subprocess
import time
from collections import defaultdict

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_IGNORE = {"System Idle Process", "System", "Registry", "Memory Compression", "MemCompression", "Idle"}


def gpu_info(run=None) -> list[dict]:
    run = run or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=8,
                                             creationflags=_NO_WINDOW).stdout)
    try:
        out = run(["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total",
                   "--format=csv,noheader,nounits"])
    except (OSError, subprocess.SubprocessError):
        return []
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 5 and parts[1].isdigit():
            gpus.append({"name": parts[0], "temp": int(parts[1]), "util": int(parts[2]),
                         "mem_used": int(parts[3]), "mem_total": int(parts[4])})
    return gpus


def board_temperature(run=None) -> float | None:
    """Sensor ACPI (em Kelvin) -> ºC. Nem todos os PCs o têm."""
    run = run or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=8,
                                             creationflags=_NO_WINDOW).stdout)
    try:
        out = run(["powershell", "-NoProfile", "-Command",
                   "Get-CimInstance Win32_PerfFormattedData_Counters_ThermalZoneInformation | "
                   "ForEach-Object { $_.Temperature }"])
    except (OSError, subprocess.SubprocessError):
        return None
    temps = [int(x) - 273.15 for x in out.split() if x.isdigit() and 250 < int(x) < 400]
    return round(max(temps), 1) if temps else None


def top_processes(limit: int = 5, sample: float = 1.0):
    """[(nome, %cpu)] e [(nome, MB)] dos programas que mais gastam (somando os processos de cada um)."""
    import psutil

    procs = list(psutil.process_iter(["name"]))
    for p in procs:
        try:
            p.cpu_percent(None)
        except psutil.Error:
            pass
    time.sleep(sample)
    cpu, ram = defaultdict(float), defaultdict(float)
    cores = psutil.cpu_count() or 1
    for p in procs:
        try:
            name = (p.info["name"] or "").removesuffix(".exe")
            if not name or name in _IGNORE:
                continue
            cpu[name] += p.cpu_percent(None) / cores
            ram[name] += p.memory_info().rss / 2**20
        except psutil.Error:
            continue
    by_cpu = sorted(cpu.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    by_ram = sorted(ram.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return by_cpu, by_ram


def open_apps() -> list[str]:
    """Programas com janelas abertas (como a lista "Aplicações" do Gestor de Tarefas)."""
    import win32gui
    import win32process

    from jarvis.actions.system import _process_exe

    names = []

    def visit(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd) or win32gui.GetParent(hwnd) or not win32gui.GetWindowText(hwnd):
            return
        if win32gui.GetWindow(hwnd, 4):  # GW_OWNER: janelas secundárias
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        exe = _process_exe(pid).rsplit("\\", 1)[-1].removesuffix(".exe")
        if exe and exe.lower() not in ("explorer", "textinputhost", "applicationframehost", "shellexperiencehost",
                                       "searchhost", "startmenuexperiencehost", "systemsettings") \
                and exe not in names:
            names.append(exe)

    win32gui.EnumWindows(visit, None)
    return names


def _gb(value: float) -> str:
    return f"{value / 2**30:.1f}".replace(".", ",") + " GB"


def _uptime(seconds: float) -> str:
    hours, minutes = int(seconds // 3600), int(seconds % 3600 // 60)
    return f"{hours // 24} dias e {hours % 24} h" if hours >= 24 else f"{hours} h {minutes} min"


def pc_status() -> str:
    import psutil

    cpu = psutil.cpu_percent(interval=0.5)
    freq = psutil.cpu_freq()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\")
    by_cpu, by_ram = top_processes()
    gpus = gpu_info()
    board = board_temperature()
    battery = psutil.sensors_battery()

    lines = ["🖥 Estado do PC:"]
    lines.append(f"• CPU: {cpu:.0f}% ({psutil.cpu_count(logical=False)} núcleos"
                 + (f", {freq.current / 1000:.1f} GHz".replace(".", ",") if freq else "") + ")")
    lines.append(f"• RAM: {mem.percent:.0f}% ({_gb(mem.used)} de {_gb(mem.total)})")
    lines.append(f"• Disco C: {disk.percent:.0f}% cheio ({_gb(disk.free)} livres)")
    for g in gpus:
        lines.append(f"• Placa gráfica {g['name']}: {g['temp']} ºC, {g['util']}% de uso, "
                     f"{g['mem_used'] / 1024:.1f} de {g['mem_total'] / 1024:.1f} GB de memória".replace(".", ","))
    if board is not None:
        lines.append(f"• Temperatura da motherboard: {board:.0f} ºC".replace(".", ","))
    if battery is not None:
        lines.append(f"• Bateria: {battery.percent:.0f}%" + (" (a carregar)" if battery.power_plugged else ""))
    lines.append(f"• Ligado há {_uptime(time.time() - psutil.boot_time())}")
    lines.append("🔥 O que gasta mais CPU: " + ", ".join(f"{n} {c:.0f}%" for n, c in by_cpu))
    lines.append("🧠 O que gasta mais RAM: " + ", ".join(f"{n} {_gb(m * 2**20)}" for n, m in by_ram))
    try:
        apps = open_apps()
        lines.append(f"🪟 Apps abertas ({len(apps)}): " + ", ".join(apps))
    except Exception:
        pass
    lines.append(verdict(cpu, mem.percent, disk.percent, gpus))
    return "\n".join(lines)


def verdict(cpu: float, ram: float, disk: float, gpus: list[dict]) -> str:
    problems = []
    if cpu > 85:
        problems.append("o CPU está quase no máximo")
    if ram > 90:
        problems.append("a RAM está quase cheia (fecha algumas apps)")
    if disk > 90:
        problems.append("o disco C está quase cheio")
    for g in gpus:
        if g["temp"] >= 85:
            problems.append(f"a placa gráfica está muito quente ({g['temp']} ºC)")
    if not problems:
        return "✅ Está tudo bem com o PC."
    return "⚠️ Atenção: " + "; ".join(problems) + "."


# "como está o pc?", "faz um diagnóstico", "temperatura do pc", "o que está a gastar mais?"
REQUEST = __import__("re").compile(
    r"como\s+(?:est[aá]|anda|vai)\s+o\s+(?:pc|computador|port[aá]til)|diagn[oó]stico|"
    r"temperatura\s+d[oa]s?\s+(?:pc|computador|cpu|gpu|processador|placa)|^\W*temperatura\W*$|gestor\s+de\s+tarefas|desempenho|performance|"
    r"(?:o\s+que|que\s+apps?|quais\s+apps?)\s+(?:est[aá]|est[aã]o|tenho)\s+(?:a\s+)?(?:gastar|usar|consumir|abert[ao]s?)|"
    r"(?:uso|consumo)\s+d[eoa]\s+(?:cpu|ram|mem[oó]ria|gpu|pc)|apps?\s+abertas",
    __import__("re").IGNORECASE,
)
