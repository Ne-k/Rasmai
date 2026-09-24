"use client";

import { useEffect, useState } from "react";
import { getJSON, type Overview } from "../api";
import { Frame } from "../Frame";
import { AdminPanel } from "./Panel";

export { AdminPanel };

export function Admin() {
  const [me, setMe] = useState<Overview["user"] | undefined>();
  useEffect(() => {
    getJSON<Overview>("/api/me").then((d) => setMe(d.user)).catch(() => undefined);
  }, []);
  return (
    <Frame user={me}>
      <AdminPanel />
    </Frame>
  );
}
