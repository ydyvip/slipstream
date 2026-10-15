import { useState } from "react";
import {
  api,
  type MeshInspection,
  type MeshRole,
  type Quality,
} from "../api";
import { formatInt } from "../lib/format";
import { useT } from "../i18n";

interface Props {
  onCreated: (id: string) => void;
  onBack: () => void;
}

const ROLE_LABELS: Record<MeshRole, string> = {
  inlet: "mesh.roleInlet",
  outlet: "mesh.roleOutlet",
  model: "mesh.roleModel",
  slip: "mesh.roleSlip",
  wall: "mesh.roleWall",
  symmetry: "mesh.roleSymmetry",
};

const ITERATIONS: Record<Quality, number> = {
  coarse: 250,
  medium: 500,
  fine: 800,
};

/**
 * Solve on a mesh you built yourself: upload, inspect (convert + checkMesh +
 * patch list), assign a role to each patch, run.
 */
export function MeshImportView({ onCreated, onBack }: Props) {
  const t = useT();
  const [file, setFile] = useState<File | null>(null);
  const [unit, setUnit] = useState("m");
  const [inspecting, setInspecting] = useState(false);
  const [info, setInfo] = useState<MeshInspection | null>(null);
  const [roles, setRoles] = useState<Record<string, MeshRole>>({});
  const [name, setName] = useState("");
  const [windSpeed, setWindSpeed] = useState("15");
  const [quality, setQuality] = useState<Quality>("medium");
  const [refArea, setRefArea] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const inspect = async () => {
    if (!file) return;
    setInspecting(true);
    setError(null);
    setInfo(null);
    try {
      const result = await api.inspectMesh(file, unit);
      setInfo(result);
      setRoles(result.suggested_roles);
      setName(file.name.replace(/\.[^.]+$/, ""));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setInspecting(false);
    }
  };

  const counts = Object.values(roles).reduce<Record<string, number>>((acc, r) => {
    acc[r] = (acc[r] ?? 0) + 1;
    return acc;
  }, {});
  const missing = (["inlet", "outlet", "model"] as MeshRole[]).filter((r) => !counts[r]);

  const run = async () => {
    if (!info) return;
    const ws = parseFloat(windSpeed);
    if (!Number.isFinite(ws) || ws <= 0 || ws >= 200) {
      setError(t("mesh.windSpeedError"));
      return;
    }
    let ref: number | undefined;
    if (refArea.trim() !== "") {
      ref = parseFloat(refArea);
      if (!Number.isFinite(ref) || ref <= 0) {
        setError(t("mesh.refAreaError"));
        return;
      }
    }
    setSubmitting(true);
    setError(null);
    try {
      const { id } = await api.importRun({
        import_id: info.id,
        roles,
        wind_speed: ws,
        quality,
        ...(name.trim() ? { name: name.trim() } : {}),
        ...(ref ? { ref_area_cm2: ref } : {}),
      });
      onCreated(id);
    } catch (err) {
      setError(t("mesh.startFailed", { msg: (err as Error).message }));
      setSubmitting(false);
    }
  };

  return (
    <div className="mesh-import">
      <header className="mesh-import-head">
        <button type="button" className="btn btn-ghost btn-sm" onClick={onBack}>
          {t("mesh.backToStlSetup")}
        </button>
        <h1>{t("mesh.title")}</h1>
        <p className="config-note">{t("mesh.importNote")}</p>
      </header>

      <section className="panel">
        <div className="panel-head">{t("mesh.stepMeshFile")}</div>
        <div className="mesh-import-body">
          <div className="mesh-import-row">
            <label className="field">
              <span className="field-label">{t("mesh.file")}</span>
              <input
                type="file"
                accept=".msh,.cas,.zip"
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setInfo(null);
                }}
              />
            </label>
            <label className="field">
              <span className="field-label">{t("mesh.meshUnits")}</span>
              <select value={unit} onChange={(e) => setUnit(e.target.value)}>
                <option value="m">{t("mesh.unitMeters")}</option>
                <option value="mm">{t("mesh.unitMillimeters")}</option>
                <option value="cm">{t("mesh.unitCentimeters")}</option>
                <option value="in">{t("mesh.unitInches")}</option>
              </select>
            </label>
          </div>
          <div>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={!file || inspecting}
              onClick={() => void inspect()}
            >
              {inspecting ? t("mesh.converting") : t("mesh.inspect")}
            </button>
          </div>
        </div>
      </section>

      {info && (
        <section className="panel">
          <div className="panel-head">{t("mesh.stepPatches")}</div>
          <div className="mesh-import-body">
            <div className="mono config-note">
              {info.format} · {t("mesh.cells", { n: formatInt(info.cells) })} ·{" "}
              {info.mesh_ok
                ? t("mesh.checkMeshOk")
                : info.failed_checks === 1
                  ? t("mesh.checkMeshFailOne")
                  : t("mesh.checkMeshFailMany", { n: info.failed_checks })}
              {info.bounds_m &&
                ` · ${t("mesh.domainX", {
                  a: info.bounds_m[0][0].toFixed(3),
                  b: info.bounds_m[1][0].toFixed(3),
                })}`}
            </div>
            <div className="mesh-import-table">
              <table>
                <thead>
                  <tr>
                    <th>{t("mesh.colPatch")}</th>
                    <th>{t("mesh.colFaces")}</th>
                    <th>{t("mesh.colCenterX")}</th>
                    <th>{t("mesh.colRole")}</th>
                  </tr>
                </thead>
                <tbody>
                  {info.patches.map((p) => (
                    <tr key={p.name}>
                      <td className="mono">{p.name}</td>
                      <td className="mono">{formatInt(p.faces)}</td>
                      <td className="mono">
                        {p.center_m ? p.center_m[0].toFixed(3) : "—"}
                      </td>
                      <td>
                        <select
                          aria-label={t("mesh.roleFor", { name: p.name })}
                          value={roles[p.name]}
                          onChange={(e) =>
                            setRoles((r) => ({ ...r, [p.name]: e.target.value as MeshRole }))
                          }
                        >
                          {(Object.keys(ROLE_LABELS) as MeshRole[]).map((r) => (
                            <option key={r} value={r}>
                              {t(ROLE_LABELS[r])}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {missing.length > 0 && (
              <div className="form-error">
                {t("mesh.missingRoles", { roles: missing.join(", ") })}
              </div>
            )}
          </div>
        </section>
      )}

      {info && (
        <section className="panel">
          <div className="panel-head">{t("mesh.stepConditions")}</div>
          <div className="mesh-import-body">
            <div className="mesh-import-row">
              <label className="field">
                <span className="field-label">{t("mesh.runName")}</span>
                <input value={name} onChange={(e) => setName(e.target.value)} />
              </label>
              <label className="field">
                <span className="field-label">{t("mesh.windSpeed")}</span>
                <input
                  type="number"
                  className="mono"
                  value={windSpeed}
                  min={0}
                  step="any"
                  onChange={(e) => setWindSpeed(e.target.value)}
                />
              </label>
              <label className="field">
                <span className="field-label">{t("mesh.solverBudget")}</span>
                <select
                  value={quality}
                  onChange={(e) => setQuality(e.target.value as Quality)}
                >
                  {(Object.keys(ITERATIONS) as Quality[]).map((q) => (
                    <option key={q} value={q}>
                      {t("mesh.iterations", { n: ITERATIONS[q] })}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span className="field-label">{t("mesh.refAreaOptional")}</span>
                <input
                  type="number"
                  className="mono"
                  value={refArea}
                  min={0}
                  step="any"
                  placeholder={t("mesh.refAreaAuto")}
                  onChange={(e) => setRefArea(e.target.value)}
                />
              </label>
            </div>
            <div>
              <button
                type="button"
                className="btn btn-primary"
                disabled={submitting || missing.length > 0}
                onClick={() => void run()}
              >
                {submitting ? t("mesh.starting") : t("mesh.runOnMesh")}
              </button>
            </div>
          </div>
        </section>
      )}

      {error && <div className="form-error mesh-import-error">{error}</div>}
    </div>
  );
}
