#!/usr/bin/env python3
"""Generate r29 statistics, charts and a report from immutable measured records.

Run with Python 3.8+ and numpy/matplotlib (analysis only, outside timed runs).
"""
import hashlib
import json
import pathlib
from collections import Counter
from itertools import combinations

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments/r29-v353-v1"
OUT = ROOT / "results/summaries"
PLOTS = ROOT / "docs/r29-plots"
VERSIONS = ("v2.1.2", "v3.5.0", "v3.5.3")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def describe(values, label):
    if not values:
        return {"count": 0}
    a = np.asarray(values, dtype=float)
    seed = int(hashlib.sha256(label.encode()).hexdigest()[:8], 16)
    ci = None
    if len(a) > 1:
        sampled = np.random.default_rng(seed).choice(a, size=(10000, len(a)), replace=True)
        ci = np.quantile(np.median(sampled, axis=1), [.025, .975]).tolist()
    q25, q75 = np.quantile(a, [.25, .75])
    mean = float(np.mean(a))
    std = float(np.std(a, ddof=1)) if len(a) > 1 else None
    return dict(count=len(a), median=float(np.median(a)), mean=mean, stdev=std,
                cv=std / mean if std is not None and mean else None,
                minimum=float(min(a)), maximum=float(max(a)), p25=float(q25), p75=float(q75),
                iqr=float(q75-q25), median_95pct_bootstrap_ci=ci)


def metric_values(row):
    values = {"elapsed_ns": row.get("elapsed_ns"),
              "throughput_ops_per_second": row["operation_count"] * 1e9 / row["elapsed_ns"],
              "user_cpu_ns": row.get("user_cpu_ns"), "system_cpu_ns": row.get("system_cpu_ns"),
              "end_rss_bytes": row.get("peak_rss_bytes"),
              "minor_faults": row.get("page_faults", {}).get("minor"),
              "major_faults": row.get("page_faults", {}).get("major")}
    if isinstance(row.get("user_cpu_ns"), int) and isinstance(row.get("system_cpu_ns"), int):
        values["cpu_ns_per_operation"] = (row["user_cpu_ns"] + row["system_cpu_ns"]) / row["operation_count"]
    if row["profile"] == "memory-return":
        for field in ("rss_before_burst_bytes", "working_set_rss_bytes", "rss_after_free_bytes",
                      "rss_after_idle_bytes", "allocation_elapsed_ns", "free_elapsed_ns",
                      "reallocation_elapsed_ns", "reallocation_minor_faults",
                      "allocation_minor_faults", "memory_action_count", "memory_action_elapsed_ns"):
            values[field] = row.get(field)
        denominator = row["working_set_rss_bytes"] - row["rss_before_burst_bytes"]
        for sample in row["rss_observations"]:
            offset = sample["offset_ms"]
            values["rss_{}_bytes".format(offset)] = sample["rss_bytes"]
            values["returned_fraction_{}".format(offset)] = (
                1 - (sample["rss_bytes"] - row["rss_before_burst_bytes"]) / denominator
                if denominator > 0 else None)
        # Memory timing contains deliberate idle; throughput is not an allocator metric.
        values.pop("throughput_ops_per_second", None)
        values.pop("end_rss_bytes", None)
        values.pop("cpu_ns_per_operation", None)
    if row["profile"] == "latency":
        values["latency_sample_count"] = row.get("latency_sample_count")
        for name, value in row.get("latency_percentiles_ns", {}).items():
            values[name + "_ns"] = value
    for name in ("queue_full_wait_count", "queue_empty_wait_count", "backpressure_ns"):
        if name in row:
            values[name] = row[name]
    return {key: value for key, value in values.items() if isinstance(value, (float, int))}


