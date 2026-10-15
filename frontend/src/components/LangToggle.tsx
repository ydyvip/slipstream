import { useI18n } from "../i18n";

/**
 * Top-right language switch: 中文 / EN. Uses each language's own endonym as
 * its label, so it stays understandable no matter which side is active.
 */
export function LangToggle() {
  const { lang, setLang } = useI18n();
  return (
    <div className="lang-toggle" role="group" aria-label="Language">
      <button
        type="button"
        className={lang === "zh" ? "active" : ""}
        onClick={() => setLang("zh")}
        aria-pressed={lang === "zh"}
        title="中文"
      >
        中文
      </button>
      <button
        type="button"
        className={lang === "en" ? "active" : ""}
        onClick={() => setLang("en")}
        aria-pressed={lang === "en"}
        title="English"
      >
        EN
      </button>
    </div>
  );
}
