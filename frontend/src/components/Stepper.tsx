import type { RunStatus } from "../api";
import { useT } from "../i18n";

const STAGES: RunStatus[] = [
  "queued",
  "preparing",
  "meshing",
  "solving",
  "postprocessing",
  "done",
];

interface Props {
  status: RunStatus;
  progress: number;
  message: string;
}

/** Six-stage pipeline stepper + progress bar + current step message. */
export function Stepper({ status, progress, message }: Props) {
  const t = useT();
  const errored = status === "error";
  const currentIdx = errored
    ? -1
    : STAGES.findIndex((key) => key === status);

  return (
    <div className="stepper-block">
      <div className="stepper">
        {STAGES.map((key, i) => {
          let cls = "step";
          if (!errored) {
            if (i < currentIdx || status === "done") cls += " step-past";
            else if (i === currentIdx) cls += " step-current";
          }
          return (
            <div key={key} className={cls}>
              <span className="step-dot" />
              <span className="step-label">{t(`stepper.${key}`)}</span>
              {i < STAGES.length - 1 && <span className="step-line" />}
            </div>
          );
        })}
      </div>
      <div className="progress-track">
        <div
          className={`progress-fill${errored ? " progress-error" : ""}`}
          style={{ width: `${Math.round(Math.min(1, Math.max(0, progress)) * 100)}%` }}
        />
      </div>
      <div className="progress-message">
        <span className="mono">{Math.round(progress * 100)}%</span>
        <span>{errored ? t("stepper.failed") : message}</span>
      </div>
    </div>
  );
}
