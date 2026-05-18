import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { fetchSession, logoutUser, type SessionUser } from "./api";

interface AuthState {
  loading: boolean;
  user: SessionUser | null;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  loading: true,
  user: null,
  refresh: async () => {},
  logout: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState<SessionUser | null>(null);

  const refresh = async () => {
    try {
      const result = await fetchSession();
      setUser(result.authenticated && result.user ? result.user : null);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    await logoutUser();
    setUser(null);
  };

  useEffect(() => {
    refresh();
  }, []);

  return (
    <AuthContext.Provider value={{ loading, user, refresh, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}
