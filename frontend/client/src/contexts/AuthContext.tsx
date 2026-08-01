import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, SessionData, User } from "@/lib/api";

interface AuthContextType {
  session: SessionData | null;
  user: User | null;
  loading: boolean;
  error: string | null;
  login: () => void;
  devLogin: (email: string, name: string) => void;
  createProfile: (data: any) => Promise<void>;
  updateUser: (data: Parameters<typeof api.updateProfile>[1]) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionData | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Verificar sesión al montar
  useEffect(() => {
    const checkSession = async () => {
      try {
        const sessionData = await api.getSession();
        setSession(sessionData);

        // Si está autenticado y no pending, cargar datos del usuario
        if (sessionData.authenticated && !sessionData.pending) {
          const userData = await api.getMe();
          setUser(userData);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error checking session");
      } finally {
        setLoading(false);
      }
    };

    checkSession();
  }, []);

  const handleLogin = () => {
    api.loginWithGoogle();
  };

  const handleDevLogin = (email: string, name: string) => {
    api.devLogin(email, name);
  };

  const handleCreateProfile = async (data: any) => {
    try {
      const newUser = await api.createProfile(data);
      setUser(newUser);
      setSession((prev) => ({
        ...prev!,
        authenticated: true,
        pending: false,
      }));
    } catch (err) {
      throw err;
    }
  };

  const handleUpdateUser = async (data: Parameters<typeof api.updateProfile>[1]) => {
    if (!user?.id) throw new Error("No hay sesión activa");
    const updated = await api.updateProfile(user.id, data);
    setUser(updated);
  };

  const handleLogout = async () => {
    try {
      await api.logout();
      setSession(null);
      setUser(null);
      window.location.href = "/";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error logging out");
    }
  };

  return (
    <AuthContext.Provider
      value={{
        session,
        user,
        loading,
        error,
        login: handleLogin,
        devLogin: handleDevLogin,
        createProfile: handleCreateProfile,
        updateUser: handleUpdateUser,
        logout: handleLogout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
