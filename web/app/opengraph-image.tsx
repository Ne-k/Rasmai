import { ImageResponse } from "next/og";

export const alt = "Rasmai · maimai DX rating bot for Discord";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/** The card that shows when a Rasmai link is pasted anywhere. Drawn at build time from the brand. */
export default async function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "0 92px",
          background: "#14121c",
          color: "#f4f0e6",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", fontSize: 26, letterSpacing: 6, color: "#918ba6", textTransform: "uppercase" }}>
          a discord bot for maimai dx
        </div>
        <div style={{ display: "flex", fontSize: 96, fontWeight: 800, lineHeight: 1.05, marginTop: 18 }}>
          See which charts
        </div>
        <div style={{ display: "flex", fontSize: 96, fontWeight: 800, lineHeight: 1.05, color: "#ff5c9f" }}>
          to play next.
        </div>
        <div style={{ display: "flex", fontSize: 30, color: "#c6c0d4", marginTop: 30, maxWidth: 900 }}>
          Rasmai looks at your scores and tells you which charts to play to raise your rating.
        </div>
        <div style={{ display: "flex", marginTop: 46, fontSize: 26, color: "#45d6f2", letterSpacing: 2 }}>
          rasmai.lol
        </div>
      </div>
    ),
    size,
  );
}
