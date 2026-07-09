"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Globe } from "lucide-react";

import { Icon } from "@/components/ui";
import { locales, type Locale } from "@/lib/i18n/config";
import { useI18n } from "@/lib/i18n/I18nProvider";

/**
 * Polished language menu (owner review): a quiet pill button showing the
 * current language and a small custom dropdown — no raw native select menu.
 * Switching persists the locale and flips RTL/LTR instantly, exactly as
 * before; closes on outside click and Escape.
 */
export function LanguageSwitcher() {
  const { locale, setLocale, t } = useI18n();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  function choose(code: Locale) {
    setLocale(code);
    setOpen(false);
  }

  return (
    <div className="lang-menu" ref={rootRef}>
      <button
        type="button"
        className="lang-menu__button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t.language.label}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon icon={Globe} size="sm" />
        <span>{t.language[locale]}</span>
        <Icon icon={ChevronDown} size="sm" className="lang-menu__chevron" />
      </button>
      {open ? (
        <ul className="lang-menu__list" role="listbox" aria-label={t.language.label}>
          {locales.map((code) => (
            <li key={code}>
              <button
                type="button"
                role="option"
                aria-selected={code === locale}
                className="lang-menu__option"
                onClick={() => choose(code)}
              >
                <span>{t.language[code]}</span>
                {code === locale ? <Icon icon={Check} size="sm" /> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
