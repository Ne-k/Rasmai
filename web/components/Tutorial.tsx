/** The linking video: an International account linked in Firefox, start to finish. Loaded only when played. */
export function Tutorial({ label }: { label: string }) {
  return (
    <figure className="tutorial">
      <video src="/tutorial/firefox.mp4?v=2" poster="/tutorial/firefox.jpg?v=2" width={1280} height={720} controls playsInline muted preload="none" aria-label={label} />
    </figure>
  );
}
