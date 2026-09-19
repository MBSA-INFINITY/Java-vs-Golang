"""
Generates all comparative Java vs Go benchmark graphs (network I/O and disk I/O)
in both log-log and linear scale.

Usage:
    pip install matplotlib
    python generate_graphs.py

Output:
    ./output/log/*.png      -> log-scale versions (concurrency, and rps/latency where applicable)
    ./output/linear/*.png   -> linear-scale versions of the same charts
    ./output/*.png          -> summary/bar charts (single scale, not concurrency-swept)
"""

import os
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, "output")
LOG_DIR = os.path.join(OUT_DIR, "log")
LINEAR_DIR = os.path.join(OUT_DIR, "linear")

# ---------------------------------------------------------------------------
# Data (transcribed from the article's tables)
# ---------------------------------------------------------------------------

NETWORK_JAVA_T1 = [
    dict(concurrency=1, rps=17.50, p50=56.49, p90=57.50, p99=63.87, errors=0, error_pct=0.00),
    dict(concurrency=5, rps=89.00, p50=55.94, p90=58.65, p99=64.56, errors=0, error_pct=0.00),
    dict(concurrency=10, rps=184.00, p50=54.32, p90=55.61, p99=59.61, errors=0, error_pct=0.00),
    dict(concurrency=20, rps=365.10, p50=53.79, p90=56.49, p99=72.53, errors=0, error_pct=0.00),
    dict(concurrency=50, rps=909.70, p50=53.21, p90=59.14, p99=84.74, errors=0, error_pct=0.00),
    dict(concurrency=100, rps=1664.50, p50=57.67, p90=67.61, p99=130.57, errors=0, error_pct=0.00),
    dict(concurrency=200, rps=2487.60, p50=66.91, p90=137.72, p99=215.25, errors=0, error_pct=0.00),
    dict(concurrency=500, rps=2130.50, p50=232.32, p90=345.87, p99=471.29, errors=0, error_pct=0.00),
    dict(concurrency=1000, rps=2314.80, p50=428.21, p90=662.11, p99=894.70, errors=0, error_pct=0.00),
    dict(concurrency=2000, rps=1659.80, p50=1273.82, p90=1721.72, p99=1959.56, errors=0, error_pct=0.00),
    dict(concurrency=5000, rps=500.00, p50=10956.84, p90=11077.62, p99=11098.96, errors=5000, error_pct=100.00),
]

NETWORK_JAVA_T2 = [
    dict(concurrency=2000, rps=485.30, p50=4210.44, p90=7406.97, p99=9016.96, errors=0, error_pct=0.00),
    dict(concurrency=3000, rps=615.80, p50=5790.37, p90=8793.69, p99=10962.21, errors=157, error_pct=2.55),
    dict(concurrency=4000, rps=406.90, p50=10940.71, p90=11013.03, p99=11044.92, errors=4000, error_pct=98.30),
    dict(concurrency=5000, rps=2422.30, p50=1948.04, p90=3423.48, p99=5154.99, errors=24223, error_pct=100.00),
]

NETWORK_GO_T1 = [
    dict(concurrency=1, rps=19.10, p50=52.46, p90=52.69, p99=52.99, errors=0, error_pct=0.00),
    dict(concurrency=5, rps=95.00, p50=52.72, p90=53.20, p99=53.85, errors=0, error_pct=0.00),
    dict(concurrency=10, rps=190.00, p50=52.73, p90=53.47, p99=55.12, errors=0, error_pct=0.00),
    dict(concurrency=20, rps=380.00, p50=52.70, p90=53.41, p99=55.58, errors=0, error_pct=0.00),
    dict(concurrency=50, rps=945.10, p50=52.75, p90=53.95, p99=56.40, errors=0, error_pct=0.00),
    dict(concurrency=100, rps=1876.30, p50=52.66, p90=54.90, p99=67.75, errors=0, error_pct=0.00),
    dict(concurrency=200, rps=3617.10, p50=53.69, p90=59.49, p99=81.98, errors=0, error_pct=0.00),
    dict(concurrency=500, rps=8021.20, p50=59.37, p90=71.97, p99=143.24, errors=0, error_pct=0.00),
    dict(concurrency=1000, rps=10084.90, p50=93.90, p90=120.31, p99=237.52, errors=0, error_pct=0.00),
    dict(concurrency=2000, rps=8172.80, p50=227.37, p90=302.51, p99=558.10, errors=0, error_pct=0.00),
    dict(concurrency=5000, rps=5635.10, p50=856.83, p90=1027.44, p99=2121.45, errors=0, error_pct=0.00),
]

