"use client";

import { useState } from "react";
import { useT } from "@/i18n";

export default function UploadPage() {
  const t = useT();
  const [dragOver, setDragOver] = useState(false);

  return (
    <div className="max-w-6xl mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold mb-2">{t.upload.title}</h1>
      <p className="text-muted-foreground mb-8">
        {t.upload.subtitle}
      </p>

      <div
        className={`rounded-lg border-2 border-dashed p-16 text-center transition-colors ${
          dragOver ? "border-primary bg-muted" : "border-muted-foreground/25"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
        }}
      >
        <p className="text-lg text-muted-foreground mb-4">
          {t.upload.dragDrop}
        </p>
        <p className="text-sm text-muted-foreground mb-4">{t.upload.or}</p>
        <button className="inline-flex items-center justify-center rounded-md bg-primary px-6 py-3 text-sm font-medium text-primary-foreground hover:opacity-90">
          {t.upload.browse}
        </button>
      </div>
    </div>
  );
}
