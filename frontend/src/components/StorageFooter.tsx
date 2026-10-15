import { useCallback, useEffect, useState } from "react";
import { api, type StorageInfo } from "../api";
import { useT } from "../i18n";

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const u = ["KB", "MB", "GB", "TB"];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 ? 1 : 0)} ${u[i]}`;
}

/** Run-store disk usage + one-click cleanup of finished runs. */
export function StorageFooter({
  refreshKey,
  onPruned,
}: {
  refreshKey: number;
  onPruned: () => void;
}) {
  const t = useT();
  const [info, setInfo] = useState<StorageInfo | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setInfo(await api.getStorage());
    } catch {
      /* backend down — banner covers it */
    }
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load, refreshKey]);

  if (!info || info.run_count === 0) return null;

  const prune = async () => {
    if (
      !window.confirm(
        t("storage.pruneConfirm", { size: fmtBytes(info.reclaimable_bytes) }),
      )
    )
      return;
    setBusy(true);
    try {
      await api.pruneRuns();
      await load();
      onPruned();
    } finally {
      setBusy(false);
    }
  };

  const compact = async () => {
    if (
      !window.confirm(
        t("storage.compactConfirm", {
          size: fmtBytes(info.compactable_bytes),
        }),
      )
    )
      return;
    setBusy(true);
    try {
      await api.compactRuns();
      await load();
      onPruned();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="storage-footer">
      <span
        className="storage-usage mono"
        title={t("storage.runsOnDisk", { n: info.run_count })}
      >
        {fmtBytes(info.total_bytes)} ·{" "}
        {info.run_count === 1
          ? t("storage.runSingular")
          : t("storage.runPlural", { n: info.run_count })}
      </span>
      <div className="storage-actions">
        {info.compactable_bytes > 0 && (
          <button
            className="seg"
            disabled={busy}
            onClick={compact}
            title={t("storage.compactTitle")}
          >
            {busy
              ? "…"
              : t("storage.compact", { size: fmtBytes(info.compactable_bytes) })}
          </button>
        )}
        {info.reclaimable_bytes > 0 && (
          <button className="seg storage-clear" disabled={busy} onClick={prune}>
            {busy
              ? "…"
              : t("storage.clear", { size: fmtBytes(info.reclaimable_bytes) })}
          </button>
        )}
      </div>
    </div>
  );
}
