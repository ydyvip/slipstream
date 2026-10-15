import { useEffect, useState } from "react";
import { api, type History, type RunDetail } from "../api";
import { LineChart, type ChartSeries } from "./LineChart";
import {
  formatArea,
  formatCoeff,
  formatDuration,
  formatForce,
  formatInt,
} from "../lib/format";
import { useT } from "../i18n";

// Distinct series colors for the two compared runs (A / B).
const C_A = "#3987e5";
const C_B = "#c98500";

interface Props {
  aId: string;
  bId: string;
  onExit: () => void;
  onOpenRun: (id: string) => void;
}

interface Loaded {
  detail: RunDetail;
  history: History | null;
}

interface Row {
  label: string;
  value: (d: RunDetail) => number | null;
  fmt: (v: number) => string;
  /** Show a % delta (sensible for positive magnitudes only). */
  pct: boolean;
  /** Color the delta: lower = better (drag-like metrics). */
  lowerBetter?: boolean;
}

const ROWS: Row[] = [
  {
    label: "compare.dragCoeff",
    value: (d) => d.result?.cd ?? null,
    fmt: (v) => formatCoeff(v),
    pct: true,
    lowerBetter: true,
  },
  {
    label: "compare.liftCoeff",
    value: (d) => d.result?.cl ?? null,
    fmt: (v) => formatCoeff(v),
    pct: false,
  },
  {
    label: "compare.dragForce",
    value: (d) => d.result?.drag_N ?? null,
    fmt: formatForce,
    pct: true,
    lowerBetter: true,
  },
  {
    label: "compare.liftForce",
    value: (d) => d.result?.lift_N ?? null,
    fmt: formatForce,
    pct: false,
  },
  {
    label: "compare.frontalArea",
    value: (d) => d.result?.frontal_area_m2 ?? null,
    fmt: formatArea,
    pct: true,
  },
  {
    label: "compare.meshCells",
    value: (d) => d.result?.mesh_cells ?? null,
    fmt: formatInt,
    pct: true,
  },
  {
    label: "compare.runtime",
    value: (d) => d.result?.runtime_s ?? null,
    fmt: formatDuration,
    pct: true,
  },
];

/**
 * Side-by-side comparison of two finished runs: stat columns with an
 * explicit delta column (Δ = B − A) and both Cd convergence histories
 * overlaid on one chart. Data is fetched once — both runs are done.
 */
export function CompareView({ aId, bId, onExit, onOpenRun }: Props) {
  const t = useT();
  const [data, setData] = useState<[Loaded, Loaded] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    const load = async (id: string): Promise<Loaded> => {
      const detail = await api.getRun(id);
      let history: History | null = null;
      try {
        history = await api.getHistory(id);
      } catch {
        /* history is optional for the overlay */
      }
      return { detail, history };
    };
    Promise.all([load(aId), load(bId)])
      .then((d) => {
        if (!cancelled) setData(d as [Loaded, Loaded]);
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [aId, bId]);

  if (data === null) {
    return (
      <div className="detail detail-loading">
        {error
          ? t("compare.loadFailed", { msg: error })
          : t("compare.loading")}
      </div>
    );
  }

  const [a, b] = data;
  const cdSeries: ChartSeries[] = [];
  if (a.history && a.history.iters.length > 0) {
    cdSeries.push({
      name: t("compare.seriesA", { name: a.detail.name }),
      color: C_A,
      x: a.history.iters,
      y: a.history.cd,
    });
  }
  if (b.history && b.history.iters.length > 0) {
    cdSeries.push({
      name: t("compare.seriesB", { name: b.detail.name }),
      color: C_B,
      x: b.history.iters,
      y: b.history.cd,
    });
  }

  const runHead = (label: "A" | "B", run: Loaded, id: string, color: string) => (
    <th>
      <button className="compare-run-link" onClick={() => onOpenRun(id)}>
        <span className="legend-swatch" style={{ background: color }} />
        {t("compare.runHead", { letter: label, name: run.detail.name })}
      </button>
      <div className="compare-run-sub mono">
        {t("compare.runSub", {
          yaw: run.detail.config.yaw_deg,
          speed: run.detail.config.wind_speed,
          quality: run.detail.config.quality,
        })}
      </div>
    </th>
  );

  return (
    <div className="detail">
      <header className="detail-header">
        <div className="detail-title">
          <h1>{t("compare.title")}</h1>
        </div>
        <div className="detail-meta mono">
          {t("compare.vsMeta", { a: a.detail.name, b: b.detail.name })}
        </div>
        <button className="btn btn-sm" onClick={onExit}>
          {t("compare.exit")}
        </button>
      </header>

      <section className="panel">
        <div className="panel-head">
          {t("compare.resultsSideBySide")}
          <span className="panel-head-meta">Δ = B − A</span>
        </div>
        <div className="compare-table-wrap">
          <table className="data-table compare-table">
            <thead>
              <tr>
                <th />
                {runHead("A", a, aId, C_A)}
                {runHead("B", b, bId, C_B)}
                <th>Δ</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => {
                const va = row.value(a.detail);
                const vb = row.value(b.detail);
                let delta = "—";
                let cls = "";
                if (va !== null && vb !== null) {
                  const d = vb - va;
                  const sign = d >= 0 ? "+" : "−";
                  delta = `${sign}${row.fmt(Math.abs(d))}`;
                  if (row.pct && va !== 0) {
                    delta += ` (${sign}${Math.abs((d / va) * 100).toFixed(1)}%)`;
                  }
                  if (row.lowerBetter && d !== 0) {
                    cls = d < 0 ? " delta-good" : " delta-bad";
                  }
                }
                return (
                  <tr key={row.label}>
                    <td className="compare-metric">{t(row.label)}</td>
                    <td className="mono">{va !== null ? row.fmt(va) : "—"}</td>
                    <td className="mono">{vb !== null ? row.fmt(vb) : "—"}</td>
                    <td className={`mono compare-delta${cls}`}>{delta}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">{t("compare.cdOverlay")}</div>
        <div className="charts charts-one">
          <LineChart
            title={t("compare.cdChartTitle")}
            xLabel={t("compare.cdChartXLabel")}
            series={cdSeries}
          />
        </div>
      </section>
    </div>
  );
}
