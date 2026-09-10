type RingProps = { lit?: number; size?: number; done?: boolean; chase?: boolean };

export function Ring({ lit = 0, size = 120, done = false, chase = false }: RingProps) {
  const r = size / 2;
  const ringR = r * 0.78;
  const btnR = size * 0.075;
  const rimEdge = Math.max(1.4, size * 0.028);
  const rim = Math.max(0.8, rimEdge * 0.6);
  const btnStroke = Math.max(0.7, size * 0.012);
  const buttons = Array.from({ length: 8 }, (_, i) => {
    // Cabinet layout: button 1 upper-right, button 8 upper-left, no button at 12 o'clock.
    const angle = ((-67.5 + i * 45) * Math.PI) / 180;
    const cx = r + ringR * Math.cos(angle);
    const cy = r + ringR * Math.sin(angle);
    const cls = done ? "btn done" : i < lit ? (i < lit - 1 ? "btn lit" : "btn lit active") : "btn";
    const style = chase ? { strokeWidth: btnStroke, animationDelay: `${i * 0.5}s` } : { strokeWidth: btnStroke };
    return <circle key={i} className={cls} cx={cx.toFixed(1)} cy={cy.toFixed(1)} r={btnR.toFixed(1)} style={style} />;
  });
  return (
    <svg className={chase ? "ring chase" : "ring"} viewBox={`0 0 ${size} ${size}`} width={size} height={size} role="img" aria-label="maimai button ring">
      <circle className="rim-edge" cx={r} cy={r} r={ringR.toFixed(1)} style={{ strokeWidth: rimEdge }} />
      <circle className="rim" cx={r} cy={r} r={ringR.toFixed(1)} style={{ strokeWidth: rim }} />
      <circle className="screen" cx={r} cy={r} r={(r * 0.46).toFixed(1)} />
      {buttons}
    </svg>
  );
}
