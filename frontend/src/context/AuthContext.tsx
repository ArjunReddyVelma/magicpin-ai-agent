import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { User, MerchantProfile } from '../types/api';
import { api, ApiClientError } from '../api/client';

interface AuthContextType {
  user: User | null;
  merchant: MerchantProfile | null;
  csrfToken: string | null;
  isLoading: boolean;
  error: string | null;
  isAuthenticated: boolean;
  login: (payload: { email: string; password: string }) => Promise<void>;
  register: (payload: {
    email: string;
    password: string;
    full_name: string;
    business_name: string;
    category?: string;
    location?: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
  deleteAccount: (password: string) => Promise<void>;
  refreshProfile: () => Promise<void>;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [merchant, setMerchant] = useState<MerchantProfile | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const clearSession = useCallback(() => {
    setUser(null);
    setMerchant(null);
    setCsrfToken(null);
    api.setCsrfToken(null);
  }, []);

  // Hook 401 callback in API client
  useEffect(() => {
    api.setOnUnauthorized(() => {
      clearSession();
    });
  }, [clearSession]);

  // Restore session on mount via /v1/auth/me
  useEffect(() => {
    let mounted = true;

    async function restoreSession() {
      try {
        const res = await api.getMe();
        if (mounted) {
          setUser(res.user);
          setMerchant(res.merchant);
          setCsrfToken(res.csrf_token);
        }
      } catch {
        // Unauthenticated or expired session on initial boot is normal
        if (mounted) {
          clearSession();
        }
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    }

    restoreSession();

    return () => {
      mounted = false;
    };
  }, [clearSession]);

  const login = async (payload: { email: string; password: string }) => {
    setError(null);
    try {
      const res = await api.login(payload);
      setUser(res.user);
      setMerchant(res.merchant);
      setCsrfToken(res.csrf_token);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError('Login failed. Please check your credentials.');
      }
      throw err;
    }
  };

  const register = async (payload: {
    email: string;
    password: string;
    full_name: string;
    business_name: string;
    category?: string;
    location?: string;
  }) => {
    setError(null);
    try {
      const res = await api.register(payload);
      setUser(res.user);
      setMerchant(res.merchant);
      setCsrfToken(res.csrf_token);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError('Registration failed. Please check the provided details.');
      }
      throw err;
    }
  };

  const logout = async () => {
    try {
      await api.logout();
    } catch {
      // Clean up local state regardless of server logout result
    } finally {
      clearSession();
    }
  };

  const deleteAccount = async (password: string) => {
    setError(null);
    try {
      await api.deleteAccount(password);
      clearSession();
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError('Failed to delete account.');
      }
      throw err;
    }
  };

  const refreshProfile = async () => {
    try {
      const updated = await api.getMerchantProfile();
      setMerchant(updated);
    } catch (err) {
      // Ignore or log
    }
  };

  const clearError = () => setError(null);

  return (
    <AuthContext.Provider
      value={{
        user,
        merchant,
        csrfToken,
        isLoading,
        error,
        isAuthenticated: !!user && !!merchant,
        login,
        register,
        logout,
        deleteAccount,
        refreshProfile,
        clearError,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
