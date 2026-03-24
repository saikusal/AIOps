import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

type RefreshContextValue = {
  refreshMs: number | false;
  setRefreshMs: (value: number | false) => void;
  options: Array<{ label: string; value: number | false }>;
};

const REFRESH_STORAGE_KEY = "aiops-refresh-ms";

const RefreshContext = createContext<RefreshContextValue | null>(null);

const options: Array<{ label: string; value: number | false }> = [
  { label: "Off", value: false },
  { label: "10s", value: 10000 },
  { label: "15s", value: 15000 },
  { label: "30s", value: 30000 },
  { label: "60s", value: 60000 },
];

export function RefreshProvider({ children }: { children: ReactNode }) {
  const [refreshMs, setRefreshMsState] = useState<number | false>(15000);

  useEffect(() => {
    const stored = window.localStorage.getItem(REFRESH_STORAGE_KEY);
    if (!stored) return;
    if (stored === "false") {
      setRefreshMsState(false);
      return;
    }
    const numeric = Number(stored);
    if (!Number.isNaN(numeric) && numeric > 0) {
      setRefreshMsState(numeric);
    }
  }, []);

  const setRefreshMs = (value: number | false) => {
    setRefreshMsState(value);
    window.localStorage.setItem(REFRESH_STORAGE_KEY, value === false ? "false" : String(value));
  };

  const contextValue = useMemo(
    () => ({
      refreshMs,
      setRefreshMs,
      options,
    }),
    [refreshMs],
  );

  return <RefreshContext.Provider value={contextValue}>{children}</RefreshContext.Provider>;
}

export function useRefreshInterval() {
  const context = useContext(RefreshContext);
  if (!context) {
    throw new Error("useRefreshInterval must be used inside RefreshProvider");
  }
  return context;
}
