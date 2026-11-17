"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    metric_ids = [m["id"] for m in spec.get("metrics", [])]
    # 1. NaN / inf anywhere in the reported metrics (a naive `nan < min` is False and sails through).
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v}")
    # 2. rows vs manifest, and vs the baseline's (item, seed) grid.
    rows = pr.get("rows") or []
    pman, bman = pr.get("manifest") or {}, base.get("manifest") or {}
    n_seeds = len(pman.get("seeds") or [])
    want_pr = int(pman.get("items", 0)) * n_seeds
    want_base = int(bman.get("items", 0)) * len(bman.get("seeds") or [])
    if len(rows) != want_pr:
        problems.append(f"{len(rows)} rows but manifest says {pman.get('items')} items x {n_seeds} seeds = {want_pr}")
    if len(rows) != want_base:
        problems.append(f"{len(rows)} rows but the baseline has {want_base} (dropped or duplicated rows)")
    pr_keys = Counter((r.get("item_id"), r.get("seed")) for r in rows)
    base_keys = Counter((r.get("item_id"), r.get("seed")) for r in base.get("rows") or [])
    if pr_keys != base_keys:
        extra, missing = pr_keys - base_keys, base_keys - pr_keys
        problems.append(f"(item, seed) set differs from baseline: {sum(missing.values())} missing, "
                        f"{sum(extra.values())} extra/duplicated")
    if set(pman.get("seeds") or []) != set(bman.get("seeds") or []):
        problems.append(f"manifest seeds {pman.get('seeds')} != baseline seeds {bman.get('seeds')}")
    # 3. broken graders: evaluator_failures, or a graded metric that is None/absent in some row.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s), first: {pr['evaluator_failures'][0]}")
    graded = [m for m in metric_ids if any(m in r for r in base.get("rows") or [])]
    for m in graded:
        missing_n = sum(1 for r in rows if r.get(m) is None)
        if missing_n:
            problems.append(f"{missing_n} row(s) with no value for graded metric {m} (a crashed grader drops out of the mean)")
    # 4. reported metrics must be reproducible from the rows (no hand-edited aggregates).
    for m in graded:
        vals = [r[m] for r in rows if r.get(m) is not None]
        reported = (pr.get("metrics") or {}).get(m)
        if not vals or reported is None:
            continue
        kind = next(x for x in spec["metrics"] if x["id"] == m).get("kind")
        got = sum(vals) if kind == "safety" else sum(vals) / len(vals)
        if abs(got - float(reported)) > 1e-3:
            problems.append(f"metric {m} reported {reported} but its rows give {got:.4f}")
    # 4b. pass_5 and pass@k / pass^k are not per-row columns, so recompute them from the rows too
    #     (a hand-edited pass_hat_5 would otherwise sail through while the rows still show the flake).
    by_item: dict[str, list[bool]] = {}
    for r in rows:
        by_item.setdefault(r.get("item_id"), []).append(bool(r.get("pass_rate")))
    reported_all = pr.get("metrics") or {}
    if by_item and "pass_rate" in graded:
        derived = {"pass_5": sum(all(v) for v in by_item.values()) / len(by_item)}
        for k in spec.get("pass_k", []):
            if min(len(v) for v in by_item.values()) >= k:
                for name, fn in (("pass_at", stats.pass_at_k), ("pass_hat", stats.pass_hat_k)):
                    est = [fn(len(v), sum(v), k) for v in by_item.values()]
                    derived[f"{name}_{k}"] = sum(est) / len(est)
        for key, got in derived.items():
            reported = reported_all.get(key)
            if reported is not None and abs(got - float(reported)) > 1e-3:
                problems.append(f"metric {key} reported {reported} but its rows give {got:.4f}")
    # 5. slice tags must not be relabelled relative to the baseline.
    base_tags = {r["item_id"]: set(r.get("slices") or []) for r in base.get("rows") or []}
    moved = sorted({r["item_id"] for r in rows
                    if r.get("item_id") in base_tags and set(r.get("slices") or []) != base_tags[r["item_id"]]})
    if moved:
        problems.append(f"slice tags changed vs baseline for {', '.join(moved)}")
    # 6. ratchet: thresholds may only get stricter on the same eval-set version.
    if base_spec is not None and base_spec.get("eval_set_version") == spec.get("eval_set_version"):
        problems += _ratchet(base_spec.get("metrics", []), spec.get("metrics", []), "metric", "id")
        problems += _ratchet(base_spec.get("slices", []), spec.get("slices", []), "slice", "name")
    return problems


def _th(entry: dict) -> dict:
    """Threshold of a metric (nested under 'threshold') or of a slice (flat keys)."""
    th = dict(entry.get("threshold") or {})
    for k in ("min", "max", "max_increase", "no_significant_drop"):
        if k in entry:
            th[k] = entry[k]
    return th


def _ratchet(old: list[dict], new: list[dict], what: str, key: str) -> list[str]:
    out, cur = [], {x[key]: x for x in new}
    for o in old:
        n = cur.get(o[key])
        if n is None:
            out.append(f"ratchet: {what} {o[key]} was removed")
            continue
        ot, nt = _th(o), _th(n)
        if o.get("blocking") and not n.get("blocking"):
            out.append(f"ratchet: {what} {o[key]} is no longer blocking")
        if "max" in ot and nt.get("max", math.inf) > ot["max"]:
            out.append(f"ratchet: {what} {o[key]} max raised {ot['max']} -> {nt.get('max')}")
        if "min" in ot and nt.get("min", -math.inf) < ot["min"]:
            out.append(f"ratchet: {what} {o[key]} min lowered {ot['min']} -> {nt.get('min')}")
        if "max_increase" in ot and nt.get("max_increase", math.inf) > ot["max_increase"]:
            out.append(f"ratchet: {what} {o[key]} max_increase raised {ot['max_increase']} -> {nt.get('max_increase')}")
        if ot.get("no_significant_drop") and not nt.get("no_significant_drop"):
            out.append(f"ratchet: {what} {o[key]} dropped no_significant_drop")
        if o.get("metric") and n.get("metric") != o.get("metric"):
            out.append(f"ratchet: {what} {o[key]} now measures {n.get('metric')} instead of {o.get('metric')}")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    bs = spec.get("bootstrap", {})
    blocked, lines = [], []
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        sid = f"slice:{name}/{metric}"
        if not a:
            verdict, val, note = "fail", None, "no rows carry this slice"
        else:
            val, verdict, note = sum(a.values()) / len(a), "ok", ""
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            if sl.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                       n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}] n={len(keys)}"
                    if hi < 0:
                        verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = "ok" if verdict == "ok" else ("BLOCK" if sl.get("blocking") else "warn")
        shown = "None" if val is None else f"{val:.4f}"
        lines.append(f"  {sid:<34} {shown:<8} {json.dumps({'min': sl.get('min')}):<14} {note:<34} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
