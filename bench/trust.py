"""The bench's trust verdict as pure functions: bench/runner.py records it, bench/publish.py routes points by it. Stdlib only.

Two different things used to share one "noisy" label, so a real slowdown could be filed as noise and vanish from the
KPIs (Codex, finding 6, 2026-10-27: cold first paints of 100, 100, 100, 100 and 1,000 ms on a quiet machine were
marked noisy because the app's own samples spread, and the 1,000 ms p95 went to kpi_diagnostics.jsonl). They are now
two verdicts:

- **machine** (`trust`): interference measured independently of the app: the fixed-work calibration loop in the same
  browser, and the other work on the CPUs the bench is pinned to (`pressure`, below). `quiet` or `noisy`. Only this may
  route a point away from the KPI series, and only a point a busy CPU can move (`cpu_sensitive` in
  bench/kpi_catalog.json): a time. Bytes, DOM counts and the heap after a forced GC are the same on a loaded machine,
  so they always stay.
- **stability**: the spread of the app's own samples (the cold first paints). A result about the app, never noise: the
  points are published as measured, and the `stable_samples` gate fails beside them. Under interference it is
  `pending` (the gate's pass is null) whatever the CV: an additive slowdown raises the mean and so LOWERS the CV
  ([100, 100, 100, 100, 1000] is 1.437; add 1,000 ms to each and it is 0.314), so a low CV there proves nothing
  (judge r2, finding 3, 2026-10-27, correcting this module's earlier "interference only widens a spread").
- **timing validity**: when a scenario's timings are kept out of the KPI series, the series still says so for the
  current build: bench/publish.py's `timing_valid` gate fails, with the code_sha and the reason. WHY (judge r2,
  finding 3): Vibe Tracks' headline skips null points, so a suppressed run left the previous build's fast number as
  the last word while no_page_errors and stable_samples both passed.

The pressure on the assigned CPUs (Codex, finding 7, 2026-10-27): bench/run.mjs pins the runner to DATA_UI_BENCH_CPUS
(default 4-11), and its browser inherits that (checked per scenario: `browser_cpus`), but the old check divided the
host's load average by the host's 24 CPUs, so eight saturated assigned CPUs read as quiet, and a build on the other
CPUs read as noisy. Now each scenario samples /proc/stat per CPU in three windows (0.5 s before it, the whole
scenario, 0.5 s after), takes out the CPU time of the bench's own process tree (the runner, Playwright's driver and
every Chromium process), and judges:
- the assigned CPUs: the share of their time other work took;
- their SMT siblings outside the set (on this Ryzen, 4-11's are 16-23): the same physical cores, so a build there
  slows the bench although its own CPUs look free. All of their busy time is other work.
The load average is still recorded, as context, never as a rule.

Each measured sample is judged by its own time (judge r2, finding 4, 2026-10-27): one second of full saturation in a
20 s scenario averages to 5 % over the "during" window and read quiet, yet it can own a paint or interaction p95.
So a Sampler thread reads /proc/stat and the bench's own process tree every 200 ms through the scenario, and every
cold load, warm load, interaction and scroll is judged by the 200 ms windows that overlap it (judge_intervals): over
half the assigned CPUs' time taken by other work, or their SMT siblings over half busy, in any of them, and the
sample is not clean. Unclean samples are left out of the timing KPIs; a timing set with too few clean samples left
(enough) is suppressed. The before/after windows are then context: interference after the samples no longer
condemns them. The calibration still judges the whole scenario (it can see what CPU time cannot: memory bandwidth,
thermal limits). Thresholds validated by injecting busy loops on the assigned CPUs: bench/inject_interference.py.
"""

from __future__ import annotations

import math
import os
import pathlib
import statistics
import threading
import time

NOISY_CALIB = 1.3   # calibration slower than 1.3x this host's best ever
NOISY_ASSIGNED = 0.5   # other work took over half the assigned CPUs' time (4 of 8 CPUs' worth)
NOISY_SIBLINGS = 0.5   # their SMT siblings were over half busy
WINDOW_S = 0.5         # the before and after windows
SAMPLE_PERIOD_S = 0.2  # the Sampler's windows: a 40 ms interaction falls inside one or two
SET_NAMES = {"cold": "cold loads", "warm": "warm loads", "interactions": "interactions", "scroll": "scroll frames"}
UNSTABLE_CV = 0.5   # the cold first paints' coefficient of variation (bench/kpi_catalog.json's stable_samples bound)
STABILITY_METRIC = "cold first_useful_paint"
# Which samples each timing KPI is computed from: a set is judged (and suppressed) as one. bench/kpi_catalog.json's
# cpu_sensitive KPIs are exactly these; load_kb, heap_mb and dom_added come from no timing set.
TIMING_SETS = {"first_paint_ms": "cold", "interactive_ms": "cold", "blocking_ms": "cold", "first_paint_100k_ms": "cold",
               "first_paint_worst_ms": "cold", "first_paint_warm_ms": "warm", "interaction_ms": "interactions",
               "model_ms": "interactions", "render_ms": "interactions", "rail_ms": "interactions", "scroll_frame_ms": "scroll"}
