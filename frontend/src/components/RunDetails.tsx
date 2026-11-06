import {
  Activity,
  LoaderCircle,
  CircleAlert,
  Terminal,
  ChevronDown,
} from "lucide-react";
import type { Run } from "../types";
import { Badge, time } from "../ui";
type Props = {
  run: Run;
  scenarios: Record<string, string>;
  selectedActive: boolean;
  canResume: boolean;
  controlsDisabled: boolean;
  demo: boolean;
  onResume: () => void;
  onFixResume: () => void;
};
export function RunDetails({
  run,
  scenarios,
  selectedActive,
  canResume,
  controlsDisabled,
  demo,
  onResume,
  onFixResume,
}: Props) {
  return (
    <section className="panel run-panel" aria-label="Run details">
      <div className="panel-heading">
        <h2>
          {selectedActive ? (
            <LoaderCircle size={16} className="spin" />
          ) : (
            <Activity size={16} />
          )}
          Run <code>{run.id.slice(0, 8)}</code>
        </h2>
        <Badge status={run.status} />
      </div>
      <div className="run-body">
        <div className="run-meta">
          <span>
            {scenarios[run.scenario]} · {time(run.started)}
          </span>
          <span>{run.since ? "Incremental" : "Full synchronization"}</span>
        </div>
        <div className="run-stats">
          {[
            [run.pages, "Pages"],
            [run.inserted, "Inserted"],
            [run.updated, "Updated"],
            [run.unchanged, "Unchanged"],
            [run.retries, "Retries"],
          ].map(([value, label]) => (
            <div key={label}>
              <strong>{value}</strong>
              <span>{label}</span>
            </div>
          ))}
        </div>
        {canResume && (
          <div className="recovery">
            <div>
              <CircleAlert size={16} />
              <span>
                Committed pages are safe. Resume at the next uncommitted page.
              </span>
            </div>
            <div>
              <button
                className="secondary small"
                disabled={controlsDisabled}
                onClick={onResume}
              >
                Resume run
              </button>
              {demo && run.scenario !== "healthy" && (
                <button
                  className="primary small"
                  disabled={controlsDisabled}
                  onClick={onFixResume}
                >
                  Fix demo & resume
                </button>
              )}
            </div>
          </div>
        )}
        <details className="events" open={run.status !== "completed"}>
          <summary>
            <Terminal size={14} />
            Execution log
            <span>
              {run.events?.length || 0} events
              <ChevronDown size={13} />
            </span>
          </summary>
          <div className="event-list" role="log" aria-label="Execution log">
            {run.events?.map((event) => (
              <div className={"event " + event.level} key={event.id}>
                <time>{time(event.time)}</time>
                <div>
                  <span className="event-code">{event.code}</span>
                  <p>{event.message}</p>
                  {event.hint && <p className="event-hint">{event.hint}</p>}
                </div>
              </div>
            ))}
          </div>
        </details>
      </div>
    </section>
  );
}
