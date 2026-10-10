import { ImageResponse } from "next/og";

export const dynamic = "force-static";

/** The picture in the whitepaper's embed, drawn at build time in the same style as the site's own card. */
export function GET() {
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
          rasmai whitepaper
        </div>
        <div style={{ display: "flex", fontSize: 84, fontWeight: 800, lineHeight: 1.05, marginTop: 18 }}>
          Predicting rating gains
        </div>
        <div style={{ display: "flex", fontSize: 84, fontWeight: 800, lineHeight: 1.05, color: "#ff5c9f" }}>
          in maimai DX.
        </div>
        <div style={{ display: "flex", fontSize: 30, color: "#c6c0d4", marginTop: 30, maxWidth: 960 }}>
          How Rasmai works out which charts will raise your rating, based on how you play.
        </div>
        <div style={{ display: "flex", marginTop: 46, fontSize: 26, color: "#45d6f2", letterSpacing: 2 }}>
          rasmai.lol/whitepaper.pdf · 19 pages
        </div>
      </div>
    ),
    { width: 1200, height: 630 },
  );
}