SETS = ("cold", "warm", "interactions", "scroll")
# WHY a prefix: results written before the split carry the spread as one of trust.why's strings (runner.py, 0c673d8)
LEGACY_SPREAD_WHY = "cold first-paint spread"


def cv(values) -> float | None:
    """Sample standard deviation over the mean, as runner.summary() computes it; None under two samples."""
    v = [x for x in values if x is not None]
    if len(v) < 2:
        return None
    mean = statistics.fmean(v)
    return round(statistics.stdev(v) / mean, 3) if mean else None


def machine(calib0, calib1, best, pressure=None, unpinned=()) -> dict:
    """Machine interference only: {"verdict": "quiet"|"noisy", "why": [...], "calibration_ratio"}.
    pressure: {window name: pressure()} (None when /proc could not be read: then the calibration alone decides).
    unpinned: the CPU lists of browser processes that are not on the assigned CPUs (the control would not match)."""
    why = []
    calib = max(calib0, calib1)
    ratio = calib / best if best else None
    if ratio is not None and ratio > NOISY_CALIB:
        why.append(f"calibration {calib:.0f} ms is {ratio:.2f}x this host's best {best:.0f} ms")
    for name, w in (pressure or {}).items():
        if not w:
            continue
        if w["foreign_share"] > NOISY_ASSIGNED:
            why.append(f"other work took {w['foreign_cpus']:.1f} of the {w['assigned']} assigned CPUs {name} the scenario")
        if w["siblings_busy_share"] is not None and w["siblings_busy_share"] > NOISY_SIBLINGS:
            why.append(f"their SMT siblings were {100 * w['siblings_busy_share']:.0f}% busy {name} the scenario")
    if unpinned:
        why.append(f"browser processes not on the assigned CPUs: {', '.join(sorted(set(unpinned)))[:120]}")
    return {"verdict": "noisy" if why else "quiet", "why": why, "calibration_ratio": None if ratio is None else round(ratio, 3)}


# ------------------------------------------------------------------ the pressure on the assigned CPUs (/proc, Linux)
def parse_cpu_stat(text: str) -> dict[int, tuple[int, int]]:
    """/proc/stat's per-CPU lines as {cpu: (busy ticks, total ticks)}. busy is user, nice, system, irq, softirq and
    steal; total adds idle and iowait. guest time is already inside user, so it is not added twice."""
    out = {}
    for line in text.splitlines():
        if line.startswith("cpu") and line[3:4].isdigit():
            name, *f = line.split()
            user, nice, system, idle, iowait, irq, softirq, steal = (int(x) for x in (f + ["0"] * 8)[:8])
            busy = user + nice + system + irq + softirq + steal
            out[int(name[3:])] = (busy, busy + idle + iowait)
    return out


def parse_pid_stat(text: str) -> tuple[int, int, int]:
    """/proc/<pid>/stat as (pid, ppid, CPU ticks): utime + stime + cutime + cstime. WHY the children's times too: a
    renderer that exits is reaped by Chromium's browser process and its time moves into the parent's cutime, so the
    tree's total stays continuous across a browser context closing. The name may hold spaces and parentheses."""
    head, _, rest = text.rpartition(")")
    f = rest.split()
    return int(head.split("(", 1)[0]), int(f[1]), sum(int(x) for x in f[11:15])


def parse_pid_times(text: str) -> tuple[int, int, int, int]:
    """/proc/<pid>/stat as (pid, ppid, starttime, its own CPU ticks: utime + stime, no children's)."""
    head, _, rest = text.rpartition(")")
    f = rest.split()
    return int(head.split("(", 1)[0]), int(f[1]), int(f[19]), int(f[11]) + int(f[12])


def tree_ticks(procs, root: int) -> int:
    """The CPU ticks of `root` and every descendant, from [(pid, ppid, ticks)]."""
    kids, ticks = {}, {}
    for pid, ppid, t in procs:
        kids.setdefault(ppid, []).append(pid)
        ticks[pid] = t
    total, todo, seen = 0, [root], set()
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        total += ticks.get(p, 0)
        todo += kids.get(p, [])
    return total


