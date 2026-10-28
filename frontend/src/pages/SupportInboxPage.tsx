import React, { useState, useEffect, useCallback } from 'react';
import {
  LifeBuoy,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Clock,
  Send,
  Save,
  Sparkles,
  AlertTriangle,
  Loader2,
  User,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
} from 'lucide-react';
import { api, ApiClientError } from '../api/client';
import {
  CustomerSupportMessage,
  CustomerSupportStatus,
} from '../types/api';

export const SupportInboxPage: React.FC = () => {
  const [messages, setMessages] = useState<CustomerSupportMessage[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 10;

  const [statusFilter, setStatusFilter] = useState<'all' | CustomerSupportStatus>('needs_review');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Inflight action tracking (prevents duplicate clicks)
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<{ id: string; message: string } | null>(null);
  const [successNotice, setSuccessNotice] = useState<string | null>(null);

  // Per-item local draft text edits
  const [draftEdits, setDraftEdits] = useState<Record<string, string>>({});

  const fetchMessages = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.listSupportMessages({
        status: statusFilter === 'all' ? undefined : statusFilter,
        page,
        page_size: pageSize,
      });
      setMessages(res.items);
      setTotal(res.total);
      // Initialize local draft state for items not already modified
      setDraftEdits((prev) => {
        const next = { ...prev };
        res.items.forEach((m) => {
          if (next[m.id] === undefined) {
            next[m.id] = m.suggested_reply || '';
          }
        });
        return next;
      });
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError('Failed to load support inbox. Please check your connection.');
      }
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter, page]);

  useEffect(() => {
    fetchMessages();
  }, [fetchMessages]);

  const handleDraftChange = (id: string, text: string) => {
    setDraftEdits((prev) => ({ ...prev, [id]: text }));
  };

  const handleSaveDraft = async (message: CustomerSupportMessage) => {
    if (processingId) return;
    const text = (draftEdits[message.id] !== undefined ? draftEdits[message.id] : (message.suggested_reply || '')).trim();
    if (!text) {
      setActionError({ id: message.id, message: 'Draft reply cannot be empty.' });
      return;
    }

    setProcessingId(message.id);
    setActionError(null);
    setSuccessNotice(null);

    try {
      const updated = await api.editSupportSuggestedReply(message.id, text);
      setSuccessNotice('Draft proposal updated and saved. Reply has NOT been delivered.');
      setMessages((prev) =>
        prev.map((item) => (item.id === updated.id ? updated : item))
      );
      setDraftEdits((prev) => ({ ...prev, [updated.id]: updated.suggested_reply || '' }));
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setActionError({ id: message.id, message: err.message });
      } else {
        setActionError({ id: message.id, message: 'Failed to save draft proposal.' });
      }
    } finally {
      setProcessingId(null);
    }
  };

  const handleDeliver = async (message: CustomerSupportMessage) => {
    if (processingId) return;
    const text = (draftEdits[message.id] !== undefined ? draftEdits[message.id] : (message.suggested_reply || '')).trim();
    if (!text) {
      setActionError({ id: message.id, message: 'Please enter or confirm a reply before delivering.' });
      return;
    }

    setProcessingId(message.id);
    setActionError(null);
    setSuccessNotice(null);

    try {
      const updated = await api.deliverSupportReply(message.id, text);
      setSuccessNotice('Reply approved and delivered to the customer session.');
      setMessages((prev) =>
        prev.map((item) => (item.id === updated.id ? updated : item))
      );
      // Re-fetch to reconcile pagination if filtering
      if (statusFilter === 'needs_review') {
        fetchMessages();
      }
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        if (err.statusCode === 409) {
          setActionError({
            id: message.id,
            message: 'Conflict: This message was already delivered or updated by another session.',
          });
          fetchMessages();
        } else {
          setActionError({ id: message.id, message: err.message });
        }
      } else {
        setActionError({ id: message.id, message: 'Delivery failed. Please try again.' });
      }
    } finally {
      setProcessingId(null);
    }
  };

  const handleDismiss = async (message: CustomerSupportMessage) => {
    if (processingId) return;
    setProcessingId(message.id);
    setActionError(null);
    setSuccessNotice(null);

    try {
      const updated = await api.dismissSupportMessage(message.id);
      setSuccessNotice('Customer inquiry dismissed.');
      setMessages((prev) =>
        prev.map((item) => (item.id === updated.id ? updated : item))
      );
      if (statusFilter === 'needs_review') {
        fetchMessages();
      }
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setActionError({ id: message.id, message: err.message });
      } else {
        setActionError({ id: message.id, message: 'Failed to dismiss inquiry.' });
      }
    } finally {
      setProcessingId(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="space-y-6">
      {/* Top Banner / Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-surface-200 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold tracking-tight text-surface-900 flex items-center gap-2">
              <LifeBuoy className="w-5 h-5 text-emerald-700" />
              Customer Support Inbox
            </h1>
            <span className="text-xs bg-emerald-100 text-emerald-800 border border-emerald-300 px-2 py-0.5 rounded font-medium">
              Human-in-the-Loop
            </span>
          </div>
          <p className="text-xs text-surface-800 mt-1">
            Review customer inquiries from your website support channel. Review, edit, and approve AI draft suggestions before delivery.
          </p>
        </div>

        <button
          onClick={fetchMessages}
          disabled={isLoading || Boolean(processingId)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded border border-surface-300 bg-white text-surface-800 hover:bg-surface-50 hover:text-surface-900 disabled:opacity-50 transition-colors self-start sm:self-auto shadow-sm"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-emerald-700' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Global Notices */}
      {successNotice && (
        <div className="flex items-center gap-2 p-3 bg-emerald-50 border border-emerald-200 text-emerald-900 text-xs rounded-md shadow-sm">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <span className="flex-1 font-medium">{successNotice}</span>
          <button
            onClick={() => setSuccessNotice(null)}
            className="text-emerald-700 hover:text-emerald-900 text-xs font-bold px-1"
          >
            &times;
          </button>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 p-3 bg-rose-50 border border-rose-200 text-rose-900 text-xs rounded-md shadow-sm">
          <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
          <span className="flex-1">{error}</span>
          <button
            onClick={() => setError(null)}
            className="text-rose-700 hover:text-rose-900 text-xs font-bold px-1"
          >
            &times;
          </button>
        </div>
      )}

      {/* Filter Tabs */}
      <div className="flex items-center justify-between border-b border-surface-200 gap-4">
        <div className="flex space-x-1">
          {(
            [
              { id: 'needs_review', label: 'Needs Review' },
              { id: 'delivered', label: 'Delivered' },
              { id: 'dismissed', label: 'Dismissed' },
              { id: 'all', label: 'All Inquiries' },
            ] as const
          ).map((tab) => {
            const isActive = statusFilter === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => {
                  setStatusFilter(tab.id);
                  setPage(1);
                }}
                className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
                  isActive
                    ? 'border-emerald-700 text-emerald-800'
                    : 'border-transparent text-surface-800 hover:text-surface-900 hover:border-surface-300'
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>

        <div className="text-xs text-surface-800 font-medium">
          {total} {total === 1 ? 'inquiry' : 'inquiries'} total
        </div>
      </div>

      {/* Main Inbox Cards */}
      {isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((n) => (
            <div
              key={n}
              className="bg-white border border-surface-200 rounded-lg p-5 shadow-sm space-y-3 animate-pulse"
            >
              <div className="flex items-center justify-between">
                <div className="h-4 bg-surface-200 rounded w-1/4"></div>
                <div className="h-4 bg-surface-200 rounded w-20"></div>
              </div>
              <div className="h-14 bg-surface-100 rounded w-full"></div>
              <div className="h-20 bg-surface-50 rounded w-full"></div>
            </div>
          ))}
        </div>
      ) : messages.length === 0 ? (
        <div className="text-center py-12 bg-white border border-surface-200 rounded-lg shadow-sm">
          <LifeBuoy className="w-10 h-10 text-surface-400 mx-auto mb-3" />
          <h3 className="text-sm font-semibold text-surface-900">No inquiries found</h3>
          <p className="text-xs text-surface-800 mt-1 max-w-sm mx-auto">
            {statusFilter === 'needs_review'
              ? 'Your review queue is clear! Inquiries from customer web chat will appear here for review.'
              : `No inquiries match the "${statusFilter}" filter.`}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {messages.map((item) => {
            const isProcessing = processingId === item.id;
            const currentDraft =
              draftEdits[item.id] !== undefined
                ? draftEdits[item.id]
                : item.suggested_reply || '';
            const isModified =
              item.status === 'needs_review' &&
              currentDraft !== (item.suggested_reply || '');

            return (
              <div
                key={item.id}
                className="bg-white border border-surface-200 rounded-lg shadow-sm hover:border-surface-300 transition-colors overflow-hidden"
              >
                {/* Header info */}
                <div className="px-5 py-3.5 bg-surface-50/60 border-b border-surface-200 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-full bg-surface-200 flex items-center justify-center text-surface-700">
                      <User className="w-3.5 h-3.5" />
                    </div>
                    <span className="text-xs font-semibold text-surface-900">
                      {item.customer_name || 'Anonymous Customer'}
                    </span>
                    <span className="text-[11px] text-surface-800">
                      &bull; {new Date(item.created_at).toLocaleString()}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    {/* Status Pill */}
                    {item.status === 'needs_review' && (
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200">
                        <Clock className="w-3 h-3" />
                        Needs Review
                      </span>
                    )}
                    {item.status === 'delivered' && (
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded bg-emerald-50 text-emerald-800 border border-emerald-200">
                        <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                        Delivered
                      </span>
                    )}
                    {item.status === 'dismissed' && (
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded bg-surface-100 text-surface-800 border border-surface-200">
                        <XCircle className="w-3 h-3 text-surface-500" />
                        Dismissed
                      </span>
                    )}
                  </div>
                </div>

                {/* Card Body */}
                <div className="p-5 space-y-4">
                  {/* Customer Question */}
                  <div>
                    <label className="text-[11px] font-semibold text-surface-800 uppercase tracking-wider block mb-1.5">
                      Customer Inquiry
                    </label>
                    <div className="p-3 bg-surface-50 border border-surface-200 rounded text-xs text-surface-900 whitespace-pre-wrap leading-relaxed">
                      {item.customer_text}
                    </div>
                  </div>

                  {/* Per-Card Error Banner */}
                  {actionError?.id === item.id && (
                    <div className="p-2.5 bg-rose-50 border border-rose-200 text-rose-900 text-xs rounded flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
                      <span>{actionError.message}</span>
                    </div>
                  )}

                  {/* Review / Delivered Section */}
                  {item.status === 'needs_review' ? (
                    <div className="space-y-3 pt-2 border-t border-surface-100">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <label className="text-[11px] font-semibold text-surface-800 uppercase tracking-wider">
                            Proposed Reply
                          </label>

                          {/* AI Status Indicators */}
                          {item.ai_status === 'completed' && (
                            <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded">
                              <Sparkles className="w-2.5 h-2.5 text-emerald-600" />
                              AI Draft Proposal
                            </span>
                          )}

                          {item.ai_status === 'failed' && (
                            <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 bg-rose-50 text-rose-800 border border-rose-200 rounded">
                              <AlertTriangle className="w-2.5 h-2.5 text-rose-600" />
                              Manual Compose Required
                            </span>
                          )}

                          {item.ai_status === 'pending' && (
                            <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 bg-surface-100 text-surface-800 border border-surface-200 rounded">
                              <Loader2 className="w-2.5 h-2.5 animate-spin" />
                              Generating Draft...
                            </span>
                          )}

                          {isModified && (
                            <span className="text-[10px] font-medium px-1.5 py-0.5 bg-amber-50 text-amber-800 border border-amber-200 rounded">
                              ✎ Edited by Merchant
                            </span>
                          )}
                        </div>

                        <span className="text-[11px] text-surface-800">
                          {currentDraft.length}/4096
                        </span>
                      </div>

                      {item.ai_status === 'failed' && (
                        <div className="p-2.5 bg-amber-50 border border-amber-200 rounded text-xs text-amber-900 flex items-start gap-2">
                          <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                          <div className="text-[11px]">
                            AI draft generation could not complete for this inquiry. Please compose your reply manually below. The customer inquiry has been safely preserved.
                          </div>
                        </div>
                      )}

                      <textarea
                        value={currentDraft}
                        onChange={(e) => handleDraftChange(item.id, e.target.value)}
                        disabled={isProcessing}
                        placeholder="Type your response to the customer..."
                        rows={3}
                        className="w-full text-xs p-3 rounded border border-surface-300 focus:outline-none focus:ring-1 focus:ring-emerald-600 focus:border-emerald-600 text-surface-900 leading-relaxed font-normal resize-y disabled:opacity-50"
                      />

                      {/* Action buttons */}
                      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                        <div className="flex items-center gap-1.5 text-[11px] text-surface-800">
                          <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                          <span>Customer sees reply only after explicit delivery</span>
                        </div>

                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => handleDismiss(item)}
                            disabled={isProcessing}
                            className="px-2.5 py-1.5 text-xs font-medium text-surface-800 hover:text-surface-900 hover:bg-surface-100 rounded border border-surface-300 transition-colors disabled:opacity-50"
                          >
                            Dismiss
                          </button>

                          <button
                            type="button"
                            onClick={() => handleSaveDraft(item)}
                            disabled={isProcessing || !currentDraft.trim()}
                            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-surface-800 bg-white hover:bg-surface-50 rounded border border-surface-300 transition-colors disabled:opacity-50 shadow-sm"
                          >
                            <Save className="w-3 h-3 text-surface-600" />
                            <span>Save Draft</span>
                          </button>

                          <button
                            type="button"
                            onClick={() => handleDeliver(item)}
                            disabled={isProcessing || !currentDraft.trim()}
                            className="inline-flex items-center gap-1 px-3.5 py-1.5 text-xs font-medium text-white bg-emerald-700 hover:bg-emerald-800 rounded transition-colors disabled:opacity-50 shadow-sm"
                          >
                            {isProcessing ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              <Send className="w-3 h-3" />
                            )}
                            <span>Approve & Deliver</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : item.status === 'delivered' ? (
                    <div className="pt-2 border-t border-surface-100 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-semibold text-emerald-900 uppercase tracking-wider flex items-center gap-1.5">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                          Approved & Delivered Reply
                        </span>
                        {item.delivered_at && (
                          <span className="text-[11px] text-surface-800">
                            Delivered at {new Date(item.delivered_at).toLocaleString()}
                          </span>
                        )}
                      </div>
                      <div className="p-3 bg-emerald-50/50 border border-emerald-200 rounded text-xs text-emerald-950 whitespace-pre-wrap leading-relaxed">
                        {item.approved_reply}
                      </div>
                    </div>
                  ) : (
                    <div className="pt-2 border-t border-surface-100 text-xs text-surface-800 italic">
                      Inquiry was dismissed on {item.reviewed_at ? new Date(item.reviewed_at).toLocaleString() : 'earlier date'}.
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-4 border-t border-surface-200 text-xs text-surface-800">
          <div>
            Showing Page {page} of {totalPages} ({total} inquiries)
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1 || isLoading}
              className="px-2.5 py-1 border border-surface-300 rounded bg-white hover:bg-surface-50 disabled:opacity-40 transition-colors flex items-center gap-1"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              <span>Previous</span>
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages || isLoading}
              className="px-2.5 py-1 border border-surface-300 rounded bg-white hover:bg-surface-50 disabled:opacity-40 transition-colors flex items-center gap-1"
            >
              <span>Next</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default SupportInboxPage;
