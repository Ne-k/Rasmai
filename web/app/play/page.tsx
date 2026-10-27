import { notFound } from "next/navigation";

// offline for now: the player (components/play, ./play.css) stays in the build and comes back with `return <Play />` and its metadata from git
export default function PlayPage() {
  notFound();
}
