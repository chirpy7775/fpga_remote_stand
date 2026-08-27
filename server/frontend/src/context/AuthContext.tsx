import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type User } from "../lib/api";

type AuthContextValue = {
  user: User | null;
  loading: boolean;
  allowAnonymous: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, email?: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [allowAnonymous, setAllowAnonymous] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .me()
      .then((data) => {
        setUser(data.user);
        setAllowAnonymous(Boolean(data.allow_anonymous));
      })
      .catch(() => {
        setUser(null);
        setAllowAnonymous(false);
      })
      .finally(() => setLoading(false));
  }, []);

  const value: AuthContextValue = {
    user,
    loading,
    allowAnonymous,
    login: async (username, password) => {
      const data = await api.login(username, password);
      setUser(data.user);
    },
    register: async (username, password, email) => {
      const data = await api.register(username, password, email);
      setUser(data.user);
    },
    logout: async () => {
      await api.logout();
      setUser(null);
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside provider");
  return ctx;
}