NETWORK_GO_T2 = [
    dict(concurrency=5000, rps=5239.10, p50=843.13, p90=1068.37, p99=2429.36, errors=0, error_pct=0.00),
    dict(concurrency=6000, rps=5390.40, p50=1073.02, p90=1426.45, p99=2027.26, errors=0, error_pct=0.00),
    dict(concurrency=7000, rps=3378.70, p50=1278.69, p90=5435.87, p99=5980.40, errors=0, error_pct=0.00),
    dict(concurrency=8000, rps=1554.60, p50=8031.67, p90=9144.78, p99=9851.18, errors=0, error_pct=0.00),
    dict(concurrency=9000, rps=1325.30, p50=14299.87, p90=21956.47, p99=22066.61, errors=13253, error_pct=100.00),
    dict(concurrency=10000, rps=1552.30, p50=14482.04, p90=18122.90, p99=18262.23, errors=15522, error_pct=99.99),
]

DISK_GO_T1 = [
    dict(concurrency=1, rps=132.10, p50=6.45, p90=8.26, p99=57.99, errors=0, error_pct=0.00),
    dict(concurrency=5, rps=197.60, p50=23.27, p90=27.98, p99=52.01, errors=0, error_pct=0.00),
    dict(concurrency=10, rps=197.80, p50=46.63, p90=52.14, p99=98.15, errors=0, error_pct=0.00),
    dict(concurrency=20, rps=201.40, p50=92.15, p90=102.52, p99=192.00, errors=0, error_pct=0.00),
    dict(concurrency=50, rps=202.00, p50=234.06, p90=255.66, p99=3107.23, errors=0, error_pct=0.00),
    dict(concurrency=100, rps=2292.80, p50=13.05, p90=34.66, p99=486.49, errors=21545, error_pct=93.97),
    dict(concurrency=200, rps=209.50, p50=459.94, p90=517.26, p99=10615.32, errors=16, error_pct=0.76),
    dict(concurrency=500, rps=237.90, p50=583.30, p90=10811.49, p99=10844.78, errors=237, error_pct=9.96),
    dict(concurrency=1000, rps=853.30, p50=228.84, p90=9788.97, p99=10788.54, errors=6718, error_pct=78.73),
    dict(concurrency=2000, rps=380.20, p50=3412.24, p90=10606.04, p99=10628.23, errors=1877, error_pct=49.37),
    dict(concurrency=5000, rps=2628.00, p50=2108.85, p90=10396.61, p99=10963.42, errors=24523, error_pct=93.31),
]

DISK_GO_T2 = [
    dict(concurrency=50, rps=196.00, p50=167.03, p90=None, p99=5057.63, errors=0, error_pct=0.00),
    dict(concurrency=60, rps=195.30, p50=231.79, p90=None, p99=4527.96, errors=0, error_pct=0.00),
    dict(concurrency=70, rps=364.60, p50=79.04, p90=None, p99=4575.41, errors=1697, error_pct=46.54),
    dict(concurrency=80, rps=7483.60, p50=1.47, p90=None, p99=246.55, errors=72844, error_pct=97.34),
    dict(concurrency=90, rps=2262.50, p50=10.64, p90=None, p99=384.17, errors=21167, error_pct=93.56),
    dict(concurrency=100, rps=387.30, p50=80.79, p90=None, p99=5424.52, errors=1894, error_pct=48.90),
]

