import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { MerchantProfileCard } from '../components/MerchantProfileCard';
import { ApiClientError } from '../api/client';
import {
  User,
  Shield,
  LogOut,
  AlertTriangle,
  Lock,
  Trash2,
  CheckCircle2,
  Loader2,
  X,
  Clock,
  Mail,
  Fingerprint,
} from 'lucide-react';

export const SettingsPage: React.FC = () => {
  const { user, merchant, logout, deleteAccount } = useAuth();

  // Logout state
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  // Delete modal state
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const handleLogout = async () => {
    setIsLoggingOut(true);
    try {
      await logout();
    } catch {
      // Local state is cleared in finally block by AuthContext
    } finally {
      setIsLoggingOut(false);
    }
  };

  const handleDeleteAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedPassword = passwordConfirm.trim();
    if (!trimmedPassword) {
      setDeleteError('Password confirmation is required to delete your account.');
      return;
    }

    setIsDeleting(true);
    setDeleteError(null);

    try {
      await deleteAccount(trimmedPassword);
      // On success, AuthContext.deleteAccount clears session,
      // unmounting this page and routing to the login screen.
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        if (err.statusCode === 401) {
          setDeleteError('Incorrect password. Account deletion was rejected by the server.');
        } else {
          setDeleteError(err.message || 'Server rejected account deletion.');
        }
      } else {
        setDeleteError('Network error. Unable to verify account deletion.');
      }
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto pb-12">
      {/* Page Header */}
      <div>
        <h1 className="text-lg font-bold text-surface-900 tracking-tight">
          Merchant & Account Settings
        </h1>
        <p className="text-xs text-surface-800 mt-1">
          Manage your business profile, view active session security, and access account controls.
        </p>
      </div>

      {/* 1. Merchant Profile Section (Reusing MerchantProfileCard) */}
      <section className="space-y-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-surface-800">
          Store & Business Profile
        </h2>
        <MerchantProfileCard profile={merchant} />
      </section>

      {/* 2. User & Identity Information */}
      <section className="space-y-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-surface-800">
          User & Authentication Identity
        </h2>
        <div className="bg-white border border-surface-200 rounded p-5 shadow-xs space-y-4">
          <div className="flex items-center gap-2 border-b border-surface-100 pb-3">
            <User className="w-4 h-4 text-emerald-700" />
            <h3 className="text-sm font-semibold text-surface-900">Registered Account Owner</h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div>
              <span className="block text-[11px] font-medium text-surface-800 mb-0.5">
                Full Name
              </span>
              <p className="font-semibold text-surface-900">{user?.full_name || '—'}</p>
            </div>

            <div>
              <span className="block text-[11px] font-medium text-surface-800 mb-0.5 flex items-center gap-1">
                <Mail className="w-3 h-3 text-surface-800" />
                <span>Email Address (Login Identifier)</span>
              </span>
              <p className="font-semibold text-surface-900">{user?.email || '—'}</p>
            </div>

            <div>
              <span className="block text-[11px] font-medium text-surface-800 mb-0.5 flex items-center gap-1">
                <Fingerprint className="w-3 h-3 text-surface-800" />
                <span>User UUID</span>
              </span>
              <p className="font-mono text-[11px] text-surface-800 truncate">{user?.id || '—'}</p>
            </div>

            <div>
              <span className="block text-[11px] font-medium text-surface-800 mb-0.5 flex items-center gap-1">
                <Clock className="w-3 h-3 text-surface-800" />
                <span>Account Member Since</span>
              </span>
              <p className="text-surface-900">
                {user?.created_at ? new Date(user.created_at).toLocaleDateString() : '—'}
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* 3. Session Security & Sign-Out */}
      <section className="space-y-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-surface-800">
          Session Security
        </h2>
        <div className="bg-white border border-surface-200 rounded p-5 shadow-xs space-y-4">
          <div className="flex items-center justify-between border-b border-surface-100 pb-3">
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-emerald-700" />
              <h3 className="text-sm font-semibold text-surface-900">Active Authentication Session</h3>
            </div>
            <span className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase px-2 py-0.5 rounded bg-emerald-50 text-emerald-800 border border-emerald-200">
              <CheckCircle2 className="w-3 h-3 text-emerald-700" />
              <span>Active</span>
            </span>
          </div>

          <div className="text-xs text-surface-800 space-y-2">
            <p className="leading-relaxed">
              Your session is authenticated via an opaque hashed token stored in an <code className="bg-surface-100 px-1 py-0.5 rounded text-surface-900">HttpOnly; SameSite=Lax</code> cookie (<code className="bg-surface-100 px-1 py-0.5 rounded text-surface-900">mp_session</code>). State-mutating requests are cryptographically protected by an active session-bound CSRF token (<code className="bg-surface-100 px-1 py-0.5 rounded text-surface-900">X-CSRF-Token</code>).
            </p>
          </div>

          <div className="pt-2 flex items-center justify-between">
            <p className="text-[11px] text-surface-800">
              Terminating this session will invalidate the server-side session token and clear your authentication cookies.
            </p>
            <button
              onClick={handleLogout}
              disabled={isLoggingOut}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-surface-800 hover:text-surface-900 bg-surface-50 hover:bg-surface-100 border border-surface-300 rounded transition-colors shadow-2xs"
              title="Sign Out"
            >
              {isLoggingOut ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <LogOut className="w-3.5 h-3.5" />
              )}
              <span>Sign Out</span>
            </button>
          </div>
        </div>
      </section>

      {/* 4. Danger Zone: Permanent Account Deletion */}
      <section className="space-y-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-red-700">
          Danger Zone
        </h2>
        <div className="bg-red-50/40 border border-red-200 rounded p-5 shadow-xs space-y-4">
          <div className="flex items-center gap-2 border-b border-red-200/60 pb-3">
            <AlertTriangle className="w-4 h-4 text-red-600" />
            <h3 className="text-sm font-semibold text-red-950">Permanent Account Deletion</h3>
          </div>

          <p className="text-xs text-red-900 leading-relaxed">
            Deleting your account will permanently purge your user credentials, merchant profile, all business context documents, conversation records, and generated assistant turns. <strong>This action is immediate and cannot be reversed.</strong>
          </p>

          <div className="pt-1 flex justify-end">
            <button
              onClick={() => {
                setPasswordConfirm('');
                setDeleteError(null);
                setIsDeleteModalOpen(true);
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-red-700 hover:bg-red-800 rounded transition-colors shadow-2xs"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Delete Account Permanently</span>
            </button>
          </div>
        </div>
      </section>

      {/* Delete Confirmation Modal */}
      {isDeleteModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded border border-surface-200 shadow-xl max-w-md w-full p-5 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-surface-100">
              <div className="flex items-center gap-2 text-red-700">
                <AlertTriangle className="w-5 h-5 shrink-0" />
                <h3 className="text-sm font-bold">Confirm Account Deletion</h3>
              </div>
              <button
                onClick={() => setIsDeleteModalOpen(false)}
                disabled={isDeleting}
                className="text-surface-800 hover:text-surface-900"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-surface-800 leading-relaxed">
              This action is <strong className="text-red-700">permanent and irreversible</strong>. All your merchant profile details, store context policies, FAQs, and AI conversation history will be permanently deleted from the database.
            </p>

            {deleteError && (
              <div className="p-2.5 rounded bg-red-50 border border-red-200 text-xs text-red-800">
                {deleteError}
              </div>
            )}

            <form onSubmit={handleDeleteAccount} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-surface-900 mb-1 flex items-center gap-1">
                  <Lock className="w-3 h-3 text-surface-800" />
                  <span>Enter Password to Confirm</span>
                </label>
                <input
                  type="password"
                  required
                  value={passwordConfirm}
                  onChange={(e) => setPasswordConfirm(e.target.value)}
                  placeholder="Your current account password"
                  disabled={isDeleting}
                  className="w-full px-3 py-2 text-xs bg-surface-50 border border-surface-200 rounded focus:outline-none focus:ring-1 focus:ring-red-600 focus:bg-white text-surface-900 disabled:opacity-60"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-surface-100">
                <button
                  type="button"
                  onClick={() => setIsDeleteModalOpen(false)}
                  disabled={isDeleting}
                  className="px-3 py-1.5 text-xs font-medium text-surface-800 hover:text-surface-900 rounded border border-surface-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isDeleting || !passwordConfirm.trim()}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-red-700 hover:bg-red-800 disabled:opacity-50 disabled:cursor-not-allowed rounded shadow-xs"
                >
                  {isDeleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                  <span>Confirm Permanent Deletion</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
