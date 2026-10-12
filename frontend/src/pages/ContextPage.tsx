import React, { useState, useEffect, useCallback } from 'react';
import { api, ApiClientError } from '../api/client';
import { ContextItem, ContextItemType } from '../types/api';
import {
  BookOpen,
  Plus,
  RefreshCw,
  Search,
  AlertCircle,
  CheckCircle2,
  AlertTriangle,
  Edit2,
  Trash2,
  X,
  Save,
  Check,
  Clock,
  Layers,
} from 'lucide-react';

const APPROVED_TYPES: Array<{ value: ContextItemType; label: string; description: string }> = [
  { value: 'policy', label: 'Store Policy', description: 'Return, refund, cancellation, exchange guidelines' },
  { value: 'faq', label: 'FAQ', description: 'Frequently asked customer questions and standard answers' },
  { value: 'business_fact', label: 'Business Fact', description: 'Store specialty, background, certifications, owner details' },
  { value: 'service', label: 'Service / Offering', description: 'Dine-in, takeaway, delivery terms, custom orders' },
  { value: 'operating_info', label: 'Operating Info', description: 'Working hours, payment methods, holiday schedules' },
];

export const ContextPage: React.FC = () => {
  // List state
  const [items, setItems] = useState<ContextItem[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [listError, setListError] = useState<string | null>(null);
  const [successBanner, setSuccessBanner] = useState<string | null>(null);

  // Filters & Pagination
  const [selectedType, setSelectedType] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [page, setPage] = useState<number>(1);
  const pageSize = 15;

  // Create Modal State
  const [isCreateOpen, setIsCreateOpen] = useState<boolean>(false);
  const [createTitle, setCreateTitle] = useState<string>('');
  const [createType, setCreateType] = useState<ContextItemType>('policy');
  const [createContent, setCreateContent] = useState<string>('');
  const [createIsActive, setCreateIsActive] = useState<boolean>(true);
  const [isSubmittingCreate, setIsSubmittingCreate] = useState<boolean>(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Edit Modal State
  const [editingItem, setEditingItem] = useState<ContextItem | null>(null);
  const [editTitle, setEditTitle] = useState<string>('');
  const [editType, setEditType] = useState<ContextItemType>('policy');
  const [editContent, setEditContent] = useState<string>('');
  const [editIsActive, setEditIsActive] = useState<boolean>(true);
  const [isSubmittingEdit, setIsSubmittingEdit] = useState<boolean>(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [conflictDetails, setConflictDetails] = useState<{ expected: number; current: number } | null>(null);

  // Delete Confirmation State
  const [deletingItem, setDeletingItem] = useState<ContextItem | null>(null);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Fetch items
  const fetchItems = useCallback(async () => {
    setIsLoading(true);
    setListError(null);
    try {
      const params: { item_type?: string; is_active?: boolean; page: number; page_size: number } = {
        page,
        page_size: pageSize,
      };

      if (selectedType !== 'all') {
        params.item_type = selectedType;
      }
      if (selectedStatus === 'active') {
        params.is_active = true;
      } else if (selectedStatus === 'inactive') {
        params.is_active = false;
      }

      const res = await api.listContextItems(params);
      setItems(res.items);
      setTotal(res.total);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setListError(err.message);
      } else {
        setListError('Failed to load merchant context items.');
      }
    } finally {
      setIsLoading(false);
    }
  }, [page, selectedType, selectedStatus]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  // Client-side search filtering
  const displayedItems = items.filter((item) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return item.title.toLowerCase().includes(q) || item.content.toLowerCase().includes(q);
  });

  const getTypeBadgeClass = (type: ContextItemType) => {
    switch (type) {
      case 'policy':
        return 'bg-blue-50 text-blue-700 border-blue-200';
      case 'faq':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      case 'business_fact':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      case 'service':
        return 'bg-purple-50 text-purple-700 border-purple-200';
      case 'operating_info':
        return 'bg-indigo-50 text-indigo-700 border-indigo-200';
      default:
        return 'bg-slate-50 text-slate-700 border-slate-200';
    }
  };

  // Create Submit
  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreateError(null);

    const trimmedTitle = createTitle.trim();
    const trimmedContent = createContent.trim();

    if (!trimmedTitle) {
      setCreateError('Title is required.');
      return;
    }
    if (trimmedTitle.length > 200) {
      setCreateError('Title cannot exceed 200 characters.');
      return;
    }
    if (!trimmedContent) {
      setCreateError('Content is required.');
      return;
    }

    setIsSubmittingCreate(true);
    try {
      await api.createContextItem({
        title: trimmedTitle,
        item_type: createType,
        content: trimmedContent,
        is_active: createIsActive,
      });

      setIsCreateOpen(false);
      setCreateTitle('');
      setCreateContent('');
      setCreateIsActive(true);
      setSuccessBanner(`Context item "${trimmedTitle}" created successfully.`);
      fetchItems();
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setCreateError(err.message);
      } else {
        setCreateError('Failed to create context item. Please try again.');
      }
    } finally {
      setIsSubmittingCreate(false);
    }
  };

  // Open Edit Modal
  const openEditModal = (item: ContextItem) => {
    setEditingItem(item);
    setEditTitle(item.title);
    setEditType(item.item_type);
    setEditContent(item.content);
    setEditIsActive(item.is_active);
    setEditError(null);
    setConflictDetails(null);
  };

  // Edit Submit (with optimistic concurrency)
  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingItem) return;
    setEditError(null);
    setConflictDetails(null);

    const trimmedTitle = editTitle.trim();
    const trimmedContent = editContent.trim();

    if (!trimmedTitle) {
      setEditError('Title is required.');
      return;
    }
    if (trimmedTitle.length > 200) {
      setEditError('Title cannot exceed 200 characters.');
      return;
    }
    if (!trimmedContent) {
      setEditError('Content is required.');
      return;
    }

    setIsSubmittingEdit(true);
    try {
      const updated = await api.updateContextItem(editingItem.id, {
        expected_version: editingItem.version,
        title: trimmedTitle,
        item_type: editType,
        content: trimmedContent,
        is_active: editIsActive,
      });

      setEditingItem(null);
      setSuccessBanner(`Context item "${updated.title}" updated successfully (now v${updated.version}).`);
      fetchItems();
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        if (err.code === 'STALE_VERSION_CONFLICT') {
          const rawDetails = err.details as Record<string, unknown> | undefined;
          setConflictDetails({
            expected: Number(rawDetails?.expected_version || editingItem.version),
            current: Number(rawDetails?.current_version || editingItem.version + 1),
          });
          setEditError('Stale version conflict: this context item was modified by another session. Please reload the latest version to review changes before overwriting.');
        } else {
          setEditError(err.message);
        }
      } else {
        setEditError('Failed to update context item.');
      }
    } finally {
      setIsSubmittingEdit(false);
    }
  };

  // Reload latest version on conflict
  const reloadLatestVersion = async () => {
    if (!editingItem) return;
    try {
      const fresh = await api.getContextItem(editingItem.id);
      setEditingItem(fresh);
      setEditTitle(fresh.title);
      setEditType(fresh.item_type);
      setEditContent(fresh.content);
      setEditIsActive(fresh.is_active);
      setConflictDetails(null);
      setEditError(null);
      setSuccessBanner(`Reloaded latest version v${fresh.version}. You may now apply your edits safely.`);
    } catch {
      setEditError('Failed to reload latest item from database.');
    }
  };

  // Quick Toggle Active State
  const handleToggleActive = async (item: ContextItem) => {
    try {
      const updated = await api.updateContextItem(item.id, {
        expected_version: item.version,
        is_active: !item.is_active,
      });
      setSuccessBanner(`Status updated: "${updated.title}" is now ${updated.is_active ? 'active' : 'inactive'}.`);
      fetchItems();
    } catch (err: unknown) {
      if (err instanceof ApiClientError && err.code === 'STALE_VERSION_CONFLICT') {
        setListError(`Conflict updating "${item.title}": Item was modified in another session. Please refresh the list.`);
      } else {
        setListError(`Failed to update status for "${item.title}".`);
      }
    }
  };

  // Delete Confirm & Execute
  const handleDeleteExecute = async () => {
    if (!deletingItem) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteContextItem(deletingItem.id);
      setSuccessBanner(`Context item "${deletingItem.title}" deleted.`);
      setDeletingItem(null);
      fetchItems();
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setDeleteError(err.message);
      } else {
        setDeleteError('Failed to delete context item.');
      }
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-surface-200 pb-4">
        <div>
          <h1 className="text-xl font-bold text-surface-900 tracking-tight flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-emerald-700" />
            Merchant Context Management
          </h1>
          <p className="text-xs text-surface-800 mt-1">
            Configure store policies, FAQs, operating rules, and facts used by the AI copilot for grounded customer responses.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsCreateOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded bg-emerald-700 text-white hover:bg-emerald-800 shadow-sm transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Context Item
          </button>
        </div>
      </div>

      {/* Success Notification Banner */}
      {successBanner && (
        <div className="p-3 rounded bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{successBanner}</span>
          </div>
          <button
            onClick={() => setSuccessBanner(null)}
            className="text-emerald-700 hover:text-emerald-900 p-1"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Global Error Banner */}
      {listError && (
        <div className="p-3 rounded bg-red-50 border border-red-200 text-xs text-red-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
            <span>{listError}</span>
          </div>
          <button
            onClick={fetchItems}
            className="underline font-medium hover:text-red-900"
          >
            Retry
          </button>
        </div>
      )}

      {/* Filter & Search Bar */}
      <div className="bg-white border border-surface-200 rounded p-4 shadow-sm flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 text-xs">
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Type Filter */}
          <div className="flex items-center gap-1.5">
            <span className="text-surface-800 font-medium text-[11px]">Type:</span>
            <select
              value={selectedType}
              onChange={(e) => {
                setSelectedType(e.target.value);
                setPage(1);
              }}
              className="px-2.5 py-1.5 rounded border border-surface-300 bg-white text-surface-900 focus:outline-none focus:ring-1 focus:ring-emerald-700"
            >
              <option value="all">All Types</option>
              {APPROVED_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>

          {/* Status Filter */}
          <div className="flex items-center gap-1.5">
            <span className="text-surface-800 font-medium text-[11px]">Status:</span>
            <select
              value={selectedStatus}
              onChange={(e) => {
                setSelectedStatus(e.target.value);
                setPage(1);
              }}
              className="px-2.5 py-1.5 rounded border border-surface-300 bg-white text-surface-900 focus:outline-none focus:ring-1 focus:ring-emerald-700"
            >
              <option value="all">All Statuses</option>
              <option value="active">Active Only</option>
              <option value="inactive">Inactive Only</option>
            </select>
          </div>

          {/* Reset Filters */}
          {(selectedType !== 'all' || selectedStatus !== 'all') && (
            <button
              onClick={() => {
                setSelectedType('all');
                setSelectedStatus('all');
                setPage(1);
              }}
              className="text-xs text-emerald-800 hover:underline px-2 py-1 font-medium"
            >
              Reset Filters
            </button>
          )}
        </div>

        {/* Search Input & Refresh Button */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1 md:w-64">
            <Search className="w-3.5 h-3.5 text-surface-800 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search title or content..."
              className="w-full pl-8 pr-3 py-1.5 rounded border border-surface-300 bg-white text-surface-900 placeholder-surface-800 focus:outline-none focus:ring-1 focus:ring-emerald-700 text-xs"
            />
          </div>
          <button
            onClick={fetchItems}
            disabled={isLoading}
            className="p-1.5 rounded border border-surface-300 bg-white text-surface-800 hover:text-emerald-700 hover:bg-surface-50 transition-colors"
            title="Refresh items"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Context Items Table / List */}
      <div className="bg-white border border-surface-200 rounded shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="py-12 text-center text-xs text-surface-800">
            Loading merchant context items...
          </div>
        ) : displayedItems.length === 0 ? (
          <div className="py-12 px-4 text-center">
            <Layers className="w-8 h-8 text-surface-800 mx-auto mb-2" />
            <p className="text-xs font-semibold text-surface-900">No context items found</p>
            <p className="text-[11px] text-surface-800 max-w-sm mx-auto mt-1 mb-4">
              {searchQuery || selectedType !== 'all' || selectedStatus !== 'all'
                ? 'No items match your active search or filter criteria.'
                : 'Start configuring store policies and FAQs so your AI copilot can deliver accurate answers.'}
            </p>
            <button
              onClick={() => setIsCreateOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded bg-emerald-700 text-white hover:bg-emerald-800 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              Add Context Item
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-surface-200 bg-surface-50 text-[11px] font-semibold text-surface-800 uppercase tracking-wider">
                  <th className="py-3 px-4">Title & Description</th>
                  <th className="py-3 px-4 w-32">Type</th>
                  <th className="py-3 px-4 w-24">Version</th>
                  <th className="py-3 px-4 w-28">Status</th>
                  <th className="py-3 px-4 w-28 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-100">
                {displayedItems.map((item) => (
                  <tr key={item.id} className="hover:bg-surface-50/60 transition-colors">
                    <td className="py-3.5 px-4 align-top">
                      <div className="font-semibold text-surface-900 text-xs">{item.title}</div>
                      <p className="text-[11px] text-surface-800 line-clamp-2 mt-1 leading-relaxed">
                        {item.content}
                      </p>
                      <div className="flex items-center gap-3 text-[10px] text-surface-800 mt-2">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3 text-surface-800" />
                          Updated: {new Date(item.updated_at).toLocaleDateString()}
                        </span>
                      </div>
                    </td>
                    <td className="py-3.5 px-4 align-top">
                      <span className={`inline-block text-[10px] uppercase font-medium px-2 py-0.5 rounded border ${getTypeBadgeClass(item.item_type)}`}>
                        {item.item_type.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 align-top font-mono text-xs text-surface-800">
                      v{item.version}
                    </td>
                    <td className="py-3.5 px-4 align-top">
                      <button
                        onClick={() => handleToggleActive(item)}
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium border transition-colors ${
                          item.is_active
                            ? 'bg-emerald-50 text-emerald-800 border-emerald-200 hover:bg-emerald-100'
                            : 'bg-slate-100 text-slate-700 border-slate-200 hover:bg-slate-200'
                        }`}
                        title="Click to toggle active state"
                      >
                        {item.is_active ? (
                          <>
                            <Check className="w-3 h-3 text-emerald-600" />
                            <span>Active</span>
                          </>
                        ) : (
                          <span>Inactive</span>
                        )}
                      </button>
                    </td>
                    <td className="py-3.5 px-4 align-top text-right">
                      <div className="inline-flex items-center gap-1.5">
                        <button
                          onClick={() => openEditModal(item)}
                          className="p-1.5 rounded border border-surface-200 hover:border-surface-300 bg-white hover:bg-surface-50 text-surface-800 hover:text-emerald-700 transition-colors"
                          title="Edit context item"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => setDeletingItem(item)}
                          className="p-1.5 rounded border border-surface-200 hover:border-red-300 bg-white hover:bg-red-50 text-surface-800 hover:text-red-700 transition-colors"
                          title="Delete context item"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Footer with pagination stats */}
        <div className="p-3 border-t border-surface-200 bg-surface-50 flex items-center justify-between text-xs text-surface-800">
          <div>
            Showing {displayedItems.length} of {total} context item{total === 1 ? '' : 's'}
          </div>
          {total > pageSize && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-2 py-1 rounded border border-surface-300 bg-white disabled:opacity-50 text-xs font-medium"
              >
                Previous
              </button>
              <span>Page {page}</span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page * pageSize >= total}
                className="px-2 py-1 rounded border border-surface-300 bg-white disabled:opacity-50 text-xs font-medium"
              >
                Next
              </button>
            </div>
          )}
        </div>
      </div>

      {/* CREATE MODAL */}
      {isCreateOpen && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-surface-200 rounded max-w-lg w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-surface-100 pb-3">
              <h2 className="text-sm font-semibold text-surface-900 flex items-center gap-2">
                <Plus className="w-4 h-4 text-emerald-700" />
                Add Merchant Context Item
              </h2>
              <button
                onClick={() => setIsCreateOpen(false)}
                className="text-surface-800 hover:text-surface-900 p-1"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {createError && (
              <div className="p-3 rounded bg-red-50 border border-red-200 text-xs text-red-800 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
                <span>{createError}</span>
              </div>
            )}

            <form onSubmit={handleCreateSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block font-medium text-surface-900 mb-1">
                  Title <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={createTitle}
                  onChange={(e) => setCreateTitle(e.target.value)}
                  placeholder="e.g. Return & Exchange Window"
                  className="w-full px-3 py-1.5 rounded border border-surface-300 bg-white text-surface-900 focus:outline-none focus:ring-1 focus:ring-emerald-700"
                  maxLength={200}
                />
              </div>

              <div>
                <label className="block font-medium text-surface-900 mb-1">
                  Context Item Type <span className="text-red-500">*</span>
                </label>
                <select
                  value={createType}
                  onChange={(e) => setCreateType(e.target.value as ContextItemType)}
                  className="w-full px-2.5 py-1.5 rounded border border-surface-300 bg-white text-surface-900 focus:outline-none focus:ring-1 focus:ring-emerald-700"
                >
                  {APPROVED_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label} ({t.value})
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-surface-800 mt-1">
                  {APPROVED_TYPES.find((t) => t.value === createType)?.description}
                </p>
              </div>

              <div>
                <label className="block font-medium text-surface-900 mb-1">
                  Content / Instructions <span className="text-red-500">*</span>
                </label>
                <textarea
                  rows={5}
                  required
                  value={createContent}
                  onChange={(e) => setCreateContent(e.target.value)}
                  placeholder="Detailed store facts, conditions, exceptions, or customer instructions..."
                  className="w-full px-3 py-1.5 rounded border border-surface-300 bg-white text-surface-900 focus:outline-none focus:ring-1 focus:ring-emerald-700 leading-relaxed"
                />
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  id="create-active-check"
                  type="checkbox"
                  checked={createIsActive}
                  onChange={(e) => setCreateIsActive(e.target.checked)}
                  className="w-4 h-4 rounded text-emerald-700 border-surface-300 focus:ring-emerald-700"
                />
                <label htmlFor="create-active-check" className="font-medium text-surface-900 cursor-pointer">
                  Activate immediately for AI prompt grounding
                </label>
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-surface-100">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  disabled={isSubmittingCreate}
                  className="px-3 py-1.5 rounded border border-surface-300 bg-white hover:bg-surface-50 font-medium text-surface-900"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmittingCreate}
                  className="px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-800 text-white font-medium disabled:opacity-60 shadow-sm transition-colors flex items-center gap-1.5"
                >
                  <Save className="w-3.5 h-3.5" />
                  {isSubmittingCreate ? 'Saving...' : 'Save Context Item'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EDIT MODAL WITH OPTIMISTIC CONCURRENCY CONFLICT RESOLUTION */}
      {editingItem && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-surface-200 rounded max-w-lg w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-surface-100 pb-3">
              <div className="flex items-center gap-2">
                <Edit2 className="w-4 h-4 text-emerald-700" />
                <h2 className="text-sm font-semibold text-surface-900">
                  Edit Context Item (v{editingItem.version})
                </h2>
              </div>
              <button
                onClick={() => setEditingItem(null)}
                className="text-surface-800 hover:text-surface-900 p-1"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Prominent Stale Version Conflict Banner */}
            {conflictDetails && (
              <div className="p-3.5 rounded bg-amber-50 border border-amber-300 text-xs text-amber-900 space-y-2">
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-700 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold text-amber-900">Optimistic Concurrency Conflict Detected</span>
                    <p className="mt-0.5 text-amber-800 text-[11px] leading-relaxed">
                      This item was modified by another session (database version is now <strong>v{conflictDetails.current}</strong>, but your edits were based on <strong>v{conflictDetails.expected}</strong>).
                    </p>
                  </div>
                </div>
                <div className="pt-2 border-t border-amber-200 flex justify-end">
                  <button
                    type="button"
                    onClick={reloadLatestVersion}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-amber-700 hover:bg-amber-800 text-white font-medium text-xs shadow-sm"
                  >
                    <RefreshCw className="w-3 h-3" />
                    Reload Latest Version (v{conflictDetails.current})
                  </button>
                </div>
              </div>
            )}

            {editError && !conflictDetails && (
              <div className="p-3 rounded bg-red-50 border border-red-200 text-xs text-red-800 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
                <span>{editError}</span>
              </div>
            )}

            <form onSubmit={handleEditSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block font-medium text-surface-900 mb-1">
                  Title <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  className="w-full px-3 py-1.5 rounded border border-surface-300 bg-white text-surface-900 focus:outline-none focus:ring-1 focus:ring-emerald-700"
                  maxLength={200}
                />
              </div>

              <div>
                <label className="block font-medium text-surface-900 mb-1">
                  Context Item Type <span className="text-red-500">*</span>
                </label>
                <select
                  value={editType}
                  onChange={(e) => setEditType(e.target.value as ContextItemType)}
                  className="w-full px-2.5 py-1.5 rounded border border-surface-300 bg-white text-surface-900 focus:outline-none focus:ring-1 focus:ring-emerald-700"
                >
                  {APPROVED_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label} ({t.value})
                    </option>
                  ))}
                </select>
                <p className="text-[11px] text-surface-800 mt-1">
                  {APPROVED_TYPES.find((t) => t.value === editType)?.description}
                </p>
              </div>

              <div>
                <label className="block font-medium text-surface-900 mb-1">
                  Content / Instructions <span className="text-red-500">*</span>
                </label>
                <textarea
                  rows={5}
                  required
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  className="w-full px-3 py-1.5 rounded border border-surface-300 bg-white text-surface-900 focus:outline-none focus:ring-1 focus:ring-emerald-700 leading-relaxed"
                />
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  id="edit-active-check"
                  type="checkbox"
                  checked={editIsActive}
                  onChange={(e) => setEditIsActive(e.target.checked)}
                  className="w-4 h-4 rounded text-emerald-700 border-surface-300 focus:ring-emerald-700"
                />
                <label htmlFor="edit-active-check" className="font-medium text-surface-900 cursor-pointer">
                  Item is active for prompt grounding
                </label>
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-surface-100">
                <span className="text-[11px] text-surface-800">
                  Target Version: <strong>v{editingItem.version}</strong>
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setEditingItem(null)}
                    disabled={isSubmittingEdit}
                    className="px-3 py-1.5 rounded border border-surface-300 bg-white hover:bg-surface-50 font-medium text-surface-900"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmittingEdit || !!conflictDetails}
                    className="px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-800 text-white font-medium disabled:opacity-60 shadow-sm transition-colors flex items-center gap-1.5"
                  >
                    <Save className="w-3.5 h-3.5" />
                    {isSubmittingEdit ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* DELETE CONFIRMATION MODAL */}
      {deletingItem && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-surface-200 rounded max-w-md w-full p-6 shadow-xl space-y-4 text-xs">
            <div className="flex items-center gap-2 text-red-700 font-semibold text-sm">
              <AlertTriangle className="w-5 h-5 text-red-600 shrink-0" />
              <span>Confirm Context Deletion</span>
            </div>

            <p className="text-surface-900 leading-relaxed">
              Are you sure you want to delete context item <strong>"{deletingItem.title}"</strong> (v{deletingItem.version})?
            </p>
            <p className="text-[11px] text-surface-800">
              This action cannot be undone. This information will be permanently removed from your merchant workspace and will no longer be retrieved during AI grounding.
            </p>

            {deleteError && (
              <div className="p-2.5 rounded bg-red-50 border border-red-200 text-red-800 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
                <span>{deleteError}</span>
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-surface-100">
              <button
                type="button"
                onClick={() => setDeletingItem(null)}
                disabled={isDeleting}
                className="px-3 py-1.5 rounded border border-surface-300 bg-white hover:bg-surface-50 font-medium text-surface-900"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteExecute}
                disabled={isDeleting}
                className="px-3 py-1.5 rounded bg-red-700 hover:bg-red-800 text-white font-medium disabled:opacity-60 shadow-sm transition-colors flex items-center gap-1.5"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {isDeleting ? 'Deleting...' : 'Delete Context Item'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
