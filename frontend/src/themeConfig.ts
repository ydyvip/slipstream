/**
 * Slipstream theme — single source of truth for the app's colour scheme.
 *
 * The `token` section follows the Ant Design v5 dark theme token model so the
 * values can double as a <ConfigProvider theme> if antd is ever adopted, but
 * today they are consumed directly: `src/theme.ts` injects the tokens into the
 * document root as CSS custom properties, and `styles.css` renders the whole UI
 * from those `--vars`. Edit colours here — never in the stylesheet.
 */
export const themeConfig = {
  token: {
    borderRadius: 8,
    borderRadiusLG: 16,
    borderRadiusSM: 4,
    borderRadiusXS: 2,
    colorSuccess: "#34c759",
    colorWarning: "#ff8d28",
    colorError: "#ff383c",
    fontSizeHeading1: 40,
    fontSizeHeading2: 32,
    colorPrimary: "#0052e7",
    colorPrimaryHover: "#256CDF",
    lineHeightHeading1: 1.2,
    lineHeightHeading2: 1.25,
    colorBorder: "rgba(255, 255, 255, 0.24)",
    colorBorderSecondary: "rgba(255, 255, 255, 0.12)",
    colorFill: "rgba(255, 255, 255, 0.24)",
    colorBgSpotlight: "rgba(0, 0, 0, 0.85)",
    colorPrimaryBg: "rgb(17, 24, 40)",
    colorBgLayout: "#303030",
    // --- text hierarchy (antd v5 dark defaults) ---
    colorText: "rgba(255, 255, 255, 0.88)",
    colorTextSecondary: "rgba(255, 255, 255, 0.65)",
    colorTextTertiary: "rgba(255, 255, 255, 0.45)",
    // --- app-specific surfaces built around the primary navy ---
    colorPanelHover: "#1C2745",
    colorBorderStrong: "rgba(255, 255, 255, 0.32)",
    colorReadout: "#ff8d28",
    colorGridLine: "rgba(255, 255, 255, 0.045)",
  },
  components: {
    Menu: {
      radiusItem: 8,
      colorItemTextSelected: "rgba(255, 255, 255, 1)",
      colorItemTextSelectedHorizontal: "rgba(255, 255, 255, 1)",
      colorItemBgSelected: "#0052E7",
      colorDangerItemText: "#ff4d4f",
    },
    Pagination: {
      borderRadiusLG: 16,
      colorPrimary: "rgba(255, 255, 255, 0.65)",
      colorPrimaryBorder: "rgba(255, 255, 255, 0.65)",
      colorPrimaryHover: "rgba(255, 255, 255, 0.85)",
    },
    Radio: {
      colorPrimary: "rgba(255, 255, 255, 0.45)",
      colorPrimaryHover: "rgba(255, 255, 255, 0.85)",
      colorPrimaryActive: "rgba(255, 255, 255, 0.25)",
    },
    Checkbox: {
      colorWhite: "#FFFFFF",
      colorPrimary: "rgba(255, 255, 255, 0.45)",
      colorText: "rgba(255, 255, 255, 0.85)",
      colorPrimaryHover: "rgba(255, 255, 255, 0.65)",
    },
    Form: {
      colorPrimary: "rgba(255, 255, 255, 0.85)",
      controlHeight: 36,
    },
    Slider: {
      colorPrimary: "rgba(255, 255, 255, 0.85)",
      colorPrimaryBorderHover: "rgba(255, 255, 255, 0.85)",
      colorBgContainer: "#141414",
      colorPrimaryBorder: "rgba(255, 255, 255, 0.65)",
      controlHeight: 36,
    },
    Switch: {
      colorPrimary: "rgba(255, 255, 255, 0.65)",
      colorPrimaryHover: "rgba(255, 255, 255, 0.85)",
      colorTextQuaternary: "rgba(255, 255, 255, 0.12)",
    },
    Cascader: {
      colorPrimary: "#0052E7",
      controlItemBgActive: "rgba(255,255,255,0.08)",
      controlHeight: 36,
    },
    Input: {
      colorPrimary: "rgba(255,255,255,0.85)",
      colorPrimaryHover: "rgba(255,255,255,0.45)",
      colorPrimaryActive: "rgba(255,255,255,0.85)",
      controlHeight: 36,
    },
    InputNumber: {
      colorPrimaryHover: "rgba(255,255,255,0.45)",
      colorPrimary: "rgba(255,255,255,0.45)",
      controlHeight: 36,
    },
    Mentions: {
      colorPrimaryHover: "rgba(255,255,255,0.45)",
      controlHeight: 36,
    },
    Select: {
      colorPrimary: "rgba(255,255,255,0.45)",
      colorPrimaryHover: "rgba(255,255,255,0.45)",
      controlItemBgActive: "rgba(255,255,255,0.08)",
      controlHeight: 36,
    },
    Upload: {
      colorPrimaryHover: "rgba(255,255,255,0.65)",
      colorPrimary: "rgba(255,255,255,0.45)",
      colorText: "rgba(255, 255, 255, 0.45)",
    },
    DatePicker: {
      colorPrimaryHover: "rgba(255,255,255,0.45)",
      colorPrimaryBorder: "rgba(255,255,255,0.45)",
      colorPrimary: "rgba(255,255,255,0.45)",
      controlHeight: 36,
    },
    TreeSelect: {
      controlItemBgActive: "rgba(255,255,255,0.08)",
    },
    Tabs: {
      colorPrimary: "rgba(255,255,255,1)",
      colorPrimaryActive: "rgba(255,255,255,0.85)",
      colorPrimaryBorder: "rgba(255,255,255,0.45)",
      colorPrimaryHover: "rgba(255,255,255,0.65)",
      colorText: "rgba(255, 255, 255, 0.45)",
    },
    Timeline: {
      colorPrimary: "rgba(255,255,255,0.65)",
    },
    Tree: {
      colorPrimary: "rgba(255,255,255,0.45)",
      colorPrimaryHover: "rgba(255,255,255,0.65)",
      colorPrimaryBorder: "rgba(255,255,255,0.45)",
    },
    Spin: {
      colorPrimary: "rgba(255,255,255,0.65)",
    },
    Calendar: {
      colorLink: "rgba(255,255,255,1)",
      colorPrimary: "rgba(255,255,255,1)",
      colorLinkActive: "rgba(255,255,255,0.45)",
      colorLinkHover: "rgba(255,255,255,0.45)",
      controlItemBgActive: "rgba(255,255,255,0.25)",
      colorPrimaryHover: "rgba(255,255,255,0.45)",
      colorSplit: "rgba(255, 255, 255, 0.12)",
      controlItemBgHover: "rgba(255, 255, 255, 0.08)",
    },
    Button: {
      colorBgContainer: "rgba(255,255,255,0.12)",
      colorLink: "#529aff",
      colorLinkHover: "#2776f5",
      colorPrimaryHover: "#256cdf",
      colorBorder: "rgba(255, 255, 255, 0.12)",
      controlHeight: 36,
    },
  },
};
