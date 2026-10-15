import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { en } from "./en";
import { zh } from "./zh";

export type Lang = "zh" | "en";
export type Messages = Record<string, string>;

const DICTS: Record<Lang, Messages> = { zh, en };
const STORAGE_KEY = "ui.lang";
const DEFAULT_LANG: Lang = "zh";

interface I18nValue {
  lang: Lang;
  /** Look up a namespaced key, e.g. t("sidebar.newRun"). Falls back to English. */
  t: (key: string, vars?: Record<string, string | number>) => string;
  setLang: (l: Lang) => void;
}

const I18nContext = createContext<I18nValue | null>(null);

function isLang(v: unknown): v is Lang {
  return v === "zh" || v === "en";
}

function readInitialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (isLang(saved)) return saved;
  } catch {
    /* storage unavailable (private mode, etc.) */
  }
  return DEFAULT_LANG;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readInitialLang);

  const setLang = (l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* ignore */
    }
  };

  // Keep <html lang> and the document title in sync with the active language.
  useEffect(() => {
    document.documentElement.lang = lang;
    const title = DICTS[lang]["common.title"] ?? DICTS.en["common.title"];
    if (title) document.title = title;
  }, [lang]);

  const value = useMemo<I18nValue>(
    () => ({
      lang,
      setLang,
      t: (key, vars) => {
        let str = DICTS[lang][key] ?? DICTS.en[key];
        if (str === undefined) return key; // missing key: show the key so gaps are visible
        if (vars) {
          str = str.replace(/\{(\w+)\}/g, (m, k: string) =>
            vars[k] !== undefined ? String(vars[k]) : m,
          );
        }
        return str;
      },
    }),
    [lang],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within <I18nProvider>");
  return ctx;
}

/** Convenience: just the translation function. */
export function useT() {
  return useI18n().t;
}
