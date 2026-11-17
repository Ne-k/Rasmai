/** A linking video, an International account linked start to finish: by hand in Firefox, or with the Aime sign-in helper
 *  extension. Loaded only when played. */
export function Tutorial({ label, clip = "firefox" }: { label: string; clip?: "firefox" | "extension" }) {
  // the number is the copy's: a new cut of a video goes up under a new address, so the old one is not served from cache
  const copy = clip === "firefox" ? 2 : 1;
  return (
    <figure className="tutorial">
      <video src={`/tutorial/${clip}.mp4?v=${copy}`} poster={`/tutorial/${clip}.jpg?v=${copy}`} width={1280} height={720} controls playsInline muted preload="none" aria-label={label} />
    </figure>
  );
}