def byte_checksum(count):
    low_cycles, low_tail = divmod(count, 256)
    low = low_cycles * 32640 + low_tail * (low_tail-1) // 2
    high_cycles, high_tail = divmod(count, 65536)
    high_whole, high_partial = divmod(high_tail, 256)
    high = high_cycles * 8355840 + 256 * high_whole * (high_whole-1) // 2 + high_whole * high_partial
    return low + high


def validate_core_checksum(row):
    if row["profile"] != "core":
        return
    count = row["operation_count"]
    if row["scenario"] == "local_churn":
        expected = row["thread_count"] * byte_checksum(count // row["thread_count"])
    else:
        expected = byte_checksum(count)
        if (row["transferred_pointer_count"] != count or row["freed_pointer_count"] != count or
                row["outstanding_pointer_count"] != 0):
            raise ValueError("remote pointer accounting failed")
    if row["checksum"] != expected:
        raise ValueError("core checksum disagrees with deterministic workload")


def summarize(plan, rows):
    plan_hash = digest(EXP / "plan.json")
    expected = {a["version"]: a for a in plan["allocators"]}
    invalid = Counter()
    selected = {}
    for row in rows:
        arm = expected.get(row["allocator_version"])
        if (row["comparison_id"] != plan["comparison_id"] or row["plan_sha256"] != plan_hash or
                arm is None or row["allocator_commit"] != arm["commit"] or
                row["measurement_stage"] != "measured"):
            raise ValueError("raw data provenance does not match frozen r29 measured plan")
        if not row["valid"]:
            invalid[row["invalid_reason"]] += 1
            continue
        validate_core_checksum(row)
        key = (row["block_id"], row["repetition"], row["allocator_version"])
        if key not in selected or row["attempt"] > selected[key]["attempt"]:
            selected[key] = row
    blocks = []
    for block in plan["blocks"]:
        wanted = block.get("repetitions", plan["block_defaults"]["repetitions"])
        matched = []
        for repetition in range(1, wanted+1):
            arms = [selected.get((block["block_id"], repetition, v)) for v in VERSIONS]
            if all(arm is not None for arm in arms):
                matched.append({v: metric_values(arm) for v, arm in zip(VERSIONS, arms)})
        names = sorted({name for group in matched for arm in group.values() for name in arm})
        metrics = {}
        for name in names:
            label = block["block_id"] + ":" + name
            by_version = {v: describe([g[v][name] for g in matched if name in g[v]], label+v) for v in VERSIONS}
            paired = []
            for denominator, numerator in combinations(VERSIONS, 2):
                pairs = [(g[denominator].get(name), g[numerator].get(name)) for g in matched]
                pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
                paired.append(dict(numerator=numerator, denominator=denominator,
                    ratio=describe([b/a for a, b in pairs if a != 0], label+numerator+denominator+"ratio"),
                    difference=describe([b-a for a, b in pairs], label+numerator+denominator+"difference")))
            metrics[name] = dict(by_version=by_version, paired=paired)
        blocks.append(dict(block_id=block["block_id"], profile=block["profile"],
                           required_repetitions=wanted, complete_matched_repetitions=len(matched), metrics=metrics))
    complete = all(b["required_repetitions"] == b["complete_matched_repetitions"] for b in blocks)
    return dict(comparison_id=plan["comparison_id"], plan_sha256=plan_hash,
                analysis=dict(numpy_version=np.__version__, bootstrap_resamples=10000,
                              statistic="median", quantile_method="linear"),
                execution_status="Complete" if complete else ("Partial" if rows else "Not executed"),
                total_attempts=len(rows), valid_unique_records=len(selected), invalid_reasons=dict(invalid),
                blocks=blocks, raw_timestamp_range=[min((r["timestamp"] for r in rows), default=None),
                                                   max((r["completed_at"] for r in rows), default=None)])


def ratio_text(metric, pair=2):
    entry = metric["paired"][pair]["ratio"]
    if not entry["count"]:
        return "unavailable"
    ci = entry["median_95pct_bootstrap_ci"]
    return "{:.4f} [{:.4f}, {:.4f}]".format(entry["median"], *ci) if ci else "{:.4f}".format(entry["median"])


def report(summary):
    lines = ["# mimalloc v3.5.3 성능 비교 (r29)", "", "Execution status: " + summary["execution_status"],
             "Design status: Frozen (r29-v353-v1)", "",
             "v2.1.2·v3.5.0·v3.5.3을 같은 환경에서 새로 실행했다. 과거 관측값은 합치지 않았다.", "",
             "- 유효한 고유 실행: {}; 전체 시도: {}.".format(summary["valid_unique_records"], summary["total_attempts"]),
             "- 실행 시각(UTC): {} ~ {}.".format(*summary["raw_timestamp_range"]),
             "- 검증: smoke 39/39, 파일럿 63/63, 버전별 첫 C++ 할당 1000개 스레드 통과.",
             "- AMD Ryzen 7 5700X, VM이 노출하는 8 cores (vCPU cpuset 0,2,4,6,8,10,12,14), node 0, THP madvise.",
             "- Rocky Linux 8.9, GCC 8.5.0, glibc 2.28, WSL2 kernel 6.6.87.2, VM RAM 32036 MiB.",
             "- 이미지: `sha256:73353c7a70d01f098f4adc96480273ce5d5b295bea3733c1f2faac2017e05877`.",
             "- 모든 버전에 동일한 r28 benchmark binary를 사용했다. 소스·빌드 옵션·해시는 [artifacts.json](../experiments/r29-v353-v1/artifacts.json)에 있다.", "",
             "## 처리량", "", "기본 정책 비교. 수치는 median M allocations/s; 비율은 같은 block의 v3.5.3/v3.5.0 median과 bootstrap 95% CI다. 비율 >1이면 v3.5.3이 빠르다.", "",
             "| Workload | matched n | v2.1.2 | v3.5.0 | v3.5.3 | v3.5.3/v3.5.0 [95% CI] |",
             "|---|---:|---:|---:|---:|---:|"]
    for block in summary["blocks"]:
        if block["profile"] != "core" or not block["metrics"]: continue
        metric = block["metrics"]["throughput_ops_per_second"]
        lines.append("| {} | {} | {} | {} |".format(block["block_id"], block["complete_matched_repetitions"],
                     " | ".join("{:.3f}".format(metric["by_version"][v]["median"] / 1e6) for v in VERSIONS), ratio_text(metric)))
    lines += ["", "세 버전의 paired 처리량 비율 (median [95% CI]):", "",
              "| Workload | v3.5.0/v2.1.2 | v3.5.3/v2.1.2 | v3.5.3/v3.5.0 |", "|---|---:|---:|---:|"]
    for block in summary["blocks"]:
        if block["profile"] != "core" or not block["metrics"]: continue
        metric = block["metrics"]["throughput_ops_per_second"]
        lines.append("| {} | {} |".format(block["block_id"], " | ".join(ratio_text(metric, i) for i in range(3))))
    lines += ["", "![Core throughput ratios](r29-plots/core-ratios.svg)", "", "## CPU 시간", "",
              "User + system CPU ns/allocation의 median. 여러 worker의 CPU 시간이 합산된다. 비율 <1이면 allocation당 CPU 사용량이 적다.", "",
              "| Workload | v2.1.2 | v3.5.0 | v3.5.3 | v3.5.3/v3.5.0 [95% CI] |", "|---|---:|---:|---:|---:|"]
    for block in summary["blocks"]:
        if block["profile"] != "core" or "cpu_ns_per_operation" not in block["metrics"]: continue
        metric = block["metrics"]["cpu_ns_per_operation"]
        lines.append("| {} | {} | {} |".format(block["block_id"],
                     " | ".join("{:.1f}".format(metric["by_version"][v]["median"]) for v in VERSIONS), ratio_text(metric)))
    lines += ["", "## 메모리 반환", "",
              "512 MiB를 page-touch 후 해제하고 5초 관찰했다. 수치는 baseline RSS를 뺀 반환율(%). Purge delay만 일치시킨 결과는 THP·통계 기능까지 완전히 정규화한 결과가 아니다.", "",
              "| Condition | matched n | v2.1.2 | v3.5.0 | v3.5.3 | 다음 burst 시간 v3.5.3/v3.5.0 [95% CI] |", "|---|---:|---:|---:|---:|---:|"]
    for block in summary["blocks"]:
        if block["profile"] != "memory-return" or not block["metrics"]: continue
        metric = block["metrics"]["returned_fraction_5000"]
        lines.append("| {} | {} | {} | {} |".format(block["block_id"], block["complete_matched_repetitions"],
                     " | ".join("{:.2f}%".format(100 * metric["by_version"][v]["median"]) for v in VERSIONS),
                     ratio_text(block["metrics"]["reallocation_elapsed_ns"])))
    lines += ["", "v3.5.3의 절대 비용과 해제 후 RSS (중앙값):", "",
              "| Condition | 5초 RSS (MiB) | free (ms) | collect/activity 합계 (ms) | 다음 burst (ms) |", "|---|---:|---:|---:|---:|"]
    for block in summary["blocks"]:
        if block["profile"] != "memory-return" or not block["metrics"]: continue
        quantities = (("rss_5000_bytes", 2**20), ("free_elapsed_ns", 1e6),
                      ("memory_action_elapsed_ns", 1e6), ("reallocation_elapsed_ns", 1e6))
        lines.append("| {} | {} |".format(block["block_id"], " | ".join(
            "{:.2f}".format(block["metrics"][name]["by_version"]["v3.5.3"]["median"] / scale) for name, scale in quantities)))
    lines += ["", "![Memory RSS](r29-plots/memory-rss.svg)", "", "## 지연시간", "",
              "별도 pipeline workload의 1/1024 표본. 측정 구간은 malloc 및 ingress 작업 이후부터 free 직전까지로, 큐 체류·중간 처리 지연이며 malloc/free 호출 지연이 아니다. 서비스 record 계산 제거 결함은 상단 정정 및 하네스 감사를 참고한다. 수치는 ns, 각 percentile의 실행 간 median이며 비율 <1이 짧은 지연시간이다. 표본 개수도 summary JSON에 기록했다.", "",
              "| Workload | matched n | v2.1.2 | v3.5.0 | v3.5.3 | v3.5.3/v3.5.0 [95% CI] |", "|---|---:|---:|---:|---:|---:|"]
    for block in summary["blocks"]:
        if block["profile"] != "latency" or "p99_ns" not in block["metrics"]: continue
        for name in ("p50_ns", "p99_ns", "p99_9_ns"):
            metric = block["metrics"][name]
            lines.append("| {} / {} | {} | {} | {} |".format(block["block_id"], name, block["complete_matched_repetitions"],
                         " | ".join("{:.0f}".format(metric["by_version"][v]["median"]) for v in VERSIONS), ratio_text(metric)))
    lines += ["", "## 통계·실패·해석 범위", "",
              "각 셀에 대해 평균·중앙값·표준편차·CV·범위·사분위수·IQR·95% CI와 세 버전 간 모든 paired ratio/difference를 [summary JSON](../results/summaries/summary-r29.json)에 저장했다. CPU 시간, page faults, RSS, p50/p99/p99.9 등 실제 제공된 필드도 포함한다.", "",
              "Invalid reasons: `" + json.dumps(summary["invalid_reasons"], ensure_ascii=False) + "`. Invalid 시도는 삭제하지 않으며 재시도 기록도 보존한다. 불완전한 3버전 block은 비교에 포함하지 않는다. 단순히 느리거나 빠른 표본은 제거하지 않는다.", "",
              "로컬·remote core는 기존 하네스에서 warm-up이 구현되어 있지 않다. local timing에는 작은 vector 준비와 join이 포함되며 remote에는 shared atomic checksum 비용이 포함된다. 따라서 순수 allocator 명령 비용으로 일반화할 수 없다. memory-return은 8-CPU cpuset 내 단일 스레드로 실행한다. 모든 시나리오에서 worker CPU 실측값을 내보내지는 않는다.", "",
              "v3.5.3 기본값에는 THP 보존 정책, 통계·프로파일링 기능 변경이 포함된다. free 개선만을 원인으로 단정하지 않는다. core의 기존 `peak_rss_bytes` 필드는 실제 peak가 아닌 종료 시점 RSS여서 집계에는 `end_rss_bytes`로 표시했다. perf cycles/instructions 및 get_mempolicy는 권한 거부로 unavailable이다. THP 사용량을 모든 실행에서 직접 측정하지 못했고 host 주파수·Windows 부하·VM 스케줄링은 통제하지 못했다. CI는 다중 비교 보정을 하지 않았다.", "",
              "## 재현", "", "```bash", "python -m unittest discover -s benchmark/tests -p 'test_*.py'",
              "bash scripts/container/run_active.sh --stage measured --status",
              "bash scripts/container/run_active.sh --stage measured --execute --max-blocks 0",
              "python scripts/analyze_r29.py", "```", "",
              "이미 기록이 존재하면 runner가 완료된 arm을 건너뛴다. 새 환경·소스·binary·설정의 측정은 새 revision/namespace를 사용한다. Draft smoke/pilot은 보존된 draft-plan.json에 해당하며 동결 후 smoke를 재실행해 덮어쓰지 않는다. Raw: `results/active/r29-v353-v1/`. Contract, calibration, environment: `experiments/r29-v353-v1/`.", ""]
    if summary.get("queue_control"):
        lines += ["## Queue-only 대조 실행", "",
                  "4:4 queue로 포인터 값만 전달한 별도 진단이다. 버전당 3회이며 allocator workload의 시간에서 빼지 않는다. 처리량은 M pointer transfers/s.", "",
                  "| Library loaded | n | median | CV |", "|---|---:|---:|---:|"]
        for version, stats in summary["queue_control"].items():
            lines.append("| {} | {} | {:.3f} | {:.1f}% |".format(version, stats["count"], stats["median"]/1e6, stats["cv"]*100))
        lines.append("")
    if summary["execution_status"] == "Complete":
        interpretation = (EXP / "interpretation.ko.md").read_text(encoding="utf-8")
        lines[6:6] = ["", interpretation, ""]
    lines += ["## 추가 환경·workload 명세", "",
              "컨테이너 network=none, CPU quota=0, cpuset mems=0이다. 별도 container memory limit은 설정하지 않았으며 VM에는 8 GiB swap이 구성되어 있다. 물리 host CPU pinning과 모든 실행의 swap 사용량은 검증하지 않았다. 이미지 값은 로컬 빌드 image ID이며 원격 registry에서 그대로 pull할 수 있는 주소는 아니다.", "",
              "Core mixed-wide는 16 B부터 64 KiB까지 13개 2의 거듭제곱 크기를 순서대로 순환한다. 1-worker/8-worker, batch 32, random free이며 정확한 operation count는 calibration.json에 있다. Core fixed는 64 B, 8 workers, batch 1이다. Remote는 4 producers/4 consumers이며 queue capacity 등은 plan.json에 고정했다.", "",
              "CMake Release -O3 -DNDEBUG, shared malloc override, secure/tracking 비활성화 조건이다. v3.5.3의 CMAKE_CXX_FLAGS_RELEASE 미사용 경고는 C-only allocator 빌드에서 발생했다. 실제 C flags와 CMakeCache는 artifacts.json에 보존했다. 원본 소스는 수정하지 않았다.", ""]
    (ROOT / "docs/experiment-report-r29.md").write_bytes("\n".join(lines).encode("utf-8"))


def plots(summary):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    PLOTS.mkdir(exist_ok=True)
    core = [b for b in summary["blocks"] if b["profile"] == "core" and b["metrics"]]
    if core:
        fig, ax = plt.subplots(figsize=(9, 4.5), layout="constrained")
        for i, block in enumerate(core):
            stat = block["metrics"]["throughput_ops_per_second"]["paired"][2]["ratio"]
            ci = stat["median_95pct_bootstrap_ci"] or [stat["median"]] * 2
            ax.errorbar(stat["median"], i, xerr=[[stat["median"]-ci[0]], [ci[1]-stat["median"]]], fmt="o", color="#137c8b", capsize=4)
        ax.axvline(1, color="#555", linestyle="--")
        ax.set_yticks(range(len(core)), [b["block_id"].replace("core-", "") + " (n={})".format(b["complete_matched_repetitions"]) for b in core])
        ax.set_xlim(0, max(1.25, ax.get_xlim()[1]))
        ax.set_xlabel("Throughput ratio v3.5.3 / v3.5.0; >1 favors v3.5.3")
        ax.set_title("Upstream defaults | THP madvise | matched median and 95% CI")
        fig.savefig(PLOTS / "core-ratios.svg")
        fig.savefig(ROOT / "build/r29-core-preview.png", dpi=150)
        plt.close(fig)
    memory = [b for b in summary["blocks"] if b["profile"] == "memory-return" and b["metrics"]]
    if memory:
        fig, axes = plt.subplots(2, 3, figsize=(12, 7), layout="constrained")
        for ax, block in zip(axes.flat, memory):
            for version in VERSIONS:
                vals = [block["metrics"]["rss_{}_bytes".format(t)]["by_version"][version] for t in (0, 10, 100, 1000, 5000)]
                ax.plot(range(5), [v["median"]/2**20 for v in vals], "o-", label=version)
                ax.fill_between(range(5), [v["p25"]/2**20 for v in vals], [v["p75"]/2**20 for v in vals], alpha=.12)
            ax.set_xticks(range(5), ["0", "10", "100", "1000", "5000"])
            ax.set_ylim(bottom=0)
            ax.set_title(block["block_id"].replace("memory-", "") + " (n={})".format(block["complete_matched_repetitions"]), fontsize=10)
            ax.set_xlabel("Checkpoint after free (ms; categorical spacing)")
            ax.set_ylabel("Absolute RSS (MiB)")
        axes.flat[0].legend()
        fig.suptitle("512 MiB working set | THP madvise | medians and IQR")
        fig.savefig(PLOTS / "memory-rss.svg")
        fig.savefig(ROOT / "build/r29-memory-preview.png", dpi=150)
        plt.close(fig)


def main():
    plan = json.loads((EXP / "plan.json").read_text())
    paths = sorted((ROOT / "results/active/r29-v353-v1/measured/raw").glob("*.json"))
    rows = [json.loads(p.read_text()) for p in paths]
    summary = summarize(plan, rows)
    control = [json.loads(p.read_text()) for p in (ROOT / "results/active/r29-v353-v1/queue-control/raw").glob("*.json")]
    summary["queue_control"] = {v: describe([r["operation_count"]*1e9/r["elapsed_ns"] for r in control
                                            if r["allocator_version"] == v and r["valid"]], "queue-control"+v)
                                for v in VERSIONS} if control else {}
    OUT.mkdir(exist_ok=True)
    (OUT / "summary-r29.json").write_text(json.dumps(summary, indent=2) + "\n")
    evidence = sorted((ROOT / "results/active/r29-v353-v1").glob("*/raw/*.json"))
    (EXP / "raw-index.json").write_text(json.dumps([dict(path=str(p.relative_to(ROOT)).replace("\\", "/"), sha256=digest(p)) for p in evidence], indent=2) + "\n")
    plots(summary)
    report(summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "blocks"}, indent=2))


if __name__ == "__main__":
    main()
