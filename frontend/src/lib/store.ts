import { create } from "zustand";

interface AppState {
  projectId: string | null;
  setProjectId: (id: string | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  projectId: null,
  setProjectId: (id) => set({ projectId: id }),
}));