DISK_JAVA_T1 = [
    dict(concurrency=1, rps=156.90, p50=5.35, p90=6.85, p99=35.33, errors=0, error_pct=0.00),
    dict(concurrency=5, rps=419.30, p50=5.85, p90=39.18, p99=48.06, errors=0, error_pct=0.00),
    dict(concurrency=10, rps=518.40, p50=7.80, p90=46.77, p99=55.19, errors=0, error_pct=0.00),
    dict(concurrency=20, rps=439.00, p50=45.36, p90=90.61, p99=137.85, errors=0, error_pct=0.00),
    dict(concurrency=50, rps=341.90, p50=145.98, p90=223.39, p99=296.59, errors=0, error_pct=0.00),
    dict(concurrency=100, rps=353.20, p50=278.12, p90=444.90, p99=610.09, errors=0, error_pct=0.00),
    dict(concurrency=200, rps=398.10, p50=446.00, p90=899.09, p99=1799.83, errors=0, error_pct=0.00),
    dict(concurrency=500, rps=505.00, p50=842.75, p90=2006.06, p99=3749.87, errors=0, error_pct=0.00),
    dict(concurrency=1000, rps=568.60, p50=1701.84, p90=3572.62, p99=5344.00, errors=0, error_pct=0.00),
    dict(concurrency=2000, rps=681.40, p50=2880.27, p90=6947.27, p99=10396.13, errors=124, error_pct=1.82),
    dict(concurrency=5000, rps=596.90, p50=10504.63, p90=10646.64, p99=10929.75, errors=4859, error_pct=81.40),
]

DISK_JAVA_T2 = [
    dict(concurrency=1000, rps=558.80, p50=1799.17, p90=None, p99=5654.96, errors=0, error_pct=0.00),
    dict(concurrency=1200, rps=576.60, p50=1900.56, p90=None, p99=7596.95, errors=4, error_pct=0.07),
    dict(concurrency=1500, rps=627.60, p50=2527.50, p90=None, p99=7460.27, errors=8, error_pct=0.13),
    dict(concurrency=1700, rps=692.70, p50=2367.69, p90=None, p99=8498.10, errors=17, error_pct=0.25),
    dict(concurrency=2000, rps=711.40, p50=2762.20, p90=None, p99=10404.73, errors=81, error_pct=1.14),
]

SERIES = {
    "network": {
        "test1": {"Java": NETWORK_JAVA_T1, "Go": NETWORK_GO_T1},
        "test2": {"Java": NETWORK_JAVA_T2, "Go": NETWORK_GO_T2},
    },
    "disk": {
        "test1": {"Java": DISK_JAVA_T1, "Go": DISK_GO_T1},
        "test2": {"Java": DISK_JAVA_T2, "Go": DISK_GO_T2},
    },
}

# last-clean / first-broken concurrency markers (from the article's breaking-point summary)
BREAKING_POINTS = {
    "network": {
        "Go": dict(last_clean=8000, first_broken=9000, inflight_last_clean=16000, inflight_first_broken=18000),
        "Java": dict(last_clean=2000, first_broken=3000, inflight_last_clean=4000, inflight_first_broken=6000),
    },
    "disk": {
        "Go": dict(last_clean=60, first_broken=70, inflight_last_clean=120, inflight_first_broken=140),
        "Java": dict(last_clean=1000, first_broken=1200, inflight_last_clean=2000, inflight_first_broken=2400),
    },
}

# approximate resource spikes called out in the article's prose
RESOURCE_USAGE = {
    "Network": {"Java": dict(memory_gib=1.0, cpu_cores=0.5), "Go": dict(memory_gib=0.5, cpu_cores=0.4)},
    "Disk": {"Java": dict(memory_gib=1.0, cpu_cores=0.5), "Go": None},  # Go disk-io OOM-killed, no stable spike
}

