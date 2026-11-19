"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, getJSON, postJSON } from "../api";
import { Empty, Label } from "../bits";
import { Facts } from "./bits";

type ControlApp = { id: string; name: string; by: string; userId: string; website: string; privacy: string; review: string; blocked: boolean; sites: string[]; stamp: string };
type ControlData = {
  maimai: { region: string; reachable: boolean; said: string };
  flags: { maintenance: boolean; deletions: boolean; disabled: string[] };
  commands: string[];
  mirrors: { handle: string; host: string }[];
  bots: string;
  grantKey: string;
  reviews: boolean;
  apps: ControlApp[];
};

const REFUSED: Record<string, string> = {
  bot_down: "The bot isn't running, so there was nothing to act on.",
  changed: "That app changed after this page was drawn, so nothing was done. Look at it again.",
  no_such_app: "That app was deleted since this page was drawn.",
  bad_commands: "One of those isn't a command that can be switched off.",
};
const RESTARTS: [action: string, label: string, warning: string][] = [
  ["restart_bot", "restart bot", "Press again to restart the bot. It is down for about a minute until Docker starts it again."],
  ["restart_site", "restart website", "Press again to restart the website. The whole site, this page included, is down for a few seconds."],
];

/** The bot's switches and its one-off actions. They were a command in Discord once; this is the only place now. The bot refuses all of it to
 *  everyone but the one account, so nothing here checks. `tick` changes each time the panel reads again, and this reads with it. */
