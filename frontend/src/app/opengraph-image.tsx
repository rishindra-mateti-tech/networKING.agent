import { ImageResponse } from "next/og";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

export const alt = "networKING.agent -- Relationship & Outreach Dashboard";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function Image() {
  const logoData = await readFile(join(process.cwd(), "public/apple-touch-icon.png"), "base64");
  const logoSrc = `data:image/png;base64,${logoData}`;

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "#12151a",
        }}
      >
        <img src={logoSrc} width={160} height={160} />
        <div style={{ display: "flex", marginTop: 36, fontSize: 72, fontWeight: 700 }}>
          <span style={{ color: "#ebe5d6" }}>networ</span>
          <span style={{ color: "#4d8565" }}>KING</span>
          <span style={{ color: "#ebe5d6" }}>.agent</span>
        </div>
        <div style={{ display: "flex", marginTop: 22, fontSize: 28, color: "#a1a1aa" }}>
          Intelligent, paced outreach queue and relationship funnel manager.
        </div>
      </div>
    ),
    { ...size }
  );
}
