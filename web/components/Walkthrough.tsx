"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

type Platform = "desktop" | "ios";

// bump when a recording is replaced: browsers hold on to a video far longer than a page
const CUT = 2;

const CLIPS: Record<Platform, { label: "desktop" | "ios"; src: string; poster: string; note: "desktopNote" | "iosNote"; chrome: string; w: number; h: number }> = {
  desktop: {
    label: "desktop",
    src: "/walkthrough/desktop.mp4",
    poster: "/walkthrough/desktop.jpg",
    note: "desktopNote",
    chrome: "maimaidx-eng.com",
    w: 1280,
    h: 720,
  },
  ios: {
    label: "ios",
    src: "/walkthrough/ios-safari.mp4",
    poster: "/walkthrough/ios-safari.jpg",
    note: "iosNote",
    chrome: "maimaidx-eng.com",
    w: 560,
    h: 1214,
  },
};

/** The linking walkthrough as a screen recording, framed like the device it was taken on. */
export function Walkthrough() {
  const t = useTranslations("walkthrough");
  const [platform, setPlatform] = useState<Platform>("desktop");
  const clip = CLIPS[platform];
  const video = (
    <video
      key={clip.src}
      src={`${clip.src}?v=${CUT}`}
      poster={`${clip.poster}?v=${CUT}`}
      width={clip.w}
      height={clip.h}
      controls
      playsInline
      muted
      loop
      preload="none"
      aria-label={t("videoLabel", { device: t(clip.label) })}
    />
  );
  return (
    <div className="walkthrough">
      <div className="walk-tabs" role="tablist" aria-label={t("tabs")}>
        {(Object.keys(CLIPS) as Platform[]).map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={platform === key}
            className={platform === key ? "on" : ""}
            onClick={() => setPlatform(key)}
          >
            {t(CLIPS[key].label)}
          </button>
        ))}
      </div>

      <div className="walk-stage">
        {platform === "desktop" ? (
          <div className="walk-browser">
            <div className="walk-chrome" aria-hidden="true">
              <span className="walk-dots">
                <i />
                <i />
                <i />
              </span>
              <span className="walk-url">{clip.chrome}</span>
            </div>
            {video}
          </div>
        ) : (
          <div className="walk-phone">
            <span className="walk-notch" aria-hidden="true" />
            {video}
          </div>
        )}
        <p className="walk-note">
          <b>{t(clip.label)}</b>
          {t(clip.note)}
        </p>
      </div>
    </div>
  );
}
