"""Check real shader modules, quality combinations, and the installable distribution."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "horizon_lighting"
REVISION = "0a875da91dbb0fdcb7ba8c42c11341aa229af51a"
PROFILES = {
    "lite": {"quality_preset": "Lite"},
    "balanced": {"quality_preset": "Balanced"},
    "high": {"quality_preset": "High"},
    "ultra": {"quality_preset": "Ultra"},
}


def run_check(checker, path, label):
    result = subprocess.run([str(checker), "check", str(path), "--json"],
                            capture_output=True, text=True, encoding="utf-8")
    try:
        report = json.loads(result.stdout)[0]
    except (ValueError, IndexError) as exc:
        raise RuntimeError(f"Invalid checker output: {result.stdout}\n{result.stderr}") from exc
    report["path"] = label
    if result.returncode or not report["ok"]:
        raise RuntimeError(json.dumps(report, indent=2) + "\n" + result.stderr)
    print(f"{label}: official check passed ({len(report['stages'])} stages)")
    return report


def with_defaults(manifest, values):
    def update(match):
        block = match.group(0)
        option_id = re.search(r'^id = "([^"]+)"', block, re.M).group(1)
        if option_id not in values:
            return block
        # All profile defaults are JSON literals valid as TOML scalar values.
        return re.sub(r"^default = .*$", "default = " + json.dumps(values[option_id]), block, flags=re.M)
    return re.sub(r"(?ms)^\[\[options\]\].*?(?=^\[|\Z)", update, manifest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checker", required=True, type=Path)
    parser.add_argument("--package", action="store_true")
    args = parser.parse_args()
    report_dir = ROOT / "validation"
    report_dir.mkdir(exist_ok=True)
    reports = [run_check(args.checker, PACK, "source/default")]
    scratch = ROOT / ".tools"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="quality-", dir=scratch) as folder:
        for name, defaults in PROFILES.items():
            copy = Path(folder) / name
            shutil.copytree(PACK, copy)
            manifest = copy / "horizon-shaders.toml"
            manifest.write_text(with_defaults(manifest.read_text("utf-8"), defaults), encoding="utf-8")
            reports.append(run_check(args.checker, copy, name))
    manifest_data = tomllib.loads((PACK / "horizon-shaders.toml").read_text("utf-8"))
    pack_id = manifest_data["id"]
    version = manifest_data["version"]
    archive = ROOT / "dist" / f"{pack_id}-{version}.hshader"
    if args.package:
        archive.parent.mkdir(exist_ok=True)
        subprocess.run([str(args.checker), "pack", str(PACK), "--out", str(archive)], check=True)
    if archive.exists():
        reports.append(run_check(args.checker, archive, "distribution"))
    test = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT)
    latest_runtime = report_dir / version / "runtime.json"
    if not latest_runtime.exists():
        latest_runtime = report_dir / "latest-client-runtime.json"
    runtime = json.loads(latest_runtime.read_text("utf-8")) if latest_runtime.exists() else {}
    full_pack_visual = (runtime.get("full_pack_loaded") is True
                        and runtime.get("visual_captured") is True
                        and runtime.get("pack_sha256") == reports[0]["sha256"])
    evidence = {
        "upstream_revision": REVISION,
        "checks": reports,
        "package_contract_tests_passed": test.returncode == 0,
        "backends": ["SPIR-V (Vulkan)", "MSL (Metal)", "HLSL (DirectX)"],
        "official_checker_option_sets": ["defaults", "all minimums", "all maximums"],
        "full_pack_runtime_visual_verified": full_pack_visual,
        "full_pack_runtime_report": latest_runtime.relative_to(report_dir).as_posix()
        if latest_runtime.exists() else None,
        "performance_measured": runtime.get("performance", {}).get("short_fixture_gpu_timing", False),
        "comparative_shader_overhead_measured": False,
    }
    (report_dir / "checker.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return test.returncode


if __name__ == "__main__":
    sys.exit(main())
