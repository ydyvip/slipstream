import { useState } from "react";
import { api, type RunDetail } from "../api";
import { useT } from "../i18n";

interface Props {
  run: RunDetail;
  onCreated: (id: string) => void;
  onClose: () => void;
}

/**
 * Re-solve on the run's existing mesh: only wind speed and prop thrust can
 * change, so meshing is skipped and the new run goes straight to the solver.
 */
export function ResolvePanel({ run, onCreated, onClose }: Props) {
  const t = useT();
  const props = run.config.props ?? [];
  const [windSpeed, setWindSpeed] = useState(String(run.config.wind_speed));
  const [thrust, setThrust] = useState(props.length ? String(props[0].thrust_g) : "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mixedThrust = props.some((p) => p.thrust_g !== props[0].thrust_g);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const ws = parseFloat(windSpeed);
    if (!Number.isFinite(ws) || ws <= 0 || ws >= 200) {
      setError(t("resolve.windSpeedError"));
      return;
    }
    let thrustG: number | undefined;
    if (props.length) {
      thrustG = parseFloat(thrust);
      if (!Number.isFinite(thrustG) || thrustG < 0) {
        setError(t("resolve.thrustError"));
        return;
      }
    }
    setSubmitting(true);
    setError(null);
    try {
      const { id } = await api.resolveRun(run.id, {
        wind_speed: ws,
        ...(thrustG !== undefined ? { thrust_g: thrustG } : {}),
      });
      onCreated(id);
    } catch (err) {
      setError(t("resolve.startFailed", { msg: (err as Error).message }));
      setSubmitting(false);
    }
  };

  return (
    <form className="panel resolve-panel" onSubmit={submit}>
      <div className="panel-head">{t("resolve.title")}</div>
      <div className="resolve-body">
        <div className="resolve-fields">
          <label className="field">
            <span className="field-label">{t("resolve.windSpeed")}</span>
            <input
              type="number"
              className="mono"
              value={windSpeed}
              min={0}
              step="any"
              onChange={(e) => setWindSpeed(e.target.value)}
            />
          </label>
          {props.length > 0 && (
            <label className="field">
              <span className="field-label">{t("resolve.thrustPerProp")}</span>
              <input
                type="number"
                className="mono"
                value={thrust}
                min={0}
                step="any"
                onChange={(e) => setThrust(e.target.value)}
              />
            </label>
          )}
        </div>
        <div className="config-note">
          {t("resolve.note", {
            cells: run.mesh_cells?.toLocaleString("en-US") ?? "",
          })}
          {mixedThrust && ` ${t("resolve.thrustEveryProp")}`}
          {run.config.refinement?.prop_slipstream &&
            ` ${t("resolve.slipstreamNote")}`}
        </div>
        {error && <div className="form-error">{error}</div>}
        <div className="resolve-actions">
          <button type="submit" className="btn btn-primary btn-sm" disabled={submitting}>
            {submitting ? t("resolve.starting") : t("resolve.startReSolve")}
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
            {t("resolve.cancel")}
          </button>
        </div>
      </div>
    </form>
  );
}
