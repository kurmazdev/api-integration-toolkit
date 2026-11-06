import { FlaskConical } from "lucide-react";
export function DebuggingGuide() {
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Debugging guide</h1>
          <p>Real HTTP failures. Visible recovery.</p>
        </div>
        <span className="pill">
          <FlaskConical size={14} />
          Local demo API
        </span>
      </div>
      <div className="guide-grid">
        <section className="panel guide-section">
          <h2>Reproduce a broken integration</h2>
          <ol>
            <li>Test & preview the healthy demo connection.</li>
            <li>
              Select <strong>Repeated cursor</strong> and run a sync. Use
              <strong> Replay all</strong> if a successful watermark already exists.
            </li>
            <li>
              Page 1 commits. Page 2 fails with <code>pagination</code>.
            </li>
            <li>
              Inspect the execution log, then choose{" "}
              <strong>Fix demo & resume</strong>.
            </li>
            <li>
              The run continues at page 2, finishing with 23 unique orders.
            </li>
          </ol>
          <div className="case-note">
            <strong>The root cause</strong>
            <p>
              The upstream returns the current cursor as its next cursor. A
              naïve client loops forever. The connector checks cursor progress
              and repeated page fingerprints before committing.
            </p>
            <p>
              The demo fix switches the upstream to correct pagination. The
              checkpoint stays unchanged until the corrected page commits.
            </p>
          </div>
        </section>
        <section className="panel guide-section">
          <h2>Failure behavior</h2>
          <dl>
            <dt>500 / 429 / timeout</dt>
            <dd>
              Bounded retries with backoff. Retry-After is honored; long waits
              stop safely for later resumption.
            </dd>
            <dt>Expired credentials</dt>
            <dd>
              Stops immediately. Refresh the session credential, then resume.
            </dd>
            <dt>Malformed JSON / incomplete record</dt>
            <dd>
              Rejects the whole page. Previously committed pages remain
              available.
            </dd>
            <dt>Duplicates / replay</dt>
            <dd>
              Stable source IDs upsert into SQLite. Unchanged records are
              counted separately.
            </dd>
            <dt>Interrupted run</dt>
            <dd>
              Select Slow pages, then stop. Resume at the last checkpoint. A
              process restart marks abandoned runs interrupted.
            </dd>
          </dl>
        </section>
        <section className="panel guide-section wide">
          <h2>Connector contract & safety</h2>
          <div className="guide-columns">
            <div>
              <h3>Predictable REST contract</h3>
              <p>
                GET with <code>limit</code> and <code>cursor</code>,{" "}
                <code>page</code> or <code>offset</code>. Map an items array and
                next cursor (null at the end) or a boolean has_more. Incremental
                APIs must accept inclusive <code>updated_since</code> and return
                stable, complete pages.
              </p>
            </div>
            <div>
              <h3>A local, single-user workbench</h3>
              <p>
                Custom destinations require public HTTPS. DNS addresses are
                checked and pinned; redirects and environment proxies are
                disabled. Only mapped order fields are stored and exported.
                Credentials and raw response bodies never enter the database or
                execution log.
              </p>
            </div>
            <div>
              <h3>Explicit partial success</h3>
              <p>
                Each page and its checkpoint commit together. Failure keeps
                those records; the watermark advances only on full completion.
                Records are upserted, never deleted. Export includes committed
                records, including partial runs.
              </p>
            </div>
          </div>
        </section>
      </div>
    </>
  );
}
