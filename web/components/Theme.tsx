"use client";

export const THEME_KEY = "rasmai-theme";
export const THEME_COLORS = { light: "#fbf6ec", dark: "#14121c" };

/** Runs before paint: applies the saved theme so the page never flashes the other one, and writes the browser-chrome
 *  colour to match. Light unless the reader chose dark; the device setting is not consulted. */
export const THEME_BOOT = `(function(){var d=false;try{d=localStorage.getItem(${JSON.stringify(THEME_KEY)})==="dark";}catch(e){}if(d)document.documentElement.setAttribute("data-theme","dark");var m=document.querySelector('meta[name="theme-color"]');if(!m){m=document.createElement("meta");m.setAttribute("name","theme-color");document.head.appendChild(m);}m.setAttribute("content",d?${JSON.stringify(THEME_COLORS.dark)}:${JSON.stringify(THEME_COLORS.light)});})();`;

export function currentTheme(): "light" | "dark" {
  return typeof document !== "undefined" && document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function paintChrome(theme: "light" | "dark") {
  let meta = document.querySelector('meta[name="theme-color"]');
  if (!meta) {
    meta = document.createElement("meta");
    meta.setAttribute("name", "theme-color");
    document.head.appendChild(meta);
  }
  meta.setAttribute("content", THEME_COLORS[theme]);
}

export function applyTheme(theme: "light" | "dark") {
  const root = document.documentElement;
  if (theme === "dark") root.setAttribute("data-theme", "dark");
  else root.removeAttribute("data-theme");
  paintChrome(theme);
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* private mode: the choice lasts for this page only */
  }
}

/** One button in the masthead: moon in the light theme, sun in the dark one. The stylesheet picks which glyph shows. */
export function ThemeToggle() {
  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label="Switch between light and dark"
      title="Light / dark"
      onClick={() => applyTheme(currentTheme() === "dark" ? "light" : "dark")}
    >
      <svg className="moon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
      </svg>
      <svg className="sun" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="4.2" />
        <path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.5 1.5M17.2 17.2l1.5 1.5M5.3 18.7l1.5-1.5M17.2 6.8l1.5-1.5" />
      </svg>
    </button>
  );
}