def parse_cpu_list(text: str) -> list[int]:
    """A kernel CPU list ("4-11,16") as sorted CPU numbers."""
    out = set()
    for part in text.strip().split(","):
        if "-" in part:
            a, b = part.split("-")
            out.update(range(int(a), int(b) + 1))
        elif part:
            out.add(int(part))
    return sorted(out)


def smt_siblings(cpus, siblings_of: dict[int, list[int]]) -> list[int]:
    """The hardware threads that share a physical core with one of `cpus` but are not in the set."""
    have = set(cpus)
    return sorted({s for c in cpus for s in siblings_of.get(c, [c])} - have)


def read_smt_siblings(cpus, sysfs="/sys/devices/system/cpu") -> list[int]:
    siblings_of = {}
    for c in cpus:
        try:
            siblings_of[c] = parse_cpu_list(pathlib.Path(f"{sysfs}/cpu{c}/topology/thread_siblings_list").read_text())
        except (OSError, ValueError):
            siblings_of[c] = [c]
    return smt_siblings(cpus, siblings_of)


def _procs(proc="/proc"):
    for d in os.scandir(proc):
        if d.name.isdigit():
            try:
                yield parse_pid_stat(pathlib.Path(d.path, "stat").read_text())
            except (OSError, ValueError, IndexError):
                pass  # a process that exited between the listing and the read


def snapshot(root: int | None = None, proc="/proc") -> dict | None:
    """{"t", "cpu": parse_cpu_stat(), "own": tree_ticks(root)}, or None where /proc/stat cannot be read (not Linux)."""
    try:
        cpu = parse_cpu_stat(pathlib.Path(proc, "stat").read_text())
    except OSError:
        return None
    return {"t": time.monotonic(), "cpu": cpu, "own": tree_ticks(list(_procs(proc)), os.getpid() if root is None else root)}


def idle_window(assigned, siblings, seconds=WINDOW_S, root=None) -> tuple[dict | None, dict | None]:
    """(pressure over `seconds` while the bench waits, the closing snapshot): the before and after windows."""
    a = snapshot(root)
    time.sleep(seconds)
    b = snapshot(root)
    return pressure(a, b, assigned, siblings), b


def pressure(a: dict | None, b: dict | None, assigned, siblings) -> dict | None:
    """What other work did on the assigned CPUs between two snapshots. Every figure is in CPUs' worth (1.0 = one CPU
    busy for the whole window) or a share of the CPUs' time (0..1):
      assigned_busy_cpus  all work on the assigned CPUs
      own_cpus            the bench's own process tree (it is pinned to them, so all of it ran there)
      foreign_cpus        the rest: other agents' work, interrupts; foreign_share = foreign over the assigned CPUs' time
      siblings_busy_share the SMT siblings outside the set (all of it other work: the bench is not on them)
      host_busy_share     every CPU, for context: the old rule's view"""
    if not a or not b:
        return None
    d = {c: (b["cpu"][c][0] - a["cpu"][c][0], b["cpu"][c][1] - a["cpu"][c][1]) for c in a["cpu"] if c in b["cpu"]}
    share = lambda cs: (sum(d[c][0] for c in cs if c in d), sum(d[c][1] for c in cs if c in d))
    busy, total = share(assigned)
    sib_busy, sib_total = share(siblings)
    host_busy, host_total = share(list(d))
    if not total:
        return None
    per_cpu = total / len([c for c in assigned if c in d])  # ticks one CPU has in the window
    own = max(0, b["own"] - a["own"])
    foreign = max(0, busy - own)
    return {"seconds": round(b["t"] - a["t"], 2), "assigned": len(assigned),
            "assigned_busy_cpus": round(busy / per_cpu, 2), "own_cpus": round(own / per_cpu, 2), "foreign_cpus": round(foreign / per_cpu, 2),
            "foreign_share": round(foreign / total, 3),
            "siblings_busy_share": round(sib_busy / sib_total, 3) if sib_total else None,
            "host_busy_share": round(host_busy / host_total, 3) if host_total else None}


