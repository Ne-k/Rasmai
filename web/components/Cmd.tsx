/** One command: what you type, and what comes back. */
export function Cmd({ name, args, children }: { name: string; args?: string; children: React.ReactNode }) {
  return (
    <div className="cmd">
      <div className="cmd-name">
        <code>{name}</code>
        {args ? <span className="cmd-args">{args}</span> : null}
      </div>
      <div className="cmd-what">{children}</div>
    </div>
  );
}
