import React, { useState } from 'react';
import { MerchantProfile } from '../types/api';
import { api, ApiClientError } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { Store, Edit3, X, Save, CheckCircle2, AlertCircle, MapPin, Tag, Globe, AlignLeft } from 'lucide-react';

interface MerchantProfileCardProps {
  profile: MerchantProfile | null;
  onProfileUpdated?: (updated: MerchantProfile) => void;
}

export const MerchantProfileCard: React.FC<MerchantProfileCardProps> = ({
  profile,
  onProfileUpdated,
}) => {
  const { refreshProfile } = useAuth();
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Form fields
  const [businessName, setBusinessName] = useState(profile?.business_name || '');
  const [category, setCategory] = useState(profile?.category || '');
  const [location, setLocation] = useState(profile?.location || '');
  const [description, setDescription] = useState(profile?.description || '');
  const [timezone, setTimezone] = useState(profile?.timezone || 'Asia/Kolkata');

  const startEditing = () => {
    if (!profile) return;
    setBusinessName(profile.business_name);
    setCategory(profile.category || '');
    setLocation(profile.location || '');
    setDescription(profile.description || '');
    setTimezone(profile.timezone || 'Asia/Kolkata');
    setErrorMessage(null);
    setSuccessMessage(null);
    setIsEditing(true);
  };

  const cancelEditing = () => {
    setIsEditing(false);
    setErrorMessage(null);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);

    const trimmedName = businessName.trim();
    if (!trimmedName) {
      setErrorMessage('Business name is required.');
      return;
    }
    if (trimmedName.length > 160) {
      setErrorMessage('Business name cannot exceed 160 characters.');
      return;
    }

    setIsSaving(true);
    try {
      const updated = await api.updateMerchantProfile({
        business_name: trimmedName,
        category: category.trim() || null,
        location: location.trim() || null,
        description: description.trim() || null,
        timezone: timezone.trim() || 'Asia/Kolkata',
      });

      setSuccessMessage('Merchant profile updated successfully.');
      setIsEditing(false);
      await refreshProfile();
      if (onProfileUpdated) {
        onProfileUpdated(updated);
      }
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage('Failed to update merchant profile. Please try again.');
      }
    } finally {
      setIsSaving(false);
    }
  };

  if (!profile) {
    return (
      <div className="bg-white border border-surface-200 rounded p-5 shadow-sm">
        <div className="text-xs text-surface-800">Loading merchant profile...</div>
      </div>
    );
  }

  return (
    <div className="bg-white border border-surface-200 rounded p-5 shadow-sm">
      <div className="flex items-center justify-between border-b border-surface-100 pb-3 mb-4">
        <div className="flex items-center gap-2">
          <Store className="w-4 h-4 text-emerald-700" />
          <h2 className="text-sm font-semibold text-surface-900">Merchant Workspace Profile</h2>
        </div>
        {!isEditing && (
          <button
            onClick={startEditing}
            className="inline-flex items-center gap-1 text-xs font-medium text-emerald-800 hover:text-emerald-900 border border-surface-200 hover:border-surface-300 bg-surface-50 hover:bg-surface-100 px-2.5 py-1 rounded transition-colors"
          >
            <Edit3 className="w-3 h-3" />
            Edit Profile
          </button>
        )}
      </div>

      {successMessage && (
        <div className="mb-4 p-2.5 rounded bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex items-center gap-2">
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
          <span>{successMessage}</span>
        </div>
      )}

      {errorMessage && (
        <div className="mb-4 p-2.5 rounded bg-red-50 border border-red-200 text-xs text-red-800 flex items-center gap-2">
          <AlertCircle className="w-3.5 h-3.5 text-red-600 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      {isEditing ? (
        <form onSubmit={handleSave} className="space-y-3.5 text-xs">
          <div>
            <label htmlFor="edit-business-name" className="block font-medium text-surface-900 mb-1">
              Business Name <span className="text-red-500">*</span>
            </label>
            <input
              id="edit-business-name"
              type="text"
              required
              value={businessName}
              onChange={(e) => setBusinessName(e.target.value)}
              className="w-full px-3 py-1.5 rounded border border-surface-300 bg-white text-surface-900 focus:outline-none focus:ring-1 focus:ring-emerald-700 focus:border-emerald-700"
              maxLength={160}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="edit-category" className="block font-medium text-surface-900 mb-1">
                Category
              </label>
              <input
                id="edit-category"
                type="text"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="Restaurant, Retail, etc."
                className="w-full px-3 py-1.5 rounded border border-surface-300 bg-white text-surface-900 focus:outline-none focus:ring-1 focus:ring-emerald-700 focus:border-emerald-700"
                maxLength={120}
              />
            </div>

            <div>
              <label htmlFor="edit-timezone" className="block font-medium text-surface-900 mb-1">
                Timezone
              </label>
              <select
                id="edit-timezone"
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="w-full px-2.5 py-1.5 rounded border border-surface-300 bg-white text-surface-900 focus:outline-none focus:ring-1 focus:ring-emerald-700 focus:border-emerald-700"
              >
                <option value="Asia/Kolkata">Asia/Kolkata (IST)</option>
                <option value="UTC">UTC</option>
                <option value="Asia/Dubai">Asia/Dubai (GST)</option>
                <option value="Asia/Singapore">Asia/Singapore (SGT)</option>
              </select>
            </div>
          </div>

          <div>
            <label htmlFor="edit-location" className="block font-medium text-surface-900 mb-1">
              Location / City
            </label>
            <input
              id="edit-location"
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Indiranagar, Bengaluru"
              className="w-full px-3 py-1.5 rounded border border-surface-300 bg-white text-surface-900 focus:outline-none focus:ring-1 focus:ring-emerald-700 focus:border-emerald-700"
              maxLength={200}
            />
          </div>

          <div>
            <label htmlFor="edit-description" className="block font-medium text-surface-900 mb-1">
              Store Description
            </label>
            <textarea
              id="edit-description"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief description of your store offerings, specialty, and policies."
              className="w-full px-3 py-1.5 rounded border border-surface-300 bg-white text-surface-900 focus:outline-none focus:ring-1 focus:ring-emerald-700 focus:border-emerald-700"
            />
          </div>

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-surface-100">
            <button
              type="button"
              onClick={cancelEditing}
              disabled={isSaving}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded border border-surface-300 bg-white text-surface-900 hover:bg-surface-50 font-medium disabled:opacity-60"
            >
              <X className="w-3.5 h-3.5" />
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-800 text-white font-medium disabled:opacity-60 shadow-sm transition-colors"
            >
              <Save className="w-3.5 h-3.5" />
              {isSaving ? 'Saving...' : 'Save Profile'}
            </button>
          </div>
        </form>
      ) : (
        <div className="space-y-3 text-xs">
          <div>
            <span className="text-[11px] font-medium text-surface-800">Business Name</span>
            <p className="text-sm font-semibold text-surface-900">{profile.business_name}</p>
          </div>

          <div className="grid grid-cols-2 gap-3 pt-1">
            <div className="flex items-start gap-1.5">
              <Tag className="w-3.5 h-3.5 text-emerald-700 mt-0.5 shrink-0" />
              <div>
                <span className="text-[11px] text-surface-800">Category</span>
                <p className="font-medium text-surface-900">{profile.category || 'Not specified'}</p>
              </div>
            </div>

            <div className="flex items-start gap-1.5">
              <Globe className="w-3.5 h-3.5 text-emerald-700 mt-0.5 shrink-0" />
              <div>
                <span className="text-[11px] text-surface-800">Timezone</span>
                <p className="font-medium text-surface-900">{profile.timezone}</p>
              </div>
            </div>
          </div>

          <div className="flex items-start gap-1.5 pt-1">
            <MapPin className="w-3.5 h-3.5 text-emerald-700 mt-0.5 shrink-0" />
            <div>
              <span className="text-[11px] text-surface-800">Location</span>
              <p className="font-medium text-surface-900">{profile.location || 'Not specified'}</p>
            </div>
          </div>

          {profile.description && (
            <div className="flex items-start gap-1.5 pt-1 border-t border-surface-100">
              <AlignLeft className="w-3.5 h-3.5 text-emerald-700 mt-0.5 shrink-0" />
              <div>
                <span className="text-[11px] text-surface-800">Description</span>
                <p className="text-surface-900 whitespace-pre-wrap">{profile.description}</p>
              </div>
            </div>
          )}

          <div className="text-[10px] text-surface-800 pt-2 border-t border-surface-100">
            Registered: {new Date(profile.created_at).toLocaleDateString()}
          </div>
        </div>
      )}
    </div>
  );
};