def judge_intervals(timeline, intervals, assigned, siblings) -> list[dict]:
    """Each (t0, t1) judged by the timeline's windows (consecutive snapshots) that overlap it: {"foreign_share",
    "siblings_busy_share" (the worst window's), "windows", "clean", "why"}. A sample no window covers, or one with no
    time, is not clean: nothing vouches for it."""
    windows = [(a["t"], b["t"], pressure(a, b, assigned, siblings)) for a, b in zip(timeline, timeline[1:])]
    out = []
    for t0, t1 in intervals:
        hit = [w for a, b, w in windows if w and t0 is not None and t1 is not None and a < t1 and b > t0]
        if not hit:
            out.append({"foreign_share": None, "siblings_busy_share": None, "windows": 0, "clean": False,
                        "why": "no pressure window covers it" if t0 is not None else "the sample has no time"})
            continue
        f = max(w["foreign_share"] for w in hit)
        sib = max((w["siblings_busy_share"] for w in hit if w["siblings_busy_share"] is not None), default=None)
        why = []
        if f > NOISY_ASSIGNED:
            why.append(f"other work took {100 * f:.0f}% of the assigned CPUs in a {SAMPLE_PERIOD_S * 1000:.0f} ms window over it")
        if sib is not None and sib > NOISY_SIBLINGS:
            why.append(f"their SMT siblings were {100 * sib:.0f}% busy in a window over it")
        out.append({"foreign_share": f, "siblings_busy_share": sib, "windows": len(hit), "clean": not why, "why": "; ".join(why)})
    return out


def needed(n: int) -> int:
    """Clean samples a set of n needs: at least half, and at least two (one when there is one)."""
    return max(1, min(n, max(2, math.ceil(n / 2))))


def enough(clean: int, n: int) -> bool:
    return n > 0 and clean >= needed(n)


def judge_set(name: str, clean_flags, machine_verdict: dict) -> dict:
    """One timing set: {"n", "clean", "valid", "why"}. clean_flags None: not judged per sample (no timeline), so every
    sample counts as clean and the scenario's machine verdict alone decides. WHY a set is suppressed whole rather than
    publishing a p95 of whatever survived: a p95 of two loads out of seven is not the KPI the catalog defines."""
    n = len(clean_flags) if clean_flags is not None else 0
    clean = sum(1 for c in clean_flags if c) if clean_flags is not None else n
    if machine_verdict["verdict"] == "noisy":
        return {"n": n, "clean": clean, "valid": False, "why": "; ".join(machine_verdict["why"])}
    if not enough(clean, n):
        return {"n": n, "clean": clean, "valid": False,
                "why": f"{n - clean} of {n} {SET_NAMES.get(name, name)} overlapped interference ({clean} clean, {needed(n)} needed)"}
    return {"n": n, "clean": clean, "valid": True, "why": ""}


def timeline_summary(timeline, assigned, siblings) -> list[list]:
    """The timeline as [t0, t1, foreign_share, siblings_busy_share] per window, for the results file."""
    out = []
    for a, b in zip(timeline, timeline[1:]):
        w = pressure(a, b, assigned, siblings)
        if w:
            out.append([round(a["t"], 3), round(b["t"], 3), w["foreign_share"], w["siblings_busy_share"]])
    return out


