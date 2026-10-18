"""End-to-end aero toolchain: raw -> database -> tables -> JSBSim XML.

CLI:
    python scripts/run_pipeline.py [--root aero]

The same logic is exposed as `run_pipeline(root) -> dict` for the test suite
(tests/conftest.py), so unit tests drive the identical code path that ships.

Steps (plan §8 pipeline):
  1. load configs           (aircraft_geometry / coordinate_mapping /
                             jsbsim_properties / cfd_case_matrix)
  2. parse raw              forceCoeffs/forces FO .dat per case
  3. build aero_raw.csv     as-parsed values + metadata
  4. normalize              -> aero_normalized.csv (SI) + metadata.json
  5. fit                    -> database/aero_tables.json (dimensionless)
  6. validate               structural checks (NaN, monotonic, envelope)
  7. generate               -> generated/aerodynamics.xml (SI->Imperial)
  8. compare                -> reports/coefficient_comparison.csv +
                               reports/validation_report.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent   # aero/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src._clock import generated_utc  # noqa: E402
from src.cfd_matrix import resolve_cases  # noqa: E402
from src.compare_jsbsim_cfd import compare  # noqa: E402
from src.fit_aero_tables import build_tables, write_tables  # noqa: E402
from src.generate_jsbsim_xml import generate_xml  # noqa: E402
from src.normalize_coefficients import (  # noqa: E402
    NORMALIZED_COLUMNS, RAW_COLUMNS,
    normalize_case, to_raw_row, write_csv,
)
from src.parse_force_coeffs import parse_force_coeffs  # noqa: E402
from src.parse_forces import parse_forces  # noqa: E402
from src.validate_tables import validate_normalized, validate_tables  # noqa: E402


def load_configs(root: Path) -> dict[str, dict]:
    return {
        key: yaml.safe_load((root / "config" / name).read_text(encoding="utf-8"))
        for key, name in (
            ("geometry", "aircraft_geometry.yaml"),
            ("mapping", "coordinate_mapping.yaml"),
            ("jsbsim", "jsbsim_properties.yaml"),
            ("matrix", "cfd_case_matrix.yaml"),
        )
    }


def parse_all_cases(root: Path, configs: dict[str, dict], cases: list[dict]) -> list[dict]:
    """Parse every case's FO outputs into merged {case, force_coeffs, forces}."""
    layout = configs["mapping"].get("forces_row_layout")
    out = []
    for case in cases:
        cid = case["id"]
        fc_file = root / "raw" / "forceCoeffs" / cid / "coefficient.dat"
        f_file = root / "raw" / "forces" / cid / "forces.dat"
        fc = parse_force_coeffs(
            fc_file, field_columns=configs["mapping"].get("force_coeffs_columns"))
        forces = parse_forces(f_file, layout=layout, prefix="")
        out.append({
            "case": case,
            "force_coeffs": fc,
            "forces": forces,
            "force_coeffs_file": str(fc_file.relative_to(root)) if fc_file.exists() else "",
            "forces_file": str(f_file.relative_to(root)) if f_file.exists() else "",
        })
    return out


def build_rows(
    cases_data: list[dict],
    geometry: dict,
    mapping: dict,
) -> tuple[list[dict], list[dict]]:
    raw_rows, norm_rows = [], []
    for cd in cases_data:
        raw_rows.append(to_raw_row(
            cd["case"], cd["force_coeffs"], cd["forces"],
            cd["force_coeffs_file"], cd["forces_file"]))
        norm_rows.append(normalize_case(
            cd["case"], geometry, mapping, cd["force_coeffs"], cd["forces"]))
    return raw_rows, norm_rows


