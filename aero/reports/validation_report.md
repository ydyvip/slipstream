# Aero table vs CFD regression report

Generated: fitted 6 axes from 6 sweep cases.

Every DB point inside a fitted table's breakpoints is evaluated by the
same linear interpolation the JSBSim function uses, then compared to the
DB coefficient.  Zero error means the JSBSim function reproduces the CFD
point exactly; non-zero error signals a bug in fitting or generation.

| axis | points | max \|abs err\| | RMS | max \|rel err\| |
|---|---|---|---|---|
| DRAG | 10 | 0.00000 | 0.00000 | 0.00000 |
| SIDE | 10 | 0.00000 | 0.00000 | 0.00000 |
| LIFT | 10 | 0.00000 | 0.00000 | 0.00000 |
| PITCH | 10 | 0.00000 | 0.00000 | 0.00000 |
| YAW | 10 | 0.00000 | 0.00000 | 0.00000 |
| ROLL | 10 | 0.00000 | 0.00000 | 0.00000 |

**Verdict: PASS** (max abs error = 0.000000).

See coefficient_comparison.csv for case-level detail.