class Sampler:
    """Snapshots of /proc/stat (the assigned CPUs and their siblings) and of the bench's own process tree, every
    `period` s on a background thread, time-aligned with the samples by time.monotonic(). The tree is rescanned (a
    full /proc walk, about 15 ms) every `rescan_s` and whenever rescan() is called: the runner calls it right after a
    new page, so the renderer a cold load runs in is known before its window opens. Between rescans only the known
    processes' stat files are read. The bench's own time is the sum of each process's last-seen utime + stime, keyed
    by (pid, start time), so it never dips: WHY not the children's cutime (measured 2026-10-27 on this box): a child
    reaped between the reads of its parent and of itself vanished from one snapshot, its time read as other work,
    and spawning two busy children lifted the foreign share's worst window from 0.43 to 0.74. A process that exits
    loses at most its time since the last read (one period)."""

    def __init__(self, assigned, siblings, period=SAMPLE_PERIOD_S, root=None, rescan_s=2.0, proc="/proc"):
        self.cpus = set(assigned) | set(siblings)
        self.period, self.rescan_s, self.proc = period, rescan_s, proc
        self.root = os.getpid() if root is None else root
        self.snaps: list[dict] = []
        self._tree: set[int] = set()
        self._seen: dict[tuple[int, int], int] = {}
        self._scanned = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def rescan(self) -> None:
        kids: dict[int, list[int]] = {}
        for pid, ppid, _ in _procs(self.proc):
            kids.setdefault(ppid, []).append(pid)
        tree, todo = set(), [self.root]
        while todo:
            p = todo.pop()
            if p not in tree:
                tree.add(p)
                todo += kids.get(p, [])
        with self._lock:
            self._tree, self._scanned = tree, time.monotonic()

    def snap(self) -> dict | None:
        try:
            text = pathlib.Path(self.proc, "stat").read_text()
        except OSError:
            return None
        t = time.monotonic()
        with self._lock:
            pids = list(self._tree)
        for pid in pids:
            try:
                _, _, start, ticks = parse_pid_times(pathlib.Path(self.proc, str(pid), "stat").read_text())
                self._seen[(pid, start)] = ticks
            except (OSError, ValueError, IndexError):
                pass  # exited: its last-seen time stays in the total
        return {"t": t, "cpu": {c: v for c, v in parse_cpu_stat(text).items() if c in self.cpus}, "own": sum(self._seen.values())}

    def _run(self) -> None:
        due = time.monotonic()
        while not self._stop.is_set():
            if time.monotonic() - self._scanned > self.rescan_s:
                self.rescan()
            s = self.snap()
            if s:
                self.snaps.append(s)
            due += self.period
            self._stop.wait(max(0.0, due - time.monotonic()))

    def start(self) -> "Sampler":
        self.rescan()
        self._thread = threading.Thread(target=self._run, name="bench-pressure-sampler", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> list[dict]:
        """Stop the thread (joined) and return the snapshots, a last one taken now."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        last = self.snap()
        if last:
            self.snaps.append(last)
        return list(self.snaps)

    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())


def tree_affinity(root: int | None = None, proc="/proc") -> list[str]:
    """The distinct CPU lists (Cpus_allowed_list) of the bench's process tree, its root left out: the browser's
    processes, read while a calibration page is open, so the renderer that runs the control is among them."""
    root = os.getpid() if root is None else root
    procs = list(_procs(proc))
    kids = {}
    for pid, ppid, _ in procs:
        kids.setdefault(ppid, []).append(pid)
    out, todo = set(), list(kids.get(root, []))
    while todo:
        p = todo.pop()
        todo += kids.get(p, [])
        try:
            line = next(x for x in pathlib.Path(proc, str(p), "status").read_text().splitlines() if x.startswith("Cpus_allowed_list"))
            out.add(line.split(":", 1)[1].strip())
        except (OSError, StopIteration):
            pass
    return sorted(out)


def stability(values, machine_verdict: str) -> dict:
    """The app's own samples: {"verdict": "stable"|"unstable"|"pending"|"unknown", "metric", "cv", "n", "threshold", "why"}.
    pending: the samples were measured under interference (machine_verdict "noisy"), whatever their CV. unknown:
    under two samples. WHY never stable under interference: an additive slowdown raises the mean and lowers the CV,
    so a low CV there can hide a spread the app really has (judge r2, finding 3)."""
    v = [x for x in values if x is not None]
    c = cv(v)
    out = {"metric": STABILITY_METRIC, "cv": c, "n": len(v), "threshold": UNSTABLE_CV}
    if c is None:
        return {**out, "verdict": "unknown", "why": f"{len(v)} {STABILITY_METRIC} sample(s): too few to judge a spread"}
    if machine_verdict == "noisy":
        return {**out, "verdict": "pending", "why": f"the machine was noisy: measured under interference, a {STABILITY_METRIC} cv of {c} proves nothing either way"}
    if c > UNSTABLE_CV:
        return {**out, "verdict": "unstable", "why": f"{STABILITY_METRIC} cv {c} > {UNSTABLE_CV}: the app's own samples disagree"}
    return {**out, "verdict": "stable", "why": ""}


def stability_pass(st: dict) -> bool | None:
    """The stable_samples gate's pass for one scenario: True, False, or None (pending or unknown)."""
    return {"stable": True, "unstable": False}.get((st or {}).get("verdict"))


def worst(verdicts) -> bool | None:
    """Vibe Tracks' worst_verdict (vibetracks/core/rules.py): false if any is false, else null if any is not true."""
    seen = list(verdicts)
    if any(v is False for v in seen):
        return False
    if not seen or any(v is not True for v in seen):
        return None
    return True


def legacy_machine(trust: dict) -> dict:
    """The machine verdict of a results file written before the split: its trust.why without the spread reason."""
    why = [w for w in trust.get("why") or [] if not w.startswith(LEGACY_SPREAD_WHY)]
    return {"verdict": "noisy" if why else "quiet", "why": why}


def cpu_sensitive(kpi: str, catalog: dict) -> bool:
    """Whether a busy CPU moves this KPI (bench/kpi_catalog.json's cpu_sensitive). A KPI or gate the catalog does not
    declare counts as sensitive, as every point did before the field existed."""
    k = next((k for k in catalog.get("kpis") or [] if k.get("id") == kpi), None)
    return True if k is None else bool(k.get("cpu_sensitive", True))
