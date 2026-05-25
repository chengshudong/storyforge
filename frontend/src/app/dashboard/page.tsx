"use client";

import { useT } from "@/i18n";

export default function DashboardPage() {
  const t = useT();

  return (
    <div className="max-w-6xl mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold mb-2">{t.dashboard.title}</h1>
      <p className="text-muted-foreground mb-8">
        {t.dashboard.subtitle}
      </p>

      <div className="rounded-lg border bg-card p-8 text-center">
        <p className="text-muted-foreground">
          {t.dashboard.empty}{" "}
          <a href="/upload" className="text-primary underline">
            {t.dashboard.uploadLink}
          </a>
          {t.dashboard.emptyTail}
        </p>
      </div>
    </div>
  );
}
