import { useCallback, useEffect, useState } from "react";
import { api, type GroupDetail, type GroupMember } from "../api";
import { usePoll } from "../hooks/usePoll";
import { useT } from "../i18n";
import { isTerminal, StatusPill } from "./StatusPill";
import { formatCoeff } from "../lib/format";
import { downloadText, matrixToCsv, slugify } from "../lib/download";
import { uniqueSorted } from "../lib/program";

interface Props {
  groupId: string;
  /** v10.1: when set, fetch the whole batched program via /api/programs/{pid}
   * (all batches joined) instead of this group's single batch. */
  programId?: string;
  /** The member currently open in the detail view (highlighted, not clickable). */
  activeRunId: string;
  onSelectRun: (id: string) => void;
}

const DELTA_KEYS = ["delta_e_deg", "delta_a_deg", "delta_r_deg"] as const;
const DELTA_MARK: Record<(typeof DELTA_KEYS)[number], string> = {
  delta_e_deg: "δe",
  delta_a_deg: "δa",
  delta_r_deg: "δr",
};

/** 5 -> "5", 2.5 -> "2.5": keep matrix axis labels short and readable. */
function fmtDeg(v: number): string {
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

/**
 * v10: progress for a multi-dimensional test program (case-matrix group). If
 * the group sweeps alpha × beta it renders a grid with one cell per
 * (α, β) pair — members that share a cell (extra deflection dims) stack as
 * small pills. Otherwise it falls back to the plain per-run list. Polls
 * /api/groups/{gid} every ~3s until every member settles, like SweepPanel.
 */
export function MatrixPanel({ groupId, programId, activeRunId, onSelectRun }: Props) {
  const t = useT();
  const fetchGroup = useCallback(
    () => (programId ? api.getProgram(programId) : api.getGroup(groupId)),
    [programId, groupId],
  );
  const [group, setGroup] = useState<GroupDetail | null>(null);
  const allSettled =
    group !== null && group.runs.every((r) => isTerminal(r.status));
  const poll = usePoll(fetchGroup, 3000, !allSettled);
  useEffect(() => {
    if (poll.data) setGroup(poll.data);
  }, [poll.data]);

  if (group === null) {
    return (
      <section className="panel">
        <div className="panel-head">{t("matrix.title")}</div>
        <div className="sweep-loading">
          {poll.error
            ? t("matrix.loadFailed", { message: poll.error.message })
            : t("matrix.loading")}
        </div>
      </section>
    );
  }

  const members = group.runs;
  const settled = members.filter((m) => isTerminal(m.status)).length;
  const alphas = uniqueSorted(members.map((m) => m.alpha_deg));
  const betas = uniqueSorted(members.map((m) => m.beta_deg));
  const isGrid = alphas.length > 0 && betas.length > 0;
  const hasDeltas = members.some((m) =>
    DELTA_KEYS.some((k) => m[k] != null),
  );

  // A member's non-α/β dims, e.g. "δe 5° · δa 0°"; empty for a pure α×β cell.
  const deltaSummary = (m: GroupMember): string =>
    DELTA_KEYS.filter((k) => m[k] != null)
      .map((k) =>
        t("matrix.deltaValue", { mark: DELTA_MARK[k], deg: m[k] as number }),
      )
      .join(" · ");
  const memberLabel = (m: GroupMember): string =>
    deltaSummary(m).trim() || t("matrix.caseLabel");

  const exportCsv = () =>
    downloadText(`${slugify(group.name)}_matrix.csv`, matrixToCsv(members));

  const pill = (m: GroupMember) => {
    const active = m.id === activeRunId;
    return (
      <button
        key={m.id}
        type="button"
        className={`matrix-pill${active ? " matrix-pill-active" : ""}`}
        disabled={active}
        onClick={() => onSelectRun(m.id)}
        title={t("matrix.cellTitle", { a: m.alpha_deg ?? 0, b: m.beta_deg ?? 0 })}
      >
        <StatusPill status={m.status} />
        {hasDeltas && (
          <span className="matrix-pill-delta mono">{deltaSummary(m)}</span>
        )}
        {m.status === "done" && m.cd !== null && (
          <span className="matrix-pill-cd mono">Cd {formatCoeff(m.cd)}</span>
        )}
        {!isTerminal(m.status) && (
          <span className="matrix-pill-cd mono">
            {Math.round(m.progress * 100)}%
          </span>
        )}
      </button>
    );
  };

  return (
    <section className="panel">
      <div className="panel-head">
        {t("matrix.title")}
        <span className="panel-head-meta">
          {t("sweep.metaSpeed", { speed: group.wind_speed })} ·{" "}
          {group.quality} ·{" "}
          {t("sweep.metaFinished", { settled, total: members.length })}
          {group.batch_count != null &&
            group.batch_count > 1 &&
            group.batch_index != null && (
              <>
                {" "}
                ·{" "}
                {t("matrix.partOf", {
                  n: group.batch_index + 1,
                  total: group.batch_count,
                })}
              </>
            )}
        </span>
        <button
          className="seg sweep-export"
          title={t("matrix.exportCsvTitle")}
          onClick={exportCsv}
        >
          {t("matrix.exportCsv")}
        </button>
      </div>

      {isGrid ? (
        <>
          <div className="config-note matrix-grid-title">
            {t("matrix.gridTitle")}
          </div>
          <div className="matrix-grid-wrap">
            <table className="matrix-grid">
              <thead>
                <tr>
                  <th className="matrix-corner" title={t("matrix.cornerTitle")}>
                    α\β
                  </th>
                  {betas.map((b) => (
                    <th
                      key={b}
                      className="matrix-beta-head mono"
                      title={t("matrix.betaTitle")}
                    >
                      {t("matrix.betaValue", { deg: fmtDeg(b) })}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {alphas.map((a) => (
                  <tr key={a}>
                    <th
                      className="matrix-alpha-head mono"
                      title={t("matrix.alphaTitle")}
                    >
                      {t("matrix.alphaValue", { deg: fmtDeg(a) })}
                    </th>
                    {betas.map((b) => {
                      const cell = members.filter(
                        (m) => m.alpha_deg === a && m.beta_deg === b,
                      );
                      return (
                        <td key={b} className="matrix-cell">
                          {cell.length > 1 ? (
                            <div className="matrix-stack">{cell.map(pill)}</div>
                          ) : (
                            cell.map(pill)
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <>
          <div className="config-note matrix-grid-title">
            {t("matrix.listHint")}
          </div>
          <div className="sweep-members">
            {members.map((m) => {
              const active = m.id === activeRunId;
              return (
                <div
                  key={m.id}
                  className={`sweep-member${active ? " sweep-member-active" : ""}`}
                  onClick={() => !active && onSelectRun(m.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) =>
                    e.key === "Enter" && !active && onSelectRun(m.id)
                  }
                >
                  <span className="sweep-member-yaw mono">{memberLabel(m)}</span>
                  <StatusPill status={m.status} />
                  {m.status === "done" && m.cd !== null && (
                    <span className="sweep-member-cd mono">
                      Cd {formatCoeff(m.cd)}
                    </span>
                  )}
                  {!isTerminal(m.status) && (
                    <span className="sweep-member-cd mono">
                      {Math.round(m.progress * 100)}%
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
}