def run_pipeline(root: Path, configs: dict[str, dict] | None = None,
                 generate_raw: bool = False) -> dict:
    """Run the full pipeline against an aero/ directory; returns artifacts.

    generate_raw=True invokes make_sample_force_coeffs to (re)create raw/ from
    the case matrix — used by the test suite's fixture and by --generate-raw.
    """
    root = Path(root)
    (root / "database").mkdir(parents=True, exist_ok=True)
    (root / "generated").mkdir(parents=True, exist_ok=True)
    (root / "reports").mkdir(parents=True, exist_ok=True)

    if generate_raw:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "make_sample_force_coeffs", ROOT / "scripts" / "make_sample_force_coeffs.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load make_sample_force_coeffs.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.main()

    cfg = configs or load_configs(root)
    matrix = cfg["matrix"]
    cases = resolve_cases(matrix)
    envelope = {
        "alpha": (cfg["geometry"].get("envelope", {}).get("alpha_min_deg"),
                  cfg["geometry"].get("envelope", {}).get("alpha_max_deg")),
        "beta": (cfg["geometry"].get("envelope", {}).get("beta_min_deg"),
                 cfg["geometry"].get("envelope", {}).get("beta_max_deg")),
    }

    cases_data = parse_all_cases(root, cfg, cases)
    raw_rows, norm_rows = build_rows(cases_data, cfg["geometry"], cfg["mapping"])

    write_csv(root / "database" / "aero_raw.csv", RAW_COLUMNS, raw_rows)
    write_csv(root / "database" / "aero_normalized.csv",
              NORMALIZED_COLUMNS, norm_rows)

    tables = build_tables(
        norm_rows, cfg["jsbsim"]["axes"], cfg["jsbsim"]["table_to_axis"],
        envelope={"LIFT": envelope["alpha"], "DRAG": envelope["alpha"],
                  "PITCH": envelope["alpha"],
                  "SIDE": envelope["beta"], "YAW": envelope["beta"],
                  "ROLL": envelope["beta"]})
    write_tables(root / "database" / "aero_tables.json", tables)

    errors, warnings = validate_tables(
        tables, cfg["jsbsim"]["axes"], cfg["jsbsim"]["table_to_axis"],
        envelope={"LIFT": envelope["alpha"], "DRAG": envelope["alpha"],
                  "PITCH": envelope["alpha"],
                  "SIDE": envelope["beta"], "YAW": envelope["beta"],
                  "ROLL": envelope["beta"]})
    n_errors, n_warn = validate_normalized(norm_rows)
    errors += n_errors
    warnings += n_warn

    xml = ""
    stats: dict = {}
    if not errors:
        xml = generate_xml(
            tables, cfg["jsbsim"], cfg["geometry"],
            template_dir=str(root / "templates"))
        (root / "generated" / "aerodynamics.xml").write_text(xml, encoding="utf-8")

        stats = compare(
            norm_rows, tables, cfg["jsbsim"]["axes"],
            cfg["jsbsim"]["table_to_axis"],
            root / "reports" / "coefficient_comparison.csv",
            root / "reports" / "validation_report.md")

    (root / "database" / "metadata.json").write_text(
        _metadata(configs or cfg, cases), encoding="utf-8")

    return {
        "errors": errors, "warnings": warnings,
        "tables": tables, "normalized_rows": norm_rows,
        "raw_rows": raw_rows, "cases": cases,
        "xml": xml,
        "generated_xml": root / "generated" / "aerodynamics.xml",
        "comparison_csv": root / "reports" / "coefficient_comparison.csv",
        "validation_md": root / "reports" / "validation_report.md",
        "stats": stats,
    }


def _metadata(configs: dict[str, dict], cases: list[dict]) -> str:
    import json

    return json.dumps({
        "generated": generated_utc(),
        "geometry_revision": configs["matrix"].get("geometry_revision", ""),
        "foam_version": configs["matrix"].get("foam_version", ""),
        "solver": configs["matrix"].get("solver", ""),
        "turbulence_model": configs["matrix"].get("turbulence_model", ""),
        "case_count": len(cases),
        "cases": [c["id"] for c in cases],
        "moment_reference": configs["mapping"].get("moment_reference", "cg"),
    }, indent=2)


def main() -> None:
    ap = argparse.ArgumentParser(description="slipstream aero pipeline")
    ap.add_argument("--root", type=Path, default=ROOT, help="aero/ directory")
    ap.add_argument("--generate-raw", action="store_true",
                    help="regenerate raw/ sample data from the case matrix")
    args = ap.parse_args()

    result = run_pipeline(args.root, generate_raw=args.generate_raw)
    for w in result["warnings"]:
        print(f"  warning: {w}")
    for e in result["errors"]:
        print(f"  ERROR:   {e}")
    if result["errors"]:
        print("pipeline aborted: validation errors; fix before generation")
        sys.exit(2)
    print("pipeline OK:")
    for axis, s in result["stats"].items():
        print(f"  {axis:6s} max_abs={s['max_abs']:.3e} rms={s['rms']:.3e}")
    print("  outputs: database/aero_raw.csv, aero_normalized.csv, "
          "aero_tables.json, metadata.json")
    print("           generated/aerodynamics.xml, reports/*")


if __name__ == "__main__":
    main()
