import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Header } from "@/components/header";

export const metadata: Metadata = {
  title: "Novel2Drama Agent",
  description: "Convert novels into serialized short-form drama videos",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh">
      <body>
        <div className="min-h-screen flex flex-col">
          <Header />
          <main className="flex-1">
            <Providers>{children}</Providers>
          </main>
        </div>
      </body>
    </html>
  );
}
