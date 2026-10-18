import { useState } from "react";
import { useT } from "../i18n";
import type { RunStatus, RunSummary } from "../api";
import { groupProgramRuns, type ProgramRunGroup } from "../lib/program";
import { StatusPill } from "./StatusPill";
import { StorageFooter } from "./StorageFooter";
import { formatCoeff, formatTimestamp, shortRunId } from "../lib/format";

interface Props {
  runs: RunSummary[] | null;
  activeId: string | null;
  /** Cd values for done runs (fetched lazily by App). */
  cdById: Record<string, number>;
  /** Run ids currently selected for comparison (0–2). */
  compareIds: string[];
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onToggleCompare: (id: string) => void;
  onOpenCompare: () => void;
  onClearCompare: () => void;
  /** Bumped whenever the run list changes, so storage usage refetches. */
  refreshKey: number;
  onPruned: () => void;
  /** v10.2: program-level cancel / delete of a collapsed case-matrix program. */
  onCancelProgram: (programId: string, programName: string, unfinished: number) => void;
  onDeleteProgram: (programId: string, programName: string, total: number) => void;
}

/** Statuses counted as finished in a program's done/total summary. */
const TERMINAL: ReadonlySet<RunStatus> = new Set(["done", "error", "cancelled"]);

export function Sidebar({
  runs,
  activeId,
  cdById,
  compareIds,
  onSelect,
  onNew,
  onDelete,
  onToggleCompare,
  onOpenCompare,
  onClearCompare,
  refreshKey,
  onPruned,
  onCancelProgram,
  onDeleteProgram,
}: Props) {
  const t = useT();
  // v10.2: program ids whose member rows are expanded. Defaults to collapsed so
  // a multi-hundred-run program shows as a single row instead of a 500-line wall.
  const [expandedPrograms, setExpandedPrograms] = useState<Set<string>>(() => new Set());

  const toggleProgram = (programId: string) => {
    setExpandedPrograms((prev) => {
      const next = new Set(prev);
      if (next.has(programId)) next.delete(programId);
      else next.add(programId);
      return next;
    });
  };

  const renderRunItem = (r: RunSummary, nested: boolean) => {
    const inCompare = compareIds.includes(r.id);
    return (
      <div
        key={r.id}
        className={`run-item${r.id === activeId ? " run-item-active" : ""}${nested ? " run-item-nested" : ""}`}
        onClick={() => onSelect(r.id)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && onSelect(r.id)}
      >
        <div className="run-item-top">
          <span className="run-item-name" title={r.name}>
            {r.name}
          </span>
          {r.status === "done" && (
            <button
              className={`icon-btn compare-btn${inCompare ? " compare-btn-active" : ""}`}
              title={
                inCompare
                  ? t("sidebar.removeFromCompare")
                  : t("sidebar.selectForCompare")
              }
              onClick={(e) => {
                e.stopPropagation();
                onToggleCompare(r.id);
              }}
            >
              ⇄
            </button>
          )}
          <button
            className="icon-btn run-item-delete"
            title={t("sidebar.deleteRun")}
            onClick={(e) => {
              e.stopPropagation();
              onDelete(r.id);
            }}
          >
            ✕
          </button>
        </div>
        <div className="run-item-bottom">
          <StatusPill status={r.status} />
          {r.status === "done" && cdById[r.id] !== undefined && (
            <span className="run-item-cd mono">
              {t("sidebar.cd")} {formatCoeff(cdById[r.id])}
            </span>
          )}
          {r.status !== "done" && r.status !== "error" && (
            <span className="run-item-cd mono">
              {Math.round(r.progress * 100)}%
            </span>
          )}
          <span
            className="run-item-id mono"
            title={t("sidebar.runId", { id: r.id })}
          >
            #{shortRunId(r.id)}
          </span>
          <span className="run-item-date">{formatTimestamp(r.created_at)}</span>
        </div>
      </div>
    );
  };

  const renderProgramGroup = (group: ProgramRunGroup<RunSummary>) => {
    const total = group.members.length;
    const done = group.members.filter((m) => TERMINAL.has(m.status)).length;
    const expanded = expandedPrograms.has(group.programId);
    return (
      <div className="program-group" key={group.programId}>
        <div
          className="program-header"
          role="button"
          tabIndex={0}
          onClick={() => onSelect(group.members[0].id)}
          onKeyDown={(e) => e.key === "Enter" && onSelect(group.members[0].id)}
        >
          <button
            className={`program-chevron${expanded ? " program-chevron-open" : ""}`}
            aria-expanded={expanded}
            onClick={(e) => {
              e.stopPropagation();
              toggleProgram(group.programId);
            }}
          >
            ▸
          </button>
          <span className="program-name" title={group.programName}>
            {group.programName}
          </span>
          <span className="program-progress mono">
            {t("sidebar.programDone", { done, total })}
          </span>
          <button
            className="program-action-btn"
            title={t("sidebar.cancelAll")}
            onClick={(e) => {
              e.stopPropagation();
              onCancelProgram(group.programId, group.programName, total - done);
            }}
          >
            {t("sidebar.cancelAll")}
          </button>
          <button
            className="program-action-btn program-action-btn-danger"
            title={t("sidebar.deleteAll")}
            onClick={(e) => {
              e.stopPropagation();
              onDeleteProgram(group.programId, group.programName, total);
            }}
          >
            {t("sidebar.deleteAll")}
          </button>
        </div>
        {expanded && (
          <div className="program-members">
            {group.members.map((m) => renderRunItem(m, true))}
          </div>
        )}
      </div>
    );
  };

  // Interleave program groups (at their first member's position, list order)
  // with plain single-run rows, preserving the backend's newest-first run list.
  const groups = groupProgramRuns(runs ?? []);
  const groupByProgram = new Map(groups.map((g) => [g.programId, g]));
  const placedPrograms = new Set<string>();
  const slots: (RunSummary | { group: ProgramRunGroup<RunSummary> })[] = [];
  for (const r of runs ?? []) {
    if (r.program_id != null) {
      if (placedPrograms.has(r.program_id)) continue;
      placedPrograms.add(r.program_id);
      const group = groupByProgram.get(r.program_id);
      if (group) slots.push({ group });
    } else {
      slots.push(r);
    }
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-head">
        <div className="brand">{t("common.brand")}</div>
        <button className="btn btn-primary btn-block" onClick={onNew}>
          {t("sidebar.newRun")}
        </button>
      </div>
      {compareIds.length > 0 && (
        <div className="compare-tray">
          <span className="compare-tray-label">
            {compareIds.length === 1
              ? t("sidebar.comparePick2")
              : t("sidebar.compareTwo")}
          </span>
          {compareIds.length === 2 && (
            <button className="btn btn-sm btn-primary" onClick={onOpenCompare}>
              {t("sidebar.compare")}
            </button>
          )}
          <button className="btn btn-sm btn-ghost" onClick={onClearCompare}>
            {t("sidebar.clear")}
          </button>
        </div>
      )}
      <div className="run-list">
        {runs === null && (
          <div className="run-list-empty">{t("sidebar.loadingRuns")}</div>
        )}
        {runs !== null && runs.length === 0 && (
          <div className="run-list-empty">
            {t("sidebar.noRuns")}
            <br />
            {t("sidebar.noRunsHint")}
          </div>
        )}
        {slots.map((slot) =>
          "group" in slot ? renderProgramGroup(slot.group) : renderRunItem(slot, false),
        )}
      </div>
      <StorageFooter refreshKey={refreshKey} onPruned={onPruned} />
    </aside>
  );
}
