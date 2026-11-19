/** A linking video, an International account linked start to finish: by hand in Firefox, by pasting a link into the Aime
 *  sign-in helper extension, or by approving in its window. Loaded only when played. */
export function Tutorial({ label, clip = "firefox" }: { label: string; clip?: "firefox" | "extension" | "approve" }) {
  // the number is the copy's: a new cut of a video goes up under a new address, so the old one is not served from cache
  const copy = 2;
  return (
    <figure className="tutorial">
      <video src={`/tutorial/${clip}.mp4?v=${copy}`} poster={`/tutorial/${clip}.jpg?v=${copy}`} width={1280} height={720} controls playsInline muted preload="none" aria-label={label} />
    </figure>
  );
}
