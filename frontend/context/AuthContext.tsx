"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { useRouter, usePathname } from "next/navigation";
import {
  loginUser,
  registerUser,
  fetchCurrentUser,
  updateProfile,
  type AuthUser,
} from "@/lib/auth-api";
import { GroupSetupModal } from "@/components/group-setup-modal";

const TOKEN_KEY = "smart_home_token";

interface AuthContextValue {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (identifier: string, password: string) => Promise<void>;
  register: (data: {
    email: string;
    username: string;
    password: string;
    full_name?: string;
  }) => Promise<void>;
  logout: () => void;
  updateGroupId: (groupId: string) => Promise<void>;
  openGroupSetup: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const PUBLIC_PATHS = ["/login", "/register"];

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showGroupSetup, setShowGroupSetup] = useState(false);
  const router = useRouter();
  const pathname = usePathname();

  // Hydrate from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem(TOKEN_KEY);
    if (stored) {
      setToken(stored);
      fetchCurrentUser(stored)
        .then((u) => {
          if (u) {
            setUser(u);
          } else {
            localStorage.removeItem(TOKEN_KEY);
            setToken(null);
          }
        })
        .finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, []);

  // Show group setup popup when user is authenticated but has no group_id
  useEffect(() => {
    if (!user) return;
    const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));
    if (!isPublic && !user.group_id) {
      setShowGroupSetup(true);
    } else {
      setShowGroupSetup(false);
    }
  }, [user, pathname]);

  // Redirect logic
  useEffect(() => {
    if (isLoading) return;
    const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));
    if (!user && !isPublic) {
      router.replace("/login");
    }
    if (user && isPublic) {
      router.replace("/dashboard");
    }
  }, [user, isLoading, pathname, router]);

  const login = useCallback(
    async (identifier: string, password: string) => {
      const res = await loginUser(identifier, password);
      if (res.token && res.user) {
        localStorage.setItem(TOKEN_KEY, res.token);
        setToken(res.token);
        setUser(res.user);
        router.replace("/dashboard");
      }
    },
    [router]
  );

  const register = useCallback(
    async (data: {
      email: string;
      username: string;
      password: string;
      full_name?: string;
    }) => {
      const res = await registerUser(data);
      if (res.token && res.user) {
        localStorage.setItem(TOKEN_KEY, res.token);
        setToken(res.token);
        setUser(res.user);
        router.replace("/dashboard");
      }
    },
    [router]
  );

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
    setShowGroupSetup(false);
    router.replace("/login");
  }, [router]);

  const updateGroupId = useCallback(
    async (groupId: string) => {
      if (!token) throw new Error("Chưa đăng nhập");
      const updated = await updateProfile(token, { group_id: groupId });
      setUser(updated);
      setShowGroupSetup(false);
    },
    [token]
  );

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user,
        isLoading,
        login,
        register,
        logout,
        updateGroupId,
        openGroupSetup: () => setShowGroupSetup(true),
      }}
    >
      {children}
      {showGroupSetup && (
        <GroupSetupModal
          onSave={updateGroupId}
          onSkip={() => setShowGroupSetup(false)}
        />
      )}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
