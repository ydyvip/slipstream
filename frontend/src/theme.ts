import { themeConfig } from "./themeConfig";

/**
 * Applies the ThemeConfig palette to the document root as CSS custom
 * properties. styles.css renders the whole UI from these --vars, so
 * themeConfig.ts is the single source of truth for the colour scheme —
 * edit colours there, never in the stylesheet.
 *
 * This module runs before React mounts (plain side-effect import in
 * main.tsx), so no painted frame ever sees an unstyled :root.
 */

/** Maps the stylesheet's --vars to their ThemeConfig token. */
const CSS_VAR_MAP: Record<string, keyof typeof themeConfig.token> = {
  "--bg": "colorBgLayout",
  "--panel": "colorPrimaryBg",
  "--panel-2": "colorPanelHover",
  "--border": "colorBorder",
  "--border-strong": "colorBorderStrong",
  "--text": "colorText",
  "--text-2": "colorTextSecondary",
  "--muted": "colorTextTertiary",
  "--accent": "colorPrimary",
  "--accent-dim": "colorPrimaryHover",
  "--readout": "colorReadout",
  "--good": "colorSuccess",
  "--warn": "colorWarning",
  "--danger": "colorError",
  "--grid": "colorGridLine",
  "--axis": "colorBorderSecondary",
};

const root = document.documentElement;
for (const [prop, token] of Object.entries(CSS_VAR_MAP)) {
  // CSS custom properties are always strings; coerce the numeric tokens too.
  root.style.setProperty(prop, String(themeConfig.token[token]));
}