export function Controls({ tick }: { tick: string }) {
  const [data, setData] = useState<ControlData | null>(null);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<{ words: string; bad: boolean } | null>(null);
  // the commands being chosen and the bots being typed; null while they are as saved
  const [off, setOff] = useState<string[] | null>(null);
  const [bots, setBots] = useState<string | null>(null);
  // a restart wants two presses: the first arms the button, the second does it
  const [armed, setArmed] = useState("");

  const load = useCallback(() => {
    getJSON<ControlData>("/api/me/admin/control")
      .then(setData)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    load();
  }, [load, tick]);

  const act = (action: string, more: Record<string, unknown> = {}) => {
    setBusy(true);
    setArmed("");
    postJSON<{ said: string }>("/api/me/admin/control", { action, ...more })
      .then((answer) => {
        setSaid({ words: answer.said, bad: false });
        if (action === "commands") setOff(null);
        if (action === "bots") setBots(null);
      })
      .catch((error: ApiError) => {
        // the site going down under this request is what restarting it looks like from here
        // an answer with its own word for what went wrong came from the site or the bot, so the site did not go down
        const restarting = action === "restart_site" && (error.status === 0 || (error.status >= 500 && !error.code));
        const told = typeof error.body.said === "string" ? error.body.said : "";
        setSaid(restarting ? { words: "The website is restarting. Reload this page in half a minute.", bad: false }
          : { words: REFUSED[error.code] ?? (told || "That didn't work. Try again in a moment."), bad: true });
      })
      .finally(() => {
        setBusy(false);
        load();
      });
  };

  if (!data) return null;
  const { flags, maimai } = data;
  // a command that has since been renamed or removed has no box to untick, and the bot refuses a list that names it
  const chosen = (off ?? flags.disabled).filter((name) => data.commands.includes(name));

  return (
    <>
      <section className="ledger">
        <div className="ledger-head">
          <Label>controls</Label>
          <span className="mono hint">
            maimai DX NET ({maimai.region}) {maimai.reachable ? "answering" : `not answering · ${maimai.said || "no answer"}`}
          </span>
        </div>
        {said && <p className={`hint ${said.bad ? "bad" : "ok"}`} role="status">{said.words}</p>}
        <div className="row-between admin-row">
          <span>
            maintenance <b>{flags.maintenance ? "on" : "off"}</b>
          </span>
          <span className="seg">
            <button type="button" disabled={busy} onClick={() => act("maintenance", { on: !flags.maintenance })}>
              {flags.maintenance ? "turn off" : "turn on"}
            </button>
          </span>
        </div>
        <div className="row-between admin-row">
          <span>
            expired-account deletion <b>{flags.deletions ? "running" : "held"}</b>
          </span>
          <span className="seg">
            <button type="button" disabled={busy} onClick={() => act("deletions", { on: !flags.deletions })}>
              {flags.deletions ? "hold" : "resume"}
            </button>
          </span>
        </div>
        <div className="row-between admin-row">
          <span>run now</span>
          <span className="seg">
            <button type="button" disabled={busy} onClick={() => act("news")}>force read news</button>
            <button type="button" disabled={busy} onClick={() => act("sweep")}>sweep expired accounts</button>
            <button type="button" disabled={busy} onClick={() => act("resync")}>resync commands</button>
          </span>
        </div>
        <div className="row-between admin-row">
          <span>restart</span>
          <span className="seg">
            {RESTARTS.map(([action, label, warning]) => (
              <button
                type="button"
                key={action}
                disabled={busy}
                className={armed === action ? "on" : undefined}
                onClick={() => {
                  if (armed === action) return act(action);
                  setArmed(action);
                  setSaid({ words: warning, bad: false });
                }}
              >
                {armed === action ? `confirm: ${label}` : label}
              </button>
            ))}
          </span>
        </div>
        <fieldset className="admin-checks">
          <legend>commands switched off</legend>
          {data.commands.map((name) => (
            <label key={name} className="mono">
              <input
                type="checkbox"
                checked={chosen.includes(name)}
                onChange={(event) => setOff(event.target.checked ? [...chosen, name] : chosen.filter((one) => one !== name))}
              />
              /{name}
            </label>
          ))}
        </fieldset>
        {off && (
          <div className="row-between admin-row">
            <span className="mono hint">not saved yet</span>
            <span className="seg">
              <button type="button" disabled={busy} onClick={() => setOff(null)}>reset</button>
              <button type="button" disabled={busy} onClick={() => act("commands", { disabled: off })}>save</button>
            </span>
          </div>
        )}
        <Facts rows={[["news mirrors", data.mirrors.map((m) => `${m.handle} → ${m.host}`).join(" · ") || "no feed read yet"]]} />
      </section>

      <section className="ledger">
        <div className="ledger-head">
          <Label>verified bots</Label>
          <span className="mono hint">one a line: Name https://its.site</span>
        </div>
        <textarea
          className="admin-text mono"
          aria-label="Verified bots"
          value={bots ?? data.bots}
          onChange={(event) => setBots(event.target.value)}
          rows={3}
          maxLength={2000}
          spellCheck={false}
        />
        {bots !== null && (
          <div className="row-between admin-row">
            <span className="mono hint">not saved yet</span>
            <span className="seg">
              <button type="button" disabled={busy} onClick={() => setBots(null)}>reset</button>
              <button type="button" disabled={busy} onClick={() => act("bots", { bots })}>save</button>
            </span>
          </div>
        )}
        <Facts rows={[["grant key", data.grantKey]]} />
      </section>

      <section className="ledger">
        <div className="ledger-head">
          <Label>applications · {data.apps.length}</Label>
          <span className="mono hint">blocking stops an app at once and deletes what it held</span>
        </div>
        {!data.apps.length ? (
          <Empty>No applications yet.</Empty>
        ) : (
          <div className="scroll">
            <table className="tbl compact keep">
              <thead>
                <tr>
                  <th>Application</th>
                  <th>Developer</th>
                  <th>Sends players to</th>
                  <th>State</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.apps.map((app) => {
                  const review = (verdict: string) => act("review", { id: app.id, verdict, stamp: app.stamp });
                  return (
                    <tr key={app.id}>
                      <td>
                        <span className="who-text">
                          <b>{app.name}</b>
                          <span className="mono dim">{app.id}</span>
                          {(app.website || app.privacy) && (
                            <span className="mono dim">
                              {app.website && <a href={app.website} target="_blank" rel="noopener noreferrer">website</a>}
                              {app.website && app.privacy && " · "}
                              {app.privacy && <a href={app.privacy} target="_blank" rel="noopener noreferrer">privacy</a>}
                            </span>
                          )}
                        </span>
                      </td>
                      <td>
                        <span className="who-text">
                          {app.by}
                          <span className="mono dim">{app.userId}</span>
                        </span>
                      </td>
                      <td className="mono">{app.sites.join(" · ") || "this machine only"}</td>
                      <td className={`mono ${app.blocked ? "bad" : "dim"}`}>{app.blocked ? "blocked" : data.reviews ? app.review : "live"}</td>
                      <td className="c-num">
                        <span className="seg">
                          {data.reviews && app.review === "pending" && (
                            <>
                              <button type="button" disabled={busy} onClick={() => review("verified")}>approve</button>
                              <button type="button" disabled={busy} onClick={() => review("rejected")}>reject</button>
                            </>
                          )}
                          {data.reviews && app.review === "verified" && (
                            <button type="button" disabled={busy} onClick={() => review("none")}>unverify</button>
                          )}
                          <button type="button" disabled={busy} onClick={() => act(app.blocked ? "unblock" : "block", { id: app.id })}>
                            {app.blocked ? "unblock" : "block"}
                          </button>
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