COLORS = {"Java": "#d97706", "Go": "#0284c7"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def ensure_dirs():
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(LINEAR_DIR, exist_ok=True)


def scale_dir(use_log):
    return LOG_DIR if use_log else LINEAR_DIR


def scale_suffix(use_log):
    return "log" if use_log else "linear"


def apply_scale(ax, use_log, x=True, y=True):
    if use_log:
        if x:
            ax.set_xscale("log")
        if y:
            ax.set_yscale("log")
    ax.grid(True, which="both", linestyle="--", alpha=0.4)


def savefig(fig, use_log, filename):
    path = os.path.join(scale_dir(use_log), filename)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {path}")


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------


def first_error_index(rows):
    """Index of the first row with any errors, or None if the whole run was clean."""
    for i, r in enumerate(rows):
        if r.get("errors", 0):
            return i
    return None


def truncate_to_first_break(rows):
    """Keep clean rows plus the first row where errors appear (the breaking point)."""
    idx = first_error_index(rows)
    if idx is None:
        return rows
    return rows[: idx + 1]


def plot_rps(workload, test_key, use_log):
    data = SERIES[workload][test_key]
    fig, ax = plt.subplots(figsize=(9, 6))
    for service, rows in data.items():
        rows = truncate_to_first_break(rows)
        broken = bool(rows[-1].get("errors", 0))
        # clean rows are connected by a line; the breaking point is an isolated marker
        clean_rows = rows[:-1] if broken else rows
        x = [r["concurrency"] for r in clean_rows]
        y = [r["rps"] for r in clean_rows]
        ax.plot(x, y, marker="o", color=COLORS[service], label=service)
        peak = max(rows, key=lambda r: r["rps"])
        ax.annotate(
            f"peak {peak['rps']:.0f} @ c={peak['concurrency']}",
            xy=(peak["concurrency"], peak["rps"]),
            xytext=(5, 8),
            textcoords="offset points",
            fontsize=8,
            color=COLORS[service],
        )
        if broken:
            bp = rows[-1]
            ax.scatter([bp["concurrency"]], [bp["rps"]], color="red", marker="X",
                       s=140, zorder=5, edgecolors="black", linewidths=0.8)
            ax.annotate(
                f"first error @ c={bp['concurrency']} ({bp['error_pct']:.1f}% err)",
                xy=(bp["concurrency"], bp["rps"]),
                xytext=(5, -14),
                textcoords="offset points",
                fontsize=8,
                color="red",
                fontweight="bold",
            )
    ax.set_xlabel("Concurrency (concurrent requests)")
    ax.set_ylabel("RPS (successful requests/sec)")
    ax.set_title(f"{workload.title()} I/O — RPS vs Concurrency ({test_key})")
    apply_scale(ax, use_log)
    ax.xaxis.set_major_locator(MultipleLocator(500))
    ax.legend()
    savefig(fig, use_log, f"{workload}_{test_key}_rps_{scale_suffix(use_log)}.png")


def plot_latency(workload, test_key, service, use_log):
    rows = SERIES[workload][test_key][service]
    x = [r["concurrency"] for r in rows]
    fig, ax = plt.subplots(figsize=(9, 6))
    for pct, style in (("p50", "-o"), ("p90", "-s"), ("p99", "-^")):
        ys = [r[pct] for r in rows]
        if all(v is None for v in ys):
            continue
        xs_plot = [xi for xi, v in zip(x, ys) if v is not None]
        ys_plot = [v for v in ys if v is not None]
        ax.plot(xs_plot, ys_plot, style, label=pct)
    ax.set_xlabel("Concurrency (concurrent requests)")
    ax.set_ylabel("Latency (ms)")
    ax.set_title(f"{workload.title()} I/O — {service} Latency vs Concurrency ({test_key})")
    apply_scale(ax, use_log)
    ax.legend()
    savefig(fig, use_log, f"{workload}_{test_key}_{service.lower()}_latency_{scale_suffix(use_log)}.png")


def plot_error_pct(workload, test_key, use_log):
    data = SERIES[workload][test_key]
    fig, ax = plt.subplots(figsize=(9, 6))
    for service, rows in data.items():
        x = [r["concurrency"] for r in rows]
        y = [r["error_pct"] for r in rows]
        ax.plot(x, y, marker="o", color=COLORS[service], label=service)
    ax.axhline(5, color="red", linestyle=":", linewidth=1, label="5% degradation threshold")
    ax.set_xlabel("Concurrency (concurrent requests)")
    ax.set_ylabel("Error rate (%)")
    ax.set_title(f"{workload.title()} I/O — Error % vs Concurrency ({test_key})")
    if use_log:
        ax.set_xscale("log")
        ax.grid(True, which="both", linestyle="--", alpha=0.4)
    else:
        ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend()
    savefig(fig, use_log, f"{workload}_{test_key}_error_pct_{scale_suffix(use_log)}.png")


def plot_breaking_point_bars(workload):
    bp = BREAKING_POINTS[workload]
    services = list(bp.keys())
    last_clean = [bp[s]["inflight_last_clean"] for s in services]
    first_broken = [bp[s]["inflight_first_broken"] for s in services]

    x = range(len(services))
    width = 0.35
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.bar([i - width / 2 for i in x], last_clean, width, label="Last clean (total in-flight)", color="#22c55e")
    ax.bar([i + width / 2 for i in x], first_broken, width, label="First broken (total in-flight)", color="#ef4444")
    ax.set_xticks(list(x))
    ax.set_xticklabels(services)
    ax.set_ylabel("Total in-flight operations (concurrency x 2)")
    ax.set_title(f"{workload.title()} I/O — Breaking Point Comparison")
    for i, v in enumerate(last_clean):
        ax.text(i - width / 2, v, str(v), ha="center", va="bottom", fontsize=9)
    for i, v in enumerate(first_broken):
        ax.text(i + width / 2, v, str(v), ha="center", va="bottom", fontsize=9)
    ax.legend()
    ax.grid(True, axis="y", linestyle="--", alpha=0.4)
    path = os.path.join(OUT_DIR, f"{workload}_breaking_point_bars.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {path}")


def plot_capacity_ratio():
    network_ratio = BREAKING_POINTS["network"]["Go"]["inflight_last_clean"] / BREAKING_POINTS["network"]["Java"]["inflight_last_clean"]
    disk_ratio = -(BREAKING_POINTS["disk"]["Java"]["inflight_last_clean"] / BREAKING_POINTS["disk"]["Go"]["inflight_last_clean"])

    labels = ["Network I/O\n(Go advantage)", "Disk I/O\n(Java advantage)"]
    values = [network_ratio, disk_ratio]
    colors = ["#0284c7" if v > 0 else "#d97706" for v in values]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.barh(labels, values, color=colors)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Capacity fold-change (positive = Go wins, negative = Java wins)")
    ax.set_title("Capacity Advantage Swap: Network I/O vs Disk I/O")
    for bar, v in zip(bars, values):
        ax.text(v, bar.get_y() + bar.get_height() / 2, f"{v:.1f}x", va="center",
                 ha="left" if v > 0 else "right", fontsize=10, fontweight="bold")
    ax.grid(True, axis="x", linestyle="--", alpha=0.4)
    path = os.path.join(OUT_DIR, "capacity_ratio_swap.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {path}")


def plot_resource_usage():
    workloads = list(RESOURCE_USAGE.keys())
    services = ["Java", "Go"]

    fig, (ax_mem, ax_cpu) = plt.subplots(1, 2, figsize=(12, 5))
    x = range(len(workloads))
    width = 0.35

    for i, service in enumerate(services):
        mem_vals = []
        cpu_vals = []
        for w in workloads:
            entry = RESOURCE_USAGE[w][service]
            mem_vals.append(entry["memory_gib"] if entry else 0)
            cpu_vals.append(entry["cpu_cores"] if entry else 0)
        offset = (i - 0.5) * width
        ax_mem.bar([xi + offset for xi in x], mem_vals, width, label=service, color=COLORS[service])
        ax_cpu.bar([xi + offset for xi in x], cpu_vals, width, label=service, color=COLORS[service])

    # annotate Go disk-io as OOM-killed instead of a bar value
    go_disk_index = workloads.index("Disk")
    ax_mem.text(go_disk_index + width / 2, 0.05, "OOM\nkilled", ha="center", va="bottom", fontsize=8, color=COLORS["Go"])
    ax_cpu.text(go_disk_index + width / 2, 0.02, "OOM\nkilled", ha="center", va="bottom", fontsize=8, color=COLORS["Go"])

    ax_mem.set_xticks(list(x))
    ax_mem.set_xticklabels(workloads)
    ax_mem.set_ylabel("Memory spike (GiB)")
    ax_mem.set_title("Memory Spike by Workload")
    ax_mem.legend()
    ax_mem.grid(True, axis="y", linestyle="--", alpha=0.4)

    ax_cpu.set_xticks(list(x))
    ax_cpu.set_xticklabels(workloads)
    ax_cpu.set_ylabel("CPU spike (cores)")
    ax_cpu.set_title("CPU Spike by Workload")
    ax_cpu.legend()
    ax_cpu.grid(True, axis="y", linestyle="--", alpha=0.4)

    fig.suptitle("Resource Usage Under Peak Load (approximate, from observed pod metrics)")
    path = os.path.join(OUT_DIR, "resource_usage.png")
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    ensure_dirs()

    for workload in ("network", "disk"):
        for test_key in ("test1", "test2"):
            for use_log in (True, False):
                plot_rps(workload, test_key, use_log)
                plot_error_pct(workload, test_key, use_log)
                for service in ("Java", "Go"):
                    plot_latency(workload, test_key, service, use_log)

        plot_breaking_point_bars(workload)

    plot_capacity_ratio()
    plot_resource_usage()


if __name__ == "__main__":
    main()
