import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Store, AlertCircle, ArrowRight } from 'lucide-react';

interface LoginPageProps {
  onSwitchToRegister: () => void;
  onViewPrivacy?: () => void;
  onViewTerms?: () => void;
}

export const LoginPage: React.FC<LoginPageProps> = ({
  onSwitchToRegister,
  onViewPrivacy,
  onViewTerms,
}) => {
  const { login, error, clearError } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    clearError();

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !password) {
      setLocalError('Please enter both your email address and password.');
      return;
    }

    setIsSubmitting(true);
    try {
      await login({ email: trimmedEmail, password });
    } catch {
      // Error message is set in AuthContext
    } finally {
      setIsSubmitting(false);
    }
  };

  const activeError = localError || error;

  return (
    <div className="min-h-screen bg-surface-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex items-center justify-center gap-2.5">
          <div className="w-9 h-9 rounded bg-emerald-700 flex items-center justify-center text-white font-bold text-base shadow-sm">
            <Store className="w-5 h-5 text-white" />
          </div>
          <span className="text-xl font-bold tracking-tight text-surface-900">
            Magicpin AI Agent
          </span>
        </div>
        <h2 className="mt-4 text-center text-sm font-semibold text-surface-900">
          Sign in to your Merchant Workspace
        </h2>
        <p className="mt-1 text-center text-xs text-surface-800">
          Standalone AI support copilot for store operations
        </p>
      </div>

      <div className="mt-6 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-6 sm:px-8 border border-surface-200 rounded shadow-sm">
          {activeError && (
            <div className="mb-5 p-3 rounded bg-red-50 border border-red-200 flex items-start gap-2.5 text-xs text-red-800">
              <AlertCircle className="w-4 h-4 text-red-600 mt-0.5 shrink-0" />
              <div className="flex-1">{activeError}</div>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div>
              <label htmlFor="login-email" className="block text-xs font-medium text-surface-900">
                Email Address
              </label>
              <input
                id="login-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="merchant@example.com"
                className="mt-1 block w-full px-3 py-2 text-xs rounded border border-surface-300 bg-white text-surface-900 placeholder-surface-800 focus:outline-none focus:ring-1 focus:ring-emerald-700 focus:border-emerald-700"
              />
            </div>

            <div>
              <label htmlFor="login-password" className="block text-xs font-medium text-surface-900">
                Password
              </label>
              <input
                id="login-password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="mt-1 block w-full px-3 py-2 text-xs rounded border border-surface-300 bg-white text-surface-900 placeholder-surface-800 focus:outline-none focus:ring-1 focus:ring-emerald-700 focus:border-emerald-700"
              />
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full flex items-center justify-center gap-2 py-2 px-4 rounded text-xs font-medium text-white bg-emerald-700 hover:bg-emerald-800 focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-emerald-700 disabled:opacity-60 disabled:cursor-not-allowed shadow-sm transition-colors"
            >
              {isSubmitting ? (
                <span>Signing in...</span>
              ) : (
                <>
                  <span>Sign In</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </>
              )}
            </button>
          </form>

          <div className="mt-6 pt-5 border-t border-surface-200 text-center text-xs text-surface-800">
            <span>Don't have a merchant workspace? </span>
            <button
              type="button"
              onClick={onSwitchToRegister}
              className="font-medium text-emerald-800 hover:text-emerald-900 underline focus:outline-none"
            >
              Register here
            </button>
          </div>
        </div>

        <div className="mt-6 text-center text-[11px] text-surface-800 space-y-2">
          <p>Isolated session protected with Argon2id and session-bound CSRF validation.</p>
          <div className="flex items-center justify-center gap-3">
            <button
              type="button"
              onClick={onViewPrivacy}
              className="hover:text-surface-900 underline"
            >
              Privacy Policy
            </button>
            <span>&bull;</span>
            <button
              type="button"
              onClick={onViewTerms}
              className="hover:text-surface-900 underline"
            >
              Terms of Service
            </button>
            <span>&bull;</span>
            <span>Draft Disclosures</span>
          </div>
        </div>
      </div>
    </div>
  );
};
