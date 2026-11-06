import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowRight,
  Braces,
  Check,
  CircleAlert,
  Database,
  FlaskConical,
  History,
  LoaderCircle,
  Play,
  Plug,
  RefreshCw,
  Square,
  Terminal,
  X,
} from "lucide-react";
import "./styles.css";
import { ConnectionForm } from "./components/ConnectionForm";
import { DebuggingGuide } from "./components/DebuggingGuide";
import { RunDetails } from "./components/RunDetails";
import { RecordPanel } from "./components/RecordPanel";
import type { Config, Row, Run, Notice } from "./types";
import { api } from "./api";
import { Badge, time, date } from "./ui";

const active = (run?: Run | null) =>
  run?.status === "running" || run?.status === "cancelling";
const resumable = (run?: Run | null) =>
  ["failed", "cancelled", "interrupted"].includes(run?.status || "");
function App() {
  const [config, setConfig] = useState<Config>();
  const [saved, setSaved] = useState("");
  const [credential, setCredential] = useState("");
  const [hasCredential, setHasCredential] = useState(false);
  const [watermark, setWatermark] = useState<string | null>(null);
  const [scenarios, setScenarios] = useState<Record<string, string>>({});
  const [scenario, setScenario] = useState("healthy");
  const [tab, setTab] = useState("integration");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [pending, setPending] = useState("");
  const [preview, setPreview] = useState<Row[] | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [dataTab, setDataTab] = useState("preview");
  const [resetDialog, setResetDialog] = useState(false);
  const dirty = !!config && saved !== JSON.stringify(config);
  const busy = active(runs[0]);
  const selectedActive = active(run);
  async function refresh(windowOffset = offset) {
    const [settings, history, records] = await Promise.all([
      api<{
        config: Config;
        watermark: string | null;
        has_credential: boolean;
        scenarios: Record<string, string>;
      }>("/settings"),
      api<Run[]>("/runs"),
      api<{ items: Row[]; total: number }>(
        `/records?limit=10&offset=${windowOffset}`,
      ),
    ]);
    setWatermark(settings.watermark);
    setHasCredential(settings.has_credential);
    setScenarios(settings.scenarios);
    setRuns(history);
    setRows(records.items);
    setTotal(records.total);
    return { settings, history };
  }
  useEffect(() => {
    refresh(0)
      .then(({ settings, history }) => {
        setConfig(settings.config);
        setSaved(JSON.stringify(settings.config));
        if (history[0])
          api<Run>("/runs/" + history[0].id)
            .then(setRun)
            .catch(setNotice);
      })
      .catch(setNotice);
  }, []);
  useEffect(() => {
    if (!busy) return;
    const interval = setInterval(() => {
      refresh()
        .then(() => {
          if (run) return api<Run>("/runs/" + run.id).then(setRun);
        })
        .catch(setNotice);
    }, 650);
    return () => clearInterval(interval);
  }, [busy, run?.id, offset]);
  useEffect(() => {
    if (!resetDialog) return;
    const previous = document.activeElement as HTMLElement | null;
    document.querySelector<HTMLButtonElement>(".modal button")?.focus();
    const trap = (event: KeyboardEvent) => {
      if (event.key === "Escape") setResetDialog(false);
      if (event.key !== "Tab") return;
      const buttons = [
        ...document.querySelectorAll<HTMLButtonElement>(
          ".modal button:not(:disabled)",
        ),
      ];
      const first = buttons[0],
        last = buttons[buttons.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      }
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", trap);
    return () => {
      document.removeEventListener("keydown", trap);
      previous?.focus();
    };
  }, [resetDialog]);
  async function action(key: string, fn: () => Promise<void>) {
    setPending(key);
    setNotice(null);
    try {
      await fn();
    } catch (error) {
      setNotice(error as Notice);
    } finally {
      setPending("");
    }
  }
  function change<K extends keyof Config>(key: K, value: Config[K]) {
    setConfig((c) => c && { ...c, [key]: value });
    setPreview(null);
  }
  async function save() {
    await api("/settings", "PUT", { config, credential: credential || null });
    setSaved(JSON.stringify(config));
    setCredential("");
    setPreview(null);
    await refresh();
    setNotice({ message: "Connection settings saved.", good: true });
  }
  async function test() {
    setPreview(null);
    const result = await api<{ items: Row[]; message: string }>(
      "/preview",
      "POST",
      { scenario },
    );
    setPreview(result.items);
    setDataTab("preview");
    setNotice({ message: result.message, good: true });
  }
  async function start(full = false, resume = false, healthy = false) {
    const result = await api<{ id: string }>(
      resume ? `/runs/${run!.id}/resume` : "/runs",
      "POST",
      { scenario: healthy ? "healthy" : scenario, full },
    );
    setOffset(0);
    setDataTab("records");
    await refresh(0);
    setRun(await api<Run>("/runs/" + result.id));
  }
  async function selectRun(id: string) {
    setRun(await api<Run>("/runs/" + id));
    setTab("integration");
  }
  const controlsDisabled = !!pending || busy;
  const configDisabled = controlsDisabled || runs.length > 0;
  if (!config)
    return (
      <div className="boot">
        <Braces size={28} />
        <h1>Integration Toolkit</h1>
        {notice ? (
          <>
            <p role="alert">{notice.message}</p>
            <button onClick={() => location.reload()}>Retry connection</button>
            <p>Start the backend on port 8000.</p>
          </>
        ) : (
          <p>Connecting…</p>
        )}
      </div>
    );
  return (
    <>
      <header className="topbar">
        <div className="brand">
          <span className="brandmark">
            <Braces size={21} />
          </span>
          <div>
            <strong>Integration Toolkit</strong>
            <span>API integration & debugging</span>
          </div>
        </div>
      </header>
      <nav className="nav" aria-label="Main navigation">
        <div>
          {[
            ["integration", "Integration", Plug],
            ["history", "Run history", History],
            ["guide", "Debugging guide", Terminal],
          ].map(([key, label, Icon]) => (
            <button
              key={key as string}
              className={tab === key ? "selected" : ""}
              onClick={() => setTab(key as string)}
            >
              <Icon size={16} />
              {label as string}
              {key === "history" && runs.length > 0 && (
                <span className="count">{runs.length}</span>
              )}
            </button>
          ))}
        </div>
      </nav>
      <main>
        {notice && (
          <div
            className={"notice " + (notice.good ? "success" : "error")}
            role={notice.good ? "status" : "alert"}
          >
            {notice.good ? <Check size={17} /> : <CircleAlert size={17} />}
            <div>
              <strong>{notice.message}</strong>
              {notice.hint && <p>{notice.hint}</p>}
            </div>
            <button
              className="icon-button"
              aria-label="Dismiss notification"
              onClick={() => setNotice(null)}
            >
              <X size={16} />
            </button>
          </div>
        )}
        {tab === "integration" && (
          <>
            <div className="page-heading">
              <div>
                <h1>Integration workspace</h1>
                <p>Connect, validate and sync your data.</p>
              </div>
              <button
                className="quiet small"
                onClick={() => setResetDialog(true)}
                disabled={controlsDisabled}
              >
                Reset workspace
              </button>
            </div>
            <div className="workflow" aria-label="Integration workflow">
              {[
                "Configure API",
                "Test & preview",
                "Synchronize",
                "Inspect & export",
              ].map((step, i) => (
                <React.Fragment key={step}>
                  <span
                    className={
                      i === 0 ||
                      (i === 1 && preview) ||
                      (i === 2 && run) ||
                      (i === 3 && total)
                        ? "done"
                        : ""
                    }
                  >
                    <b>
                      {i === 0 || (i === 1 && preview) ? (
                        <Check size={12} />
                      ) : (
                        i + 1
                      )}
                    </b>
                    {step}
                  </span>
                  {i < 3 && <ArrowRight size={13} />}
                </React.Fragment>
              ))}
            </div>
            <div className="workspace">
              <ConnectionForm
                config={config}
                configDisabled={configDisabled}
                controlsDisabled={controlsDisabled}
                credential={credential}
                hasCredential={hasCredential}
                dirty={dirty}
                pending={pending}
                locked={runs.length > 0}
                change={change}
                setCredential={setCredential}
                onSave={() => action("save", save)}
              />
              <div className="main-column">
                <section className="panel">
                  <div className="panel-heading">
                    <h2>
                      <RefreshCw size={16} />
                      Synchronization
                    </h2>
                    <span className="eyebrow">02</span>
                  </div>
                  <div className="sync-body">
                    {config.source === "demo" && (
                      <div className="scenario-row">
                        <label htmlFor="scenario">
                          <FlaskConical size={15} />
                          Demo scenario
                        </label>
                        <select
                          id="scenario"
                          value={scenario}
                          disabled={controlsDisabled}
                          onChange={(e) => setScenario(e.target.value)}
                        >
                          {Object.entries(scenarios).map(([key, label]) => (
                            <option value={key} key={key}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}
                    <div className="sync-options">
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          checked={config.incremental}
                          disabled={configDisabled}
                          onChange={(e) =>
                            change("incremental", e.target.checked)
                          }
                        />
                        <span>
                          Incremental sync
                          <small>
                            {watermark
                              ? `Watermark: ${date(watermark)} · inclusive replay`
                              : "First run fetches all records"}
                          </small>
                        </span>
                      </label>
                      <span className="destination">
                        <Database size={15} />
                        <span>
                          Destination<strong>SQLite / orders</strong>
                        </span>
                      </span>
                    </div>
                    <div className="actions">
                      <button
                        className="secondary"
                        disabled={controlsDisabled || dirty}
                        onClick={() => action("preview", test)}
                      >
                        {pending === "preview" ? (
                          <LoaderCircle className="spin" size={15} />
                        ) : (
                          <Plug size={15} />
                        )}
                        Test & preview
                      </button>
                      <button
                        className="primary"
                        disabled={controlsDisabled || dirty || !preview}
                        onClick={() => action("run", () => start())}
                      >
                        <Play size={14} />
                        Run sync
                      </button>
                      {busy && (
                        <button
                          className="danger-outline"
                          onClick={() =>
                            action("stop", async () => {
                              await api(`/runs/${runs[0].id}/stop`, "POST");
                              await refresh();
                              setRun(await api<Run>("/runs/" + runs[0].id));
                            })
                          }
                          disabled={!!pending}
                        >
                          <Square size={13} />
                          Stop run
                        </button>
                      )}
                      {watermark && !busy && (
                        <button
                          className="quiet small"
                          disabled={controlsDisabled || dirty || !preview}
                          onClick={() => action("full", () => start(true))}
                        >
                          Replay all
                        </button>
                      )}
                    </div>
                    {!preview && !busy && (
                      <p className="help action-help">
                        {dirty
                          ? "Save your changes before testing."
                          : "Test the connection to validate the first page before running."}
                      </p>
                    )}
                  </div>
                </section>
                {run && (
                  <RunDetails
                    run={run}
                    scenarios={scenarios}
                    selectedActive={selectedActive}
                    canResume={resumable(run) && run.id === runs[0]?.id}
                    controlsDisabled={controlsDisabled}
                    demo={config.source === "demo"}
                    onResume={() => action("resume", () => start(false, true))}
                    onFixResume={() =>
                      action("recover", () => start(false, true, true))
                    }
                  />
                )}
                <RecordPanel
                  dataTab={dataTab}
                  setDataTab={setDataTab}
                  preview={preview}
                  rows={rows}
                  total={total}
                  offset={offset}
                  onPage={(next) =>
                    action("page", async () => {
                      setOffset(next);
                      await refresh(next);
                    })
                  }
                />
                {config.source === "demo" && total > 0 && !busy && (
                  <div className="demo-tip">
                    <FlaskConical size={16} />
                    <p>
                      <strong>Try an incremental update.</strong> Change one
                      source order and add another, then run again.
                    </p>
                    <button
                      className="quiet small"
                      disabled={!!pending}
                      onClick={() =>
                        action("revision", async () => {
                          const result = await api<Notice>(
                            "/demo/revision",
                            "POST",
                          );
                          setNotice({ ...result, good: true });
                        })
                      }
                    >
                      Update demo data
                      <ArrowRight size={13} />
                    </button>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
        {tab === "history" && (
          <>
            <div className="page-heading">
              <div>
                <h1>Run history</h1>
                <p>Every attempt, checkpoint and recovery.</p>
              </div>
              <button
                className="secondary small"
                onClick={() =>
                  action("refresh", async () => {
                    await refresh();
                  })
                }
              >
                <RefreshCw size={14} />
                Refresh
              </button>
            </div>
            <section className="panel">
              {runs.length ? (
                <div className="table-scroll">
                  <table className="history-table">
                    <thead>
                      <tr>
                        <th>Run / started</th>
                        <th>Scenario</th>
                        <th>Status</th>
                        <th>Pages</th>
                        <th>Inserted</th>
                        <th>Updated</th>
                        <th>Retries</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {runs.map((r) => (
                        <tr key={r.id}>
                          <td>
                            <code>{r.id.slice(0, 8)}</code>
                            <small>
                              {date(r.started)} · {time(r.started)}
                            </small>
                          </td>
                          <td>{scenarios[r.scenario]}</td>
                          <td>
                            <Badge status={r.status} />
                          </td>
                          <td>{r.pages}</td>
                          <td>{r.inserted}</td>
                          <td>{r.updated}</td>
                          <td>{r.retries}</td>
                          <td>
                            <button
                              className="quiet small"
                              onClick={() =>
                                action("select", () => selectRun(r.id))
                              }
                            >
                              Inspect
                              <ArrowRight size={13} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty">
                  <History size={26} />
                  <h3>No runs yet</h3>
                  <p>Your synchronization attempts will appear here.</p>
                </div>
              )}
            </section>
          </>
        )}
        {tab === "guide" && <DebuggingGuide />}
      </main>
      {resetDialog && (
        <div className="modal-backdrop" onClick={() => setResetDialog(false)}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="reset-title"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === "Escape") setResetDialog(false);
            }}
          >
            <CircleAlert size={24} />
            <h2 id="reset-title">Reset this workspace?</h2>
            <p>
              This removes synchronized records, run history and the watermark.
              Connection settings stay saved. Export any records you need first.
            </p>
            <div className="actions">
              <button
                className="secondary"
                onClick={() => setResetDialog(false)}
              >
                Keep workspace
              </button>
              <button
                className="danger"
                disabled={!!pending}
                onClick={() =>
                  action("reset", async () => {
                    await api("/reset", "POST");
                    setRun(null);
                    setPreview(null);
                    setOffset(0);
                    await refresh(0);
                    setResetDialog(false);
                    setNotice({
                      message:
                        "Workspace reset. You can edit connection settings.",
                      good: true,
                    });
                  })
                }
              >
                Reset workspace
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
