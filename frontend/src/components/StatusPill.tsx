import type { RunStatus } from "../api";
import { useT } from "../i18n";

export function StatusPill({ status }: { status: RunStatus }) {
  const t = useT();
  return (
    <span className={`pill pill-${status}`}>{t(`detail.status.${status}`)}</span>
  );
}

export const ACTIVE_STATUSES: RunStatus[] = [
  "queued",
  "preparing",
  "meshing",
  "solving",
  "postprocessing",
];

export function isTerminal(status: RunStatus): boolean {
  return status === "done" || status === "error" || status === "cancelled";
}
