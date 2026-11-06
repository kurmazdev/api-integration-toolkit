import {
  Plug,
  FlaskConical,
  Settings2,
  ChevronDown,
  ArrowRight,
  Check,
  LoaderCircle,
} from "lucide-react";
import type { Config } from "../types";
type Props = {
  config: Config;
  configDisabled: boolean;
  controlsDisabled: boolean;
  credential: string;
  hasCredential: boolean;
  dirty: boolean;
  pending: string;
  locked: boolean;
  change: <K extends keyof Config>(key: K, value: Config[K]) => void;
  setCredential: (value: string) => void;
  onSave: () => void;
};
export function ConnectionForm({
  config,
  configDisabled,
  controlsDisabled,
  credential,
  hasCredential,
  dirty,
  pending,
  locked,
  change,
  setCredential,
  onSave,
}: Props) {
  return (
    <aside className="connection panel">
      <div className="panel-heading">
        <h2>
          <Plug size={16} />
          Connection
        </h2>
        <span className="eyebrow">01</span>
      </div>
      <div className="form-body">
        <label>
          Integration name
          <input
            value={config.name}
            maxLength={80}
            disabled={configDisabled}
            onChange={(e) => change("name", e.target.value)}
          />
        </label>
        <label>
          API source
          <select
            value={config.source}
            disabled={configDisabled}
            onChange={(e) =>
              change("source", e.target.value as Config["source"])
            }
          >
            <option value="demo">Local demo · Orders API</option>
            <option value="custom">Custom REST API</option>
          </select>
        </label>
        {config.source === "demo" ? (
          <div className="endpoint">
            <div>
              <FlaskConical size={14} />
              <strong>Demo orders</strong>
              <span className="method">GET</span>
            </div>
            <code>127.0.0.1:8001/orders</code>
            <p>
              No credentials needed. A separate local API with controlled
              failures.
            </p>
          </div>
        ) : (
          <>
            <label>
              Endpoint URL
              <input
                type="url"
                placeholder="https://api.example.com/orders"
                value={config.url}
                disabled={configDisabled}
                onChange={(e) => change("url", e.target.value)}
              />
              <small>Public HTTPS · no query string or redirects</small>
            </label>
            <label>
              Authentication
              <select
                value={config.auth}
                disabled={configDisabled}
                onChange={(e) => change("auth", e.target.value)}
              >
                <option value="none">No authentication</option>
                <option value="bearer">Bearer token</option>
                <option value="api_key">API key · X-API-Key</option>
              </select>
            </label>
            {config.auth !== "none" && (
              <label>
                Credential
                <input
                  type="password"
                  autoComplete="off"
                  value={credential}
                  onChange={(e) => setCredential(e.target.value)}
                  placeholder={
                    hasCredential
                      ? "Credential set · enter to replace"
                      : "Enter token"
                  }
                  disabled={controlsDisabled}
                />
                <small>Session only. Re-enter after a restart.</small>
              </label>
            )}
          </>
        )}
        <div className="form-row">
          <label>
            Pagination
            <select
              value={config.pagination}
              disabled={configDisabled}
              onChange={(e) => change("pagination", e.target.value)}
            >
              <option value="cursor">Cursor</option>
              <option value="page">Page number</option>
              <option value="offset">Offset</option>
            </select>
          </label>
          <label>
            Page size
            <input
              type="number"
              min={1}
              max={100}
              value={config.page_size}
              disabled={configDisabled}
              onChange={(e) => change("page_size", +e.target.value)}
            />
          </label>
        </div>
        <details>
          <summary>
            <Settings2 size={14} />
            Advanced settings
            <ChevronDown size={14} />
          </summary>
          <div className="advanced">
            <div className="form-row">
              <label>
                Timeout (seconds)
                <input
                  type="number"
                  min="0.1"
                  max="30"
                  step="0.1"
                  value={config.timeout}
                  disabled={configDisabled}
                  onChange={(e) => change("timeout", +e.target.value)}
                />
              </label>
              <label>
                Retries
                <input
                  type="number"
                  min="0"
                  max="5"
                  value={config.retries}
                  disabled={configDisabled}
                  onChange={(e) => change("retries", +e.target.value)}
                />
              </label>
            </div>
            <label>
              Maximum pages
              <input
                type="number"
                min="1"
                max="1000"
                value={config.max_pages}
                disabled={configDisabled}
                onChange={(e) => change("max_pages", +e.target.value)}
              />
            </label>
            <label>
              Items path
              <input
                value={config.items_path}
                disabled={configDisabled}
                onChange={(e) => change("items_path", e.target.value)}
              />
            </label>
            <label>
              {config.pagination === "cursor"
                ? "Next cursor path"
                : "Has more path"}
              <input
                value={
                  config.pagination === "cursor"
                    ? config.cursor_path
                    : config.more_path
                }
                disabled={configDisabled}
                onChange={(e) =>
                  change(
                    config.pagination === "cursor"
                      ? "cursor_path"
                      : "more_path",
                    e.target.value,
                  )
                }
              />
            </label>
            <fieldset>
              <legend>
                Field mapping <span>source → stored field</span>
              </legend>
              {Object.entries(config.mapping).map(([target, source]) => (
                <div className="mapping" key={target}>
                  <input
                    aria-label={`Source field for ${target}`}
                    value={source}
                    disabled={configDisabled}
                    onChange={(e) =>
                      change("mapping", {
                        ...config.mapping,
                        [target]: e.target.value,
                      })
                    }
                  />
                  <ArrowRight size={12} />
                  <code>{target}</code>
                </div>
              ))}
            </fieldset>
            <p className="help">
              Text is trimmed, status lowercased, amounts rounded and timestamps
              converted to UTC.
            </p>
          </div>
        </details>
        <button
          className="secondary full"
          onClick={onSave}
          disabled={controlsDisabled || (!dirty && !credential)}
        >
          {pending === "save" ? (
            <LoaderCircle className="spin" size={15} />
          ) : (
            <Check size={15} />
          )}
          Save settings
          {dirty && <span className="unsaved">Unsaved</span>}
        </button>
        {locked && (
          <p className="help">
            Settings are locked to this dataset. Reset to change the
            integration.
          </p>
        )}
      </div>
    </aside>
  );
}
