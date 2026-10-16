# Aero table vs CFD regression report

Generated: fitted 6 axes from 6 sweep cases.

Every DB point inside a fitted table's breakpoints is evaluated by the
same linear interpolation the JSBSim function uses, then compared to the
DB coefficient.  Zero error means the JSBSim function reproduces the CFD
point exactly; non-zero error signals a bug in fitting or generation.

| axis | points | max \|abs err\| | RMS | max \|rel err\| |
|---|---|---|---|---|
| DRAG | 10 | 0.01822 | 0.00696 | 0.15237 |
| SIDE | 10 | 0.00881 | 0.00367 | 55.70456 |
| LIFT | 10 | 0.04510 | 0.01912 | 0.42276 |
| PITCH | 10 | 0.34810 | 0.18466 | 5.72114 |
| YAW | 10 | 0.00496 | 0.00213 | 21.05384 |
| ROLL | 10 | 0.00412 | 0.00176 | 2.84735 |

**Verdict: REVIEW** (max abs error = 0.348100).

See coefficient_comparison.csv for case-level detail.
