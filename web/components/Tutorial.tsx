/** The linking video: an International account linked in Firefox, start to finish. Loaded only when played. */
export function Tutorial({ label, note }: { label: string; note: string }) {
  return (
    <figure className="tutorial">
      <video src="/tutorial/firefox.mp4" poster="/tutorial/firefox.jpg" width={1280} height={720} controls playsInline muted preload="none" aria-label={label} />
      <figcaption>{note}</figcaption>
    </figure>
  );
}
