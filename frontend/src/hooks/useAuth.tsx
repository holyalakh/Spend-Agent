import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  completeNewPassword,
  restoreSession,
  signIn,
  signOut,
} from "../auth/cognitoAuth";
import type { AuthChallenge } from "../types";

interface AuthContextValue {
  email: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  challenge: AuthChallenge;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  setNewPassword: (password: string) => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [email, setEmail] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [challenge, setChallenge] = useState<AuthChallenge>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    restoreSession()
      .then((resolvedEmail) => {
        if (resolvedEmail) {
          setEmail(resolvedEmail);
        }
      })
      .finally(() => setIsLoading(false));
  }, []);

  const login = useCallback(async (loginEmail: string, password: string) => {
    setError(null);
    const result = await signIn(loginEmail, password);
    setEmail(result.email);
    setChallenge(result.challenge);
  }, []);

  const setNewPassword = useCallback(async (password: string) => {
    setError(null);
    const result = await completeNewPassword(password);
    setChallenge(null);
    setEmail(result.email);
  }, []);

  const logout = useCallback(async () => {
    await signOut();
    setEmail(null);
    setChallenge(null);
    setError(null);
  }, []);

  const isAuthenticated = Boolean(email) && !challenge;

  const value = useMemo<AuthContextValue>(
    () => ({
      email,
      isAuthenticated,
      isLoading,
      challenge,
      error,
      login,
      setNewPassword,
      logout,
      clearError: () => setError(null),
    }),
    [email, isAuthenticated, isLoading, challenge, error, login, setNewPassword, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
