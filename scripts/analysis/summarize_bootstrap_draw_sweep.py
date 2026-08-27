"""How much do the Figure 4 bands move when the draw count moves?

`run_merge_curves.py` used 400 repository bootstrap draws while every other
analysis in the repository uses 1,000 to 10,000. The point estimates are
deterministic and cannot move; only the bands can. This compares the bands
produced at several draw counts against the 2,000-draw reference, so the
appendix can state the Monte-Carlo error of the bands rather than assert a
draw count.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = ROOT / "outputs" / "constant_sensitivity"

ARMS = ("no_edge", "with_edge", "no_reply", "reply_off_target", "reply_on_target")
DRAW_COUNTS = (400, 1000, 2000, 4000)
REFERENCE_DRAWS = 2000


def load(directory: Path, draws: int) -> pd.DataFrame:
    return pd.read_csv(directory / f"merge_curves_draws_{draws}" / "cumulative_merge.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep-dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args()

    tables = {draws: load(args.sweep_dir, draws) for draws in DRAW_COUNTS}
    reference = tables[REFERENCE_DRAWS]

    point_columns = [f"merged_{arm}" for arm in ARMS]
    for draws, table in tables.items():
        if not np.allclose(
            table[point_columns].to_numpy(), reference[point_columns].to_numpy()
        ):
            raise AssertionError(
                f"Point estimates moved between {draws} and {REFERENCE_DRAWS} draws; "
                "they are deterministic and must not."
            )

    rows: list[dict[str, object]] = []
    for draws, table in tables.items():
        for arm in ARMS:
            for edge in ("low", "high"):
                column = f"merged_{arm}_{edge}"
                delta = (table[column] - reference[column]).to_numpy() * 100.0
                rows.append(
                    {
                        "bootstrap_draws": draws,
                        "arm": arm,
                        "band_edge": edge,
                        "reference_draws": REFERENCE_DRAWS,
                        "max_abs_shift_pp": float(np.abs(delta).max()),
                        "mean_abs_shift_pp": float(np.abs(delta).mean()),
                        "day_30_shift_pp": float(delta[-1]),
                        "day_30_value_pp": float(table[column].iloc[-1] * 100.0),
                    }
                )
    detail = pd.DataFrame(rows)
    detail.to_csv(args.sweep_dir / "bootstrap_draws_band_shift.csv", index=False)

    width_rows: list[dict[str, object]] = []
    for draws, table in tables.items():
        for arm in ARMS:
            width = (
                table[f"merged_{arm}_high"] - table[f"merged_{arm}_low"]
            ).to_numpy() * 100.0
            reference_width = (
                reference[f"merged_{arm}_high"] - reference[f"merged_{arm}_low"]
            ).to_numpy() * 100.0
            width_rows.append(
                {
                    "bootstrap_draws": draws,
                    "arm": arm,
                    "mean_band_width_pp": float(width.mean()),
                    "day_30_band_width_pp": float(width[-1]),
                    "mean_width_change_vs_reference_pp": float(
                        (width - reference_width).mean()
                    ),
                    "day_30_width_change_vs_reference_pp": float(
                        width[-1] - reference_width[-1]
                    ),
                }
            )
    widths = pd.DataFrame(width_rows)
    widths.to_csv(args.sweep_dir / "bootstrap_draws_band_width.csv", index=False)

    qualitative: list[dict[str, object]] = []
    for draws, table in tables.items():
        summary = json.loads(
            (
                args.sweep_dir / f"merge_curves_draws_{draws}" / "summary.json"
            ).read_text(encoding="utf-8")
        )
        diagnostics = summary["three_arm_overlap_diagnostics"]
        qualitative.append(
            {
                "bootstrap_draws": draws,
                "off_target_on_target_bands_overlap_whole_horizon": diagnostics[
                    "off_target_on_target_bands_overlap_whole_horizon"
                ],
                "off_target_on_target_band_overlap_share": diagnostics[
                    "off_target_on_target_band_overlap_share"
                ],
                "no_reply_band_below_off_target_at_day_30": diagnostics[
                    "no_reply_band_below_off_target_at_day_30"
                ],
                "no_reply_band_below_on_target_at_day_30": diagnostics[
                    "no_reply_band_below_on_target_at_day_30"
                ],
                "merged_by_day_30_reply_on_target_ci": summary[
                    "merged_by_day_30_reply_on_target_ci"
                ],
                "merged_by_day_30_no_reply_ci": summary["merged_by_day_30_no_reply_ci"],
                "merged_by_day_30_reply_off_target_ci": summary[
                    "merged_by_day_30_reply_off_target_ci"
                ],
            }
        )
    conclusions = pd.DataFrame(qualitative)
    conclusions.to_csv(
        args.sweep_dir / "bootstrap_draws_conclusions.csv", index=False
    )

    payload = {
        "point_estimates_identical_across_draw_counts": True,
        "reference_draws": REFERENCE_DRAWS,
        "max_abs_band_shift_pp_by_draw_count": {
            str(draws): float(
                detail.loc[detail["bootstrap_draws"] == draws, "max_abs_shift_pp"].max()
            )
            for draws in DRAW_COUNTS
        },
        "mean_abs_band_shift_pp_by_draw_count": {
            str(draws): float(
                detail.loc[
                    detail["bootstrap_draws"] == draws, "mean_abs_shift_pp"
                ].mean()
            )
            for draws in DRAW_COUNTS
        },
        "qualitative_conclusions": qualitative,
    }
    (args.sweep_dir / "bootstrap_draws_summary.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
