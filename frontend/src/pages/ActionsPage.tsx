import React, { useState, useEffect, useCallback } from 'react';
import {
  CheckSquare,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Clock,
  MessageSquare,
  ShieldAlert,
  ChevronDown,
  ChevronRight,
  Code2,
  Loader2,
} from 'lucide-react';
import { api, ApiClientError } from '../api/client';
import { SuggestedAction, ActionStatus, ActionType } from '../types/api';

export const ActionsPage: React.FC = () => {
  const [actions, setActions] = useState<SuggestedAction[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 15;

  const [statusFilter, setStatusFilter] = useState<'all' | ActionStatus>('pending');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Inflight action transition tracking
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<{ id: string; message: string } | null>(null);
  const [successNotice, setSuccessNotice] = useState<string | null>(null);

  // Expandable payload toggle map
  const [expandedPayloads, setExpandedPayloads] = useState<Record<string, boolean>>({});

  const fetchActions = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.listActions({
        status: statusFilter === 'all' ? undefined : statusFilter,
        page,
        page_size: pageSize,
      });
      setActions(res.items);
      setTotal(res.total);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError('Failed to load review queue. Please verify your connection.');
      }
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter, page]);

  useEffect(() => {
    fetchActions();
  }, [fetchActions]);

  const handleApprove = async (action: SuggestedAction) => {
    if (processingId) return; // Prevent concurrent submissions
    setProcessingId(action.id);
    setActionError(null);
    setSuccessNotice(null);

    try {
      const updated = await api.approveAction(action.id);
      setSuccessNotice(`Action "${action.title}" approved. Decision recorded in database.`);
      // Update local state and refresh
      setActions((prev) =>
        prev.map((item) => (item.id === updated.id ? updated : item))
      );
      // If filtering by pending, re-fetch to update pagination counts
      if (statusFilter === 'pending') {
        fetchActions();
      }
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setActionError({ id: action.id, message: err.message });
      } else {
        setActionError({ id: action.id, message: 'Failed to record approval decision.' });
      }
    } finally {
      setProcessingId(null);
    }
  };

  const handleDismiss = async (action: SuggestedAction) => {
    if (processingId) return; // Prevent concurrent submissions
    setProcessingId(action.id);
    setActionError(null);
    setSuccessNotice(null);

    try {
      const updated = await api.dismissAction(action.id);
      setSuccessNotice(`Action "${action.title}" dismissed. Decision recorded in database.`);
      setActions((prev) =>
        prev.map((item) => (item.id === updated.id ? updated : item))
      );
      if (statusFilter === 'pending') {
        fetchActions();
      }
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setActionError({ id: action.id, message: err.message });
      } else {
        setActionError({ id: action.id, message: 'Failed to record dismissal decision.' });
      }
    } finally {
      setProcessingId(null);
    }
  };

  const togglePayload = (id: string) => {
    setExpandedPayloads((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  const getActionTypeBadgeClass = (type: ActionType) => {
    switch (type) {
      case 'reply_draft':
        return 'bg-amber-50 text-amber-800 border-amber-200';
      case 'recommendation':
        return 'bg-emerald-50 text-emerald-800 border-emerald-200';
      case 'summary':
        return 'bg-blue-50 text-blue-800 border-blue-200';
      case 'follow_up':
        return 'bg-indigo-50 text-indigo-800 border-indigo-200';
      default:
        return 'bg-slate-50 text-slate-800 border-slate-200';
    }
  };

  const getStatusBadgeClass = (status: ActionStatus) => {
    switch (status) {
      case 'pending':
        return 'bg-amber-50 text-amber-800 border-amber-200';
      case 'approved':
        return 'bg-emerald-50 text-emerald-800 border-emerald-200';
      case 'dismissed':
        return 'bg-slate-100 text-slate-700 border-slate-300';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-300';
    }
  };

  const totalPages = Math.ceil(total / pageSize) || 1;

  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold text-surface-900 tracking-tight flex items-center gap-2">
            <CheckSquare className="w-5 h-5 text-emerald-700" />
            <span>Drafts & Suggested Actions Review Queue</span>
          </h1>
          <p className="text-xs text-surface-800 mt-1">
            Review and govern customer reply drafts, insights, and suggestions proposed by the AI assistant.
          </p>
        </div>

        <button
          onClick={fetchActions}
          disabled={isLoading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-surface-800 hover:text-surface-900 bg-white border border-surface-200 hover:bg-surface-50 rounded shadow-xs transition-colors self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-emerald-700' : ''}`} />
          <span>Refresh Queue</span>
        </button>
      </div>

      {/* Human-in-the-Loop Safeguard Notice */}
      <div className="bg-surface-50 border border-surface-200 rounded p-4 text-xs text-surface-900 flex items-start gap-3 shadow-2xs">
        <ShieldAlert className="w-5 h-5 text-emerald-700 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <p className="font-semibold text-surface-900">
            Human-in-the-Loop Safeguard: Approvals are Decisions, Not External Automations
          </p>
          <p className="text-[11px] text-surface-800 leading-relaxed">
            The AI assistant generates proposals and suggested reply drafts based on your store's context. 
            Approving an item records your decision in the database. <strong>Approval does NOT send external WhatsApp messages, SMS, emails, or execute financial transactions.</strong>
          </p>
        </div>
      </div>

      {/* Filters & Status Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-surface-200 pb-3">
        <div className="flex rounded border border-surface-200 bg-surface-100 p-0.5 text-xs">
          {(['pending', 'approved', 'dismissed', 'all'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => {
                setStatusFilter(tab);
                setPage(1);
              }}
              className={`px-3 py-1 font-medium capitalize rounded transition-colors ${
                statusFilter === tab
                  ? 'bg-white text-surface-900 shadow-xs'
                  : 'text-surface-800 hover:text-surface-900'
              }`}
            >
              {tab === 'all' ? 'All Items' : tab}
            </button>
          ))}
        </div>

        <div className="text-xs text-surface-800 font-medium">
          Showing {actions.length} of {total} {statusFilter === 'all' ? 'total' : statusFilter} items
        </div>
      </div>

      {/* Global Success / Notice Banner */}
      {successNotice && (
        <div className="p-3 rounded bg-emerald-50 border border-emerald-200 text-xs text-emerald-900 flex items-center justify-between gap-2 shadow-2xs">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-700 shrink-0" />
            <span>{successNotice}</span>
          </div>
          <button
            onClick={() => setSuccessNotice(null)}
            className="text-emerald-800 hover:text-emerald-950 font-semibold text-[11px]"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main List Area */}
      {isLoading ? (
        <div className="bg-white border border-surface-200 rounded p-12 text-center text-xs text-surface-800 space-y-2">
          <Loader2 className="w-6 h-6 animate-spin mx-auto text-emerald-700" />
          <p>Loading suggested actions review queue...</p>
        </div>
      ) : error ? (
        <div className="bg-white border border-surface-200 rounded p-8 text-center space-y-3">
          <AlertCircle className="w-8 h-8 text-red-600 mx-auto" />
          <p className="text-xs text-red-800 font-semibold">{error}</p>
          <button
            onClick={fetchActions}
            className="text-xs font-medium text-emerald-800 underline hover:text-emerald-900"
          >
            Retry Loading Queue
          </button>
        </div>
      ) : actions.length === 0 ? (
        <div className="bg-white border border-dashed border-surface-200 rounded p-12 text-center space-y-3">
          <div className="w-10 h-10 rounded-full bg-surface-100 border border-surface-200 flex items-center justify-center mx-auto text-surface-800">
            <CheckSquare className="w-5 h-5" />
          </div>
          <h2 className="text-sm font-semibold text-surface-900">
            {statusFilter === 'pending'
              ? 'No Pending Actions for Review'
              : `No ${statusFilter} items found`}
          </h2>
          <p className="text-xs text-surface-800 max-w-sm mx-auto leading-relaxed">
            {statusFilter === 'pending'
              ? 'When the AI assistant flags a suggested customer reply draft, follow-up recommendation, or summary turn, it will appear here for your review and approval.'
              : 'There are no actions matching the selected filter criteria.'}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {actions.map((action) => {
            const isProcessing = processingId === action.id;
            const hasError = actionError?.id === action.id;
            const isExpanded = !!expandedPayloads[action.id];
            const hasPayload = action.payload && Object.keys(action.payload).length > 0;

            return (
              <div
                key={action.id}
                className="bg-white border border-surface-200 rounded shadow-xs overflow-hidden transition-shadow hover:shadow-sm"
              >
                {/* Action Card Header */}
                <div className="p-4 border-b border-surface-100 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded border tracking-wide ${getActionTypeBadgeClass(
                        action.action_type
                      )}`}
                    >
                      {action.action_type.replace('_', ' ')}
                    </span>

                    <h2 className="text-sm font-semibold text-surface-900">
                      {action.title}
                    </h2>

                    <span
                      className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded border ${getStatusBadgeClass(
                        action.status
                      )}`}
                    >
                      {action.status}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 text-[11px] text-surface-800 shrink-0">
                    <Clock className="w-3.5 h-3.5 text-surface-800" />
                    <span>
                      {new Date(action.created_at).toLocaleString([], {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>
                </div>

                {/* Card Body */}
                <div className="p-4 space-y-3">
                  <div className="text-xs text-surface-900 leading-relaxed whitespace-pre-wrap bg-surface-50/70 p-3.5 rounded border border-surface-100 font-sans">
                    {action.description}
                  </div>

                  {/* Metadata References */}
                  <div className="flex flex-wrap items-center gap-3 text-[11px] text-surface-800 pt-1">
                    <span>
                      Proposed by: <strong className="text-surface-900 font-medium">{action.created_by}</strong>
                    </span>

                    {action.conversation_id && (
                      <span className="flex items-center gap-1">
                        <MessageSquare className="w-3 h-3 text-surface-800" />
                        <span>Conversation:</span>
                        <code className="text-emerald-800 bg-surface-100 px-1 py-0.5 rounded font-mono text-[10px]">
                          {action.conversation_id.slice(0, 8)}...
                        </code>
                      </span>
                    )}

                    {action.reviewed_at && (
                      <span className="flex items-center gap-1 text-surface-800">
                        <CheckCircle2 className="w-3 h-3 text-emerald-700" />
                        <span>Reviewed: {new Date(action.reviewed_at).toLocaleDateString()}</span>
                      </span>
                    )}

                    {hasPayload && (
                      <button
                        onClick={() => togglePayload(action.id)}
                        className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-800 hover:text-emerald-950 underline ml-auto"
                      >
                        <Code2 className="w-3 h-3" />
                        <span>{isExpanded ? 'Hide Payload' : 'Inspect Payload'}</span>
                        {isExpanded ? (
                          <ChevronDown className="w-3 h-3" />
                        ) : (
                          <ChevronRight className="w-3 h-3" />
                        )}
                      </button>
                    )}
                  </div>

                  {/* Collapsible Payload Viewer */}
                  {isExpanded && hasPayload && (
                    <div className="mt-2 p-3 rounded bg-surface-900 text-surface-100 font-mono text-[11px] overflow-x-auto">
                      <pre>{JSON.stringify(action.payload, null, 2)}</pre>
                    </div>
                  )}

                  {/* Item-level Error Alert */}
                  {hasError && (
                    <div className="p-2.5 rounded bg-red-50 border border-red-200 text-xs text-red-800 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
                      <span>{actionError.message}</span>
                    </div>
                  )}
                </div>

                {/* Card Footer: Action Controls */}
                <div className="px-4 py-3 bg-surface-50 border-t border-surface-100 flex items-center justify-between">
                  <p className="text-[11px] text-surface-800">
                    {action.status === 'pending'
                      ? 'Action is awaiting merchant review.'
                      : `Decision recorded: ${action.status}.`}
                  </p>

                  <div className="flex items-center gap-2">
                    {action.status === 'pending' ? (
                      <>
                        <button
                          onClick={() => handleDismiss(action)}
                          disabled={isProcessing}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-surface-800 hover:text-surface-900 bg-white hover:bg-surface-100 border border-surface-300 disabled:opacity-50 rounded transition-colors shadow-2xs"
                          title="Dismiss this suggested action"
                        >
                          {isProcessing ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <XCircle className="w-3.5 h-3.5 text-surface-800" />
                          )}
                          <span>Dismiss</span>
                        </button>

                        <button
                          onClick={() => handleApprove(action)}
                          disabled={isProcessing}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-white bg-emerald-700 hover:bg-emerald-800 disabled:opacity-50 rounded transition-colors shadow-2xs"
                          title="Record merchant approval decision"
                        >
                          {isProcessing ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <CheckCircle2 className="w-3.5 h-3.5" />
                          )}
                          <span>Approve Suggestion</span>
                        </button>
                      </>
                    ) : (
                      <span className="text-xs font-semibold text-surface-800 bg-surface-200/60 px-2.5 py-1 rounded">
                        Decision Recorded ({action.status})
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-4 border-t border-surface-200 text-xs">
          <button
            onClick={() => setPage((p) => Math.max(p - 1, 1))}
            disabled={page === 1 || isLoading}
            className="px-3 py-1.5 font-medium text-surface-800 bg-white border border-surface-200 rounded disabled:opacity-40 hover:bg-surface-50 transition-colors shadow-2xs"
          >
            Previous
          </button>

          <span className="text-surface-800 font-medium">
            Page {page} of {totalPages}
          </span>

          <button
            onClick={() => setPage((p) => Math.min(p + 1, totalPages))}
            disabled={page === totalPages || isLoading}
            className="px-3 py-1.5 font-medium text-surface-800 bg-white border border-surface-200 rounded disabled:opacity-40 hover:bg-surface-50 transition-colors shadow-2xs"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};
