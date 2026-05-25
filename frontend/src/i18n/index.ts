import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Locale = "zh" | "en";

export const locales: Locale[] = ["zh", "en"];

export const localeLabels: Record<Locale, string> = {
  zh: "中文",
  en: "English",
};

// ── Translation dictionary type ──
export interface Translations {
  common: {
    appName: string;
    dashboard: string;
    upload: string;
    getStarted: string;
    viewDashboard: string;
  };
  home: {
    title: string;
    description: string;
    steps: Array<{ title: string; desc: string }>;
  };
  dashboard: {
    title: string;
    subtitle: string;
    empty: string;
    uploadLink: string;
    emptyTail: string;
  };
  upload: {
    title: string;
    subtitle: string;
    dragDrop: string;
    or: string;
    browse: string;
  };
}

// ── Dictionaries ──
const zh: Translations = {
  common: {
    appName: "小说转短剧",
    dashboard: "项目列表",
    upload: "上传小说",
    getStarted: "开始使用",
    viewDashboard: "查看项目",
  },
  home: {
    title: "小说转短剧 Agent",
    description: "将小说转化为系列短视频。上传你的小说，让 AI 自动编排改编流程。",
    steps: [
      { title: "上传", desc: "支持 TXT、DOCX、EPUB 格式的小说文件上传。" },
      { title: "处理", desc: "AI Agent 自动解析、总结，并将你的故事改编为剧集。" },
      { title: "导出", desc: "下载最终的短剧视频，格式为 MP4。" },
    ],
  },
  dashboard: {
    title: "项目列表",
    subtitle: "查看和管理你的短剧生成项目和任务。",
    empty: "暂无项目。",
    uploadLink: "上传一部小说",
    emptyTail: "开始使用吧。",
  },
  upload: {
    title: "上传小说",
    subtitle: "支持的格式：TXT、DOCX、EPUB",
    dragDrop: "将小说文件拖拽到此处",
    or: "或",
    browse: "选择文件",
  },
};

const en: Translations = {
  common: {
    appName: "Novel2Drama",
    dashboard: "Dashboard",
    upload: "Upload",
    getStarted: "Get Started",
    viewDashboard: "View Dashboard",
  },
  home: {
    title: "Novel2Drama Agent",
    description:
      "Convert novels into serialized short-form drama videos. Upload your story and let AI orchestrate the adaptation.",
    steps: [
      { title: "Upload", desc: "Upload your novel in TXT, DOCX, or EPUB format." },
      { title: "Process", desc: "AI agents parse, summarize, and adapt your story into episodes." },
      { title: "Export", desc: "Download the final drama video in MP4 format." },
    ],
  },
  dashboard: {
    title: "Dashboard",
    subtitle: "Monitor your drama generation projects and jobs.",
    empty: "No projects yet.",
    uploadLink: "Upload a novel",
    emptyTail: "to get started.",
  },
  upload: {
    title: "Upload Novel",
    subtitle: "Supported formats: TXT, DOCX, EPUB",
    dragDrop: "Drag & drop your novel file here",
    or: "or",
    browse: "Browse Files",
  },
};

const dicts: Record<Locale, Translations> = { zh, en };

// ── Language store ──
interface LangState {
  locale: Locale;
  setLocale: (l: Locale) => void;
}

export const useLocaleStore = create<LangState>()(
  persist(
    (set) => ({
      locale: "zh",
      setLocale: (locale: Locale) => set({ locale }),
    }),
    { name: "novel2drama-locale" }
  )
);

// ── Hook ──
export function useT() {
  const locale = useLocaleStore((s) => s.locale);
  return dicts[locale];
}

export function useLocale() {
  return useLocaleStore((s) => s.locale);
}

export function useSetLocale() {
  return useLocaleStore((s) => s.setLocale);
}
