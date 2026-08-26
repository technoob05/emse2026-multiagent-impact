# Independent AI-assisted screening report

Source: `outputs/manual_audit/direct_handoff_manual_audit.csv`  
Labels: `tmp/manual_label_legacy.csv`  
Date: 2026-08-25

## Scope

This is an independent **AI-assisted screening**, not human validation. It used only the two PR titles, the example shared path and path class, and the time gap supplied in the source file. GitHub URLs were retained in the output but were not needed to assign these labels. The screen does not infer that a maintainer or contributor intentionally handed work from one agent to another.

`likely_same_task=yes` required clear semantic continuity in the titles plus a compatible shared path. Broadly related work in the same subsystem was marked `unclear`; a shared lockfile, README, changelog, package manifest, or other incidental path was not enough.

## Results

| Label | Rows | Share |
|---|---:|---:|
| Yes | 13 | 11.9% |
| Unclear | 16 | 14.7% |
| No | 80 | 73.4% |

Confidence distribution:

- `yes`: 9 high, 4 medium;
- `unclear`: 13 medium, 3 low;
- `no`: 69 high, 11 medium.

Path evidence helped but did not solve task identity:

| Path class | Yes | Unclear | No | Total |
|---|---:|---:|---:|---:|
| Generic-only | 3 | 6 | 40 | 49 |
| Non-generic | 10 | 10 | 40 | 60 |

Thus, only 16.7% of the non-generic-path sample was clearly the same task. A file overlap alone remains a weak proxy.

Among the 49 changed-agent rows, only 5 (10.2%) were screened as likely the same task; 9 were unclear and 35 were likely different tasks. These five cases are evidence of cross-agent task continuity, but still not evidence of an intentional handoff.

## Important diagnostic for the paper

Only 3 of the 13 likely-same-task rows were marked `recovered_within_30d`, while 49 of the 80 likely-different-task rows were marked recovered. This means the current “recovery” flag mostly captures whether a later PR succeeded, not whether the failed task itself was recovered.

The artifact-handoff story therefore needs a stricter outcome:

1. first establish task continuity through title/path/issue evidence;
2. then measure whether that successor integrates;
3. report same-agent and changed-agent continuity separately;
4. call the current broad metric “successful successor within 30 days,” not “task recovery.”

## Clear positive examples

- BoxModule type alias to struct wrapper → BoxModule newtype wrapper.
- Gallery transparency in frameless window → transparent gallery view in Windows frameless mode.
- Curve-handle display issue → stabilized curve/levels handle UI.
- Tailscale Serve connection fix → broader Tailscale integration fix.
- Shell completion addition → revert/follow-up in completion copying.
- Persist PR filters → add PR label filtering.
- Android sample/emulator test workflow → Android instrumentation execution in CI.

The row-level CSV includes a concise reason and an explicit `intentional_handoff=not_inferred` field for every episode.
