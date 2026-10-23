// Record the canvas + the song to a video file in real time with MediaRecorder.

const CANDIDATES = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm", "video/mp4"];

export function supportedVideoType(): string | null {
  if (typeof MediaRecorder === "undefined") return null;
  return CANDIDATES.find((t) => MediaRecorder.isTypeSupported(t)) ?? null;
}

export function recordVideo(canvas: HTMLCanvasElement, audio: MediaStream, fps = 60): { stop(): Promise<Blob>; readonly mimeType: string } {
  const mimeType = supportedVideoType();
  if (!mimeType) throw new Error("this browser cannot record video");
  const video = canvas.captureStream(fps).getVideoTracks();
  const rec = new MediaRecorder(new MediaStream([...video, ...audio.getAudioTracks()]), { mimeType, videoBitsPerSecond: 8_000_000 });
  const chunks: Blob[] = [];
  rec.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
  const done = new Promise<Blob>((resolve, reject) => {
    rec.onstop = () => resolve(new Blob(chunks, { type: mimeType }));
    rec.onerror = () => reject(new Error("recording failed"));
  });
  rec.start(1000);   // a chunk a second so a long recording is not one giant buffer flush at the end
  return {
    mimeType,
    stop() {
      if (rec.state !== "inactive") rec.stop();
      for (const t of video) t.stop();   // the audio tracks belong to the SongClock; leave them
      return done;
    },
  };
}
