"use client";

import { useT } from "@/i18n";

export default function HomePage() {
  const t = useT();

  return (
    <div className="max-w-6xl mx-auto px-4 py-16">
      <div className="text-center space-y-6">
        <h1 className="text-4xl font-bold tracking-tight">
          {t.home.title}
        </h1>
        <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
          {t.home.description}
        </p>
        <div className="flex gap-4 justify-center pt-4">
          <a
            href="/upload"
            className="inline-flex items-center justify-center rounded-md bg-primary px-6 py-3 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            {t.common.getStarted}
          </a>
          <a
            href="/dashboard"
            className="inline-flex items-center justify-center rounded-md border px-6 py-3 text-sm font-medium hover:bg-muted"
          >
            {t.common.viewDashboard}
          </a>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-8 mt-20">
        {t.home.steps.map((step, i) => (
          <div key={i} className="rounded-lg border p-6 text-center">
            <div className="w-10 h-10 rounded-full bg-primary text-primary-foreground flex items-center justify-center mx-auto mb-3 font-bold">
              {i + 1}
            </div>
            <h3 className="font-semibold mb-2">{step.title}</h3>
            <p className="text-sm text-muted-foreground">{step.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
