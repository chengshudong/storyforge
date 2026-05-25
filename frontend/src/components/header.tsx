"use client";

import Link from "next/link";
import { useT, useLocale, useSetLocale, locales, localeLabels } from "@/i18n";

export function Header() {
  const t = useT();
  const locale = useLocale();
  const setLocale = useSetLocale();

  const toggleLocale = () => {
    const next = locale === "zh" ? "en" : "zh";
    setLocale(next);
  };

  return (
    <header className="border-b bg-white">
      <nav className="max-w-6xl mx-auto px-4 h-14 flex items-center gap-6">
        <Link href="/" className="font-bold text-lg text-primary">
          {t.common.appName}
        </Link>
        <Link
          href="/dashboard"
          className="text-sm text-muted-foreground hover:text-primary"
        >
          {t.common.dashboard}
        </Link>
        <Link
          href="/upload"
          className="text-sm text-muted-foreground hover:text-primary"
        >
          {t.common.upload}
        </Link>
        <div className="flex-1" />
        <button
          onClick={toggleLocale}
          className="text-sm border rounded px-3 py-1 hover:bg-muted transition-colors"
          title={localeLabels[locale === "zh" ? "en" : "zh"]}
        >
          {localeLabels[locale]}
        </button>
      </nav>
    </header>
  );
}
