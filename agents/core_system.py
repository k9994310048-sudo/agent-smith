"""
Core System v4.3 - The AGI Heartbeat.
Unified async controller for life cycles (Awake, Idle, Sleep).
Graceful degradation under resource pressure.
"""
import asyncio
import logging
import time
import os

logger = logging.getLogger("core-system")

CPU_WARN = 80.0
CPU_CRIT = 95.0
RAM_WARN_GB = 2.0
RAM_CRIT_GB = 1.0
DISK_WARN_PCT = 90.0


def _get_cpu_load():
    try:
        load = os.getloadavg()[0]
        ncpu = os.cpu_count() or 2
        return (load / ncpu) * 100.0
    except:
        return 0.0


def _get_ram_free_gb():
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return kb / 1024 / 1024
    except:
        pass
    return 4.0


def _get_disk_free_pct():
    try:
        stat = os.statvfs("/")
        return (stat.f_bavail / stat.f_blocks) * 100.0
    except:
        return 50.0


def _check_resources():
    cpu = _get_cpu_load()
    ram = _get_ram_free_gb()
    disk = _get_disk_free_pct()
    details = {"cpu_pct": round(cpu, 1), "ram_free_gb": round(ram, 2), "disk_free_pct": round(disk, 1)}
    if cpu > CPU_CRIT or ram < RAM_CRIT_GB or disk < (100 - DISK_WARN_PCT):
        return "crit", details
    if cpu > CPU_WARN or ram < RAM_WARN_GB:
        return "warn", details
    return "ok", details


class PerformanceMonitor:
    """Track agent performance metrics for self-upgrade decisions."""
    def __init__(self):
        self.response_times = []  # last 20 response times
        self.tool_call_counts = []  # last 20 tool call counts
        self.error_count = 0
        self.total_requests = 0

    def record_response(self, duration_s, tool_calls):
        self.total_requests += 1
        self.response_times.append(duration_s)
        self.tool_call_counts.append(tool_calls)
        if len(self.response_times) > 20:
            self.response_times = self.response_times[-20:]
            self.tool_call_counts = self.tool_call_counts[-20:]

    def record_error(self):
        self.error_count += 1

    def get_stats(self):
        if not self.response_times:
            return {"avg_response": 0, "avg_tools": 0, "error_rate": 0, "total": 0}
        return {
            "avg_response_s": round(sum(self.response_times) / len(self.response_times), 1),
            "avg_tool_calls": round(sum(self.tool_call_counts) / len(self.tool_call_counts), 1),
            "error_rate_pct": round(self.error_count / max(self.total_requests, 1) * 100, 1),
            "total_requests": self.total_requests
        }


class CoreSystem:
    def __init__(self, agent):
        self.agent = agent
        self.state = "awake"
        self.last_interaction = time.time()
        self.is_busy = False
        self.running = True
        self.last_dream = 0
        self.last_correction = 0
        self._degraded = False
        self.perf = PerformanceMonitor()

    def update_interaction(self):
        self.last_interaction = time.time()
        self.state = "awake"

    def set_busy(self, busy: bool):
        self.is_busy = busy

    async def cognitive_loop(self):
        logger.info("Cognitive rhythms initialized.")
        while self.running:
            try:
                idle_time = time.time() - self.last_interaction
                level, details = _check_resources()
                if level == "crit":
                    if not self._degraded:
                        logger.warning("CRITICAL resources: %s. Disabling background tasks.", details)
                        self._degraded = True
                    await asyncio.sleep(60)
                    continue
                elif level == "warn":
                    if not self._degraded:
                        logger.warning("High resource usage: %s. Reducing background activity.", details)
                        self._degraded = True
                else:
                    if self._degraded:
                        logger.info("Resources recovered: %s. Resuming normal operation.", details)
                        self._degraded = False

                if not self.is_busy:
                    if idle_time > 1800:
                        if self.state != "sleeping":
                            self.state = "sleeping"
                            logger.info("Entering deep sleep cycle.")
                        await self._run_sleep_tasks()
                    elif idle_time > 300:
                        if self.state != "idle":
                            self.state = "idle"
                            logger.info("Entering idle state.")
                await asyncio.sleep(60)
            except Exception as e:
                logger.error("Loop error: %s", e)
                await asyncio.sleep(10)

    async def self_reflection(self, query, response, facts_used=None):
        """Post-response self-evaluation: check confidence and contradictions."""
        try:
            from ikkf.memory_awareness import MemoryAwareness
            ma = MemoryAwareness()
            assessment = ma.assess(query)
            ma.close()

            issues = []
            if assessment.get('should_admit_ignorance'):
                issues.append("LOW_COVERAGE")
            if assessment.get('avg_freshness', 1.0) < 0.3:
                issues.append("STALE_FACTS")
            if facts_used:
                for f in facts_used:
                    if f.get('metadata', {}).get('contradictions'):
                        issues.append("CONTRADICTION")

            if issues:
                logger.warning(f"Self-reflection: {issues} for query: {query[:60]}")
            return {'issues': issues, 'coverage': assessment.get('coverage', 0)}
        except Exception as e:
            logger.error(f"Self-reflection error: {e}")
            return {'issues': [], 'coverage': 0}

    async def _run_sleep_tasks(self):
        if self._degraded:
            return
        now = time.time()
        if now - self.last_correction > 43200:
            logger.info("Self-Correction triggered.")
            await self.agent.self_correct()
            self.last_correction = now
        if now - self.last_dream > 86400:
            logger.info("Dream insights triggered.")
            await self.agent.dream()
            self.last_dream = now


_core = None
def get_core(agent=None):
    global _core
    if _core is None and agent:
        _core = CoreSystem(agent)
    return _core
