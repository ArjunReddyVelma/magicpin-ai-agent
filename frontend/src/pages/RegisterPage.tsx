import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { Store, AlertCircle, ArrowRight } from 'lucide-react';

interface RegisterPageProps {
  onSwitchToLogin: () => void;
  onViewPrivacy?: () => void;
  onViewTerms?: () => void;
}

export const RegisterPage: React.FC<RegisterPageProps> = ({
  onSwitchToLogin,
  onViewPrivacy,
  onViewTerms,
}) => {
  const { register, error, clearError } = useAuth();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [businessName, setBusinessName] = useState('');
  const [category, setCategory] = useState('Restaurant');
  const [location, setLocation] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    clearError();

    const trimmedEmail = email.trim();
    const trimmedFullName = fullName.trim();
    const trimmedBusiness = businessName.trim();

    if (!trimmedFullName || !trimmedEmail || !password || !trimmedBusiness) {
      setLocalError('Please complete all required fields.');
      return;
    }

    if (password.length < 8) {
      setLocalError('Password must be at least 8 characters long.');
      return;
    }

    setIsSubmitting(true);
    try {
      await register({
        email: trimmedEmail,
        password,
        full_name: trimmedFullName,
        business_name: trimmedBusiness,
        category: category || undefined,
        location: location.trim() || undefined,
      });
    } catch {
      // Error message set in AuthContext
    } finally {
      setIsSubmitting(false);
    }
  };

  const activeError = localError || error;

  return (
    <div className="min-h-screen bg-surface-50 flex flex-col justify-center py-10 sm:px-6 lg:px-8">
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
          Create your Merchant Workspace
        </h2>
        <p className="mt-1 text-center text-xs text-surface-800">
          Get started with your dedicated AI support copilot
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

          <form onSubmit={handleSubmit} className="space-y-3.5" noValidate>
            <div>
              <label htmlFor="reg-name" className="block text-xs font-medium text-surface-900">
                Full Name <span className="text-red-500">*</span>
              </label>
              <input
                id="reg-name"
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Rohit Sharma"
                className="mt-1 block w-full px-3 py-2 text-xs rounded border border-surface-300 bg-white text-surface-900 placeholder-surface-800 focus:outline-none focus:ring-1 focus:ring-emerald-700 focus:border-emerald-700"
              />
            </div>

            <div>
              <label htmlFor="reg-email" className="block text-xs font-medium text-surface-900">
                Email Address <span className="text-red-500">*</span>
              </label>
              <input
                id="reg-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="owner@store.com"
                className="mt-1 block w-full px-3 py-2 text-xs rounded border border-surface-300 bg-white text-surface-900 placeholder-surface-800 focus:outline-none focus:ring-1 focus:ring-emerald-700 focus:border-emerald-700"
              />
            </div>

            <div>
              <label htmlFor="reg-password" className="block text-xs font-medium text-surface-900">
                Password <span className="text-red-500">*</span> (min 8 chars)
              </label>
              <input
                id="reg-password"
                type="password"
                required
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="mt-1 block w-full px-3 py-2 text-xs rounded border border-surface-300 bg-white text-surface-900 placeholder-surface-800 focus:outline-none focus:ring-1 focus:ring-emerald-700 focus:border-emerald-700"
              />
            </div>

            <div>
              <label htmlFor="reg-business" className="block text-xs font-medium text-surface-900">
                Business Name <span className="text-red-500">*</span>
              </label>
              <input
                id="reg-business"
                type="text"
                required
                value={businessName}
                onChange={(e) => setBusinessName(e.target.value)}
                placeholder="Sharma Sweets & Cafe"
                className="mt-1 block w-full px-3 py-2 text-xs rounded border border-surface-300 bg-white text-surface-900 placeholder-surface-800 focus:outline-none focus:ring-1 focus:ring-emerald-700 focus:border-emerald-700"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="reg-category" className="block text-xs font-medium text-surface-900">
                  Category
                </label>
                <select
                  id="reg-category"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="mt-1 block w-full px-2.5 py-2 text-xs rounded border border-surface-300 bg-white text-surface-900 focus:outline-none focus:ring-1 focus:ring-emerald-700 focus:border-emerald-700"
                >
                  <option value="Restaurant">Restaurant</option>
                  <option value="Grocery">Grocery</option>
                  <option value="Fashion">Fashion & Apparel</option>
                  <option value="Electronics">Electronics</option>
                  <option value="Spa & Salon">Spa & Salon</option>
                  <option value="Other">Other Retail</option>
                </select>
              </div>

              <div>
                <label htmlFor="reg-location" className="block text-xs font-medium text-surface-900">
                  Location / City
                </label>
                <input
                  id="reg-location"
                  type="text"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  placeholder="Connaught Place, Delhi"
                  className="mt-1 block w-full px-3 py-2 text-xs rounded border border-surface-300 bg-white text-surface-900 placeholder-surface-800 focus:outline-none focus:ring-1 focus:ring-emerald-700 focus:border-emerald-700"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full mt-2 flex items-center justify-center gap-2 py-2 px-4 rounded text-xs font-medium text-white bg-emerald-700 hover:bg-emerald-800 focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-emerald-700 disabled:opacity-60 disabled:cursor-not-allowed shadow-sm transition-colors"
            >
              {isSubmitting ? (
                <span>Registering Workspace...</span>
              ) : (
                <>
                  <span>Create Workspace</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </>
              )}
            </button>

            <p className="mt-3 text-[11px] text-surface-800 text-center leading-relaxed">
              By creating a workspace, you agree to the{' '}
              <button
                type="button"
                onClick={onViewTerms}
                className="underline text-emerald-800 hover:text-emerald-950 font-medium"
              >
                Terms of Service
              </button>{' '}
              and acknowledge our{' '}
              <button
                type="button"
                onClick={onViewPrivacy}
                className="underline text-emerald-800 hover:text-emerald-950 font-medium"
              >
                Privacy Policy
              </button>
              .
            </p>
          </form>

          <div className="mt-6 pt-5 border-t border-surface-200 text-center text-xs text-surface-800">
            <span>Already have an account? </span>
            <button
              type="button"
              onClick={onSwitchToLogin}
              className="font-medium text-emerald-800 hover:text-emerald-900 underline focus:outline-none"
            >
              Sign in here
            </button>
          </div>
        </div>

        {/* Unauthenticated Legal Footer */}
        <div className="mt-6 text-center text-[11px] text-surface-800 flex items-center justify-center gap-3">
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
          <span>Draft Operational Disclosures</span>
        </div>
      </div>
    </div>
  );
};
