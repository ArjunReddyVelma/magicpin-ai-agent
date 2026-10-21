import React, { useEffect, useState, useCallback } from 'react';
import { HealthIndicator } from '../components/HealthIndicator';
import { MerchantProfileCard } from '../components/MerchantProfileCard';
import { useAuth } from '../context/AuthContext';
import { api, ApiClientError } from '../api/client';
import { ContextItem, Conversation } from '../types/api';
import {
  MessageSquare,
  Plus,
  FileText,
  AlertCircle,
  RefreshCw,
  ArrowRight,
  BookOpen,
  Cpu,
  CheckCircle2,
  Clock,
  Layers,
} from 'lucide-react';

interface DashboardPageProps {
  onNavigate: (tab: string, convId?: string) => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({ onNavigate }) => {
  const { merchant } = useAuth();

  // Context Items State
  const [contextItems, setContextItems] = useState<ContextItem[]>([]);
  const [totalContext, setTotalContext] = useState<number>(0);
  const [activeContextCount, setActiveContextCount] = useState<number>(0);
  const [isLoadingContext, setIsLoadingContext] = useState<boolean>(true);
  const [contextError, setContextError] = useState<string | null>(null);

  // Conversations State
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [totalConversations, setTotalConversations] = useState<number>(0);
  const [activeConversationsCount, setActiveConversationsCount] = useState<number>(0);
  const [isLoadingConversations, setIsLoadingConversations] = useState<boolean>(true);
  const [conversationsError, setConversationsError] = useState<string | null>(null);

  const fetchContextData = useCallback(async () => {
    setIsLoadingContext(true);
    setContextError(null);
    try {
      const res = await api.listContextItems({ page: 1, page_size: 5 });
      setContextItems(res.items);
      setTotalContext(res.total);
      const activeCount = res.items.filter((i) => i.is_active).length;
      setActiveContextCount(activeCount);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setContextError(err.message);
      } else {
        setContextError('Failed to load context items.');
      }
    } finally {
      setIsLoadingContext(false);
    }
  }, []);

  const fetchConversationsData = useCallback(async () => {
    setIsLoadingConversations(true);
    setConversationsError(null);
    try {
      const res = await api.listConversations({ page: 1, page_size: 5 });
      setConversations(res.items);
      setTotalConversations(res.total);
      const activeCount = res.items.filter((c) => c.status === 'active').length;
      setActiveConversationsCount(activeCount);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setConversationsError(err.message);
      } else {
        setConversationsError('Failed to load conversations.');
      }
    } finally {
      setIsLoadingConversations(false);
    }
  }, []);

  useEffect(() => {
    fetchContextData();
    fetchConversationsData();
  }, [fetchContextData, fetchConversationsData]);

  const getItemTypeBadgeClass = (type: string) => {
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

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-surface-200 pb-4">
        <div>
          <h1 className="text-xl font-bold text-surface-900 tracking-tight">
            {merchant?.business_name ? `${merchant.business_name} Dashboard` : 'Merchant Workspace Dashboard'}
          </h1>
          <p className="text-xs text-surface-800 mt-1">
            Grounded AI support assistance configured with your merchant policies, FAQs, and business context.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onNavigate('context')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded border border-surface-300 bg-white text-surface-900 hover:bg-surface-50 shadow-sm transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Context Item
          </button>
          <button
            onClick={() => onNavigate('workspace')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded bg-emerald-700 text-white hover:bg-emerald-800 shadow-sm transition-colors"
          >
            <MessageSquare className="w-3.5 h-3.5" />
            Start AI Chat
          </button>
        </div>
      </div>

      {/* Metrics Row (Real Data Only) */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* Metric 1: Context Items */}
        <div className="bg-white border border-surface-200 rounded p-4 shadow-sm flex items-start justify-between">
          <div>
            <div className="text-xs font-medium text-surface-800">Business Context</div>
            <div className="text-2xl font-bold text-surface-900 mt-1">
              {isLoadingContext ? '...' : totalContext}
            </div>
            <div className="text-[11px] text-surface-800 mt-0.5">
              {isLoadingContext ? 'Checking...' : `${activeContextCount} active in prompt grounding`}
            </div>
          </div>
          <div className="p-2 rounded bg-surface-50 border border-surface-100 text-emerald-700">
            <BookOpen className="w-5 h-5" />
          </div>
        </div>

        {/* Metric 2: Conversations */}
        <div className="bg-white border border-surface-200 rounded p-4 shadow-sm flex items-start justify-between">
          <div>
            <div className="text-xs font-medium text-surface-800">Total Conversations</div>
            <div className="text-2xl font-bold text-surface-900 mt-1">
              {isLoadingConversations ? '...' : totalConversations}
            </div>
            <div className="text-[11px] text-surface-800 mt-0.5">
              {isLoadingConversations ? 'Checking...' : `${activeConversationsCount} active threads`}
            </div>
          </div>
          <div className="p-2 rounded bg-surface-50 border border-surface-100 text-emerald-700">
            <MessageSquare className="w-5 h-5" />
          </div>
        </div>

        {/* Metric 3: AI Service Status */}
        <div className="bg-white border border-surface-200 rounded p-4 shadow-sm flex items-start justify-between">
          <div>
            <div className="text-xs font-medium text-surface-800">AI Model & Grounding</div>
            <div className="text-sm font-semibold text-surface-900 mt-1.5 flex items-center gap-1.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>openai/gpt-oss-120b</span>
            </div>
            <div className="text-[11px] text-surface-800 mt-1">
              Grounded via PostgreSQL context
            </div>
          </div>
          <div className="p-2 rounded bg-surface-50 border border-surface-100 text-emerald-700">
            <Cpu className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* Main 2-Column Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column (2/3 width on desktop): Context & Conversations */}
        <div className="lg:col-span-2 space-y-6">
          {/* Card: Configured Business Context */}
          <div className="bg-white border border-surface-200 rounded shadow-sm">
            <div className="flex items-center justify-between p-4 border-b border-surface-100">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-emerald-700" />
                <h2 className="text-sm font-semibold text-surface-900">Configured Business Context</h2>
                <span className="text-[11px] font-medium text-surface-800 bg-surface-100 px-2 py-0.5 rounded">
                  {totalContext} total
                </span>
              </div>
              <button
                onClick={fetchContextData}
                disabled={isLoadingContext}
                className="text-xs text-surface-800 hover:text-emerald-700 p-1 rounded hover:bg-surface-50 transition-colors"
                title="Refresh context"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isLoadingContext ? 'animate-spin' : ''}`} />
              </button>
            </div>

            <div className="p-4">
              {isLoadingContext ? (
                <div className="py-8 text-center text-xs text-surface-800">
                  Loading business context items...
                </div>
              ) : contextError ? (
                <div className="p-3 rounded bg-red-50 border border-red-200 text-xs text-red-800 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
                    <span>{contextError}</span>
                  </div>
                  <button
                    onClick={fetchContextData}
                    className="underline font-medium hover:text-red-900"
                  >
                    Retry
                  </button>
                </div>
              ) : contextItems.length === 0 ? (
                <div className="rounded border border-dashed border-surface-200 p-6 text-center">
                  <FileText className="w-8 h-8 text-surface-800 mx-auto mb-2" />
                  <p className="text-xs font-medium text-surface-900">No context items configured yet</p>
                  <p className="text-[11px] text-surface-800 max-w-sm mx-auto mt-1 mb-3">
                    Add store return policies, operating hours, delivery rules, or FAQs so the AI assistant gives grounded answers.
                  </p>
                  <button
                    onClick={() => onNavigate('context')}
                    className="inline-flex items-center gap-1 text-xs font-medium text-emerald-800 hover:text-emerald-900 px-2.5 py-1 rounded border border-emerald-300 bg-emerald-50 hover:bg-emerald-100 transition-colors"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Add First Policy / FAQ
                  </button>
                </div>
              ) : (
                <div className="space-y-2.5">
                  <div className="divide-y divide-surface-100">
                    {contextItems.map((item) => (
                      <div key={item.id} className="py-2.5 first:pt-0 last:pb-0 flex items-center justify-between gap-3 text-xs">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-surface-900 truncate">{item.title}</span>
                            <span className={`text-[10px] uppercase font-medium px-1.5 py-0.5 rounded border ${getItemTypeBadgeClass(item.item_type)}`}>
                              {item.item_type}
                            </span>
                            <span className="text-[10px] text-surface-800">
                              v{item.version}
                            </span>
                          </div>
                          <p className="text-[11px] text-surface-800 line-clamp-1 mt-0.5">
                            {item.content}
                          </p>
                        </div>
                        <div className="shrink-0 flex items-center gap-2 text-[11px]">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                            item.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'
                          }`}>
                            {item.is_active ? 'Active' : 'Inactive'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="pt-3 border-t border-surface-100 flex justify-end">
                    <button
                      onClick={() => onNavigate('context')}
                      className="inline-flex items-center gap-1 text-xs font-medium text-emerald-800 hover:text-emerald-900 underline"
                    >
                      <span>Manage all {totalContext} context items</span>
                      <ArrowRight className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Card: Recent Conversations */}
          <div className="bg-white border border-surface-200 rounded shadow-sm">
            <div className="flex items-center justify-between p-4 border-b border-surface-100">
              <div className="flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-emerald-700" />
                <h2 className="text-sm font-semibold text-surface-900">Recent Conversations</h2>
                <span className="text-[11px] font-medium text-surface-800 bg-surface-100 px-2 py-0.5 rounded">
                  {totalConversations} total
                </span>
              </div>
              <button
                onClick={fetchConversationsData}
                disabled={isLoadingConversations}
                className="text-xs text-surface-800 hover:text-emerald-700 p-1 rounded hover:bg-surface-50 transition-colors"
                title="Refresh conversations"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isLoadingConversations ? 'animate-spin' : ''}`} />
              </button>
            </div>

            <div className="p-4">
              {isLoadingConversations ? (
                <div className="py-8 text-center text-xs text-surface-800">
                  Loading recent conversations...
                </div>
              ) : conversationsError ? (
                <div className="p-3 rounded bg-red-50 border border-red-200 text-xs text-red-800 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
                    <span>{conversationsError}</span>
                  </div>
                  <button
                    onClick={fetchConversationsData}
                    className="underline font-medium hover:text-red-900"
                  >
                    Retry
                  </button>
                </div>
              ) : conversations.length === 0 ? (
                <div className="rounded border border-dashed border-surface-200 p-6 text-center">
                  <MessageSquare className="w-8 h-8 text-surface-800 mx-auto mb-2" />
                  <p className="text-xs font-medium text-surface-900">No conversations recorded yet</p>
                  <p className="text-[11px] text-surface-800 max-w-sm mx-auto mt-1 mb-3">
                    Conversations persist across sessions and allow drafting customer replies and testing merchant knowledge grounding.
                  </p>
                  <button
                    onClick={() => onNavigate('workspace')}
                    className="inline-flex items-center gap-1 text-xs font-medium text-emerald-800 hover:text-emerald-900 px-2.5 py-1 rounded border border-emerald-300 bg-emerald-50 hover:bg-emerald-100 transition-colors"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Start New Conversation
                  </button>
                </div>
              ) : (
                <div className="space-y-2.5">
                  <div className="divide-y divide-surface-100">
                    {conversations.map((conv) => (
                      <div
                        key={conv.id}
                        onClick={() => onNavigate('workspace', conv.id)}
                        className="py-2.5 first:pt-0 last:pb-0 flex items-center justify-between gap-3 text-xs cursor-pointer hover:bg-surface-50 px-1 rounded transition-colors"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-surface-900 truncate">{conv.title}</span>
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                              conv.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'
                            }`}>
                              {conv.status}
                            </span>
                          </div>
                          <div className="flex items-center gap-2 text-[11px] text-surface-800 mt-0.5">
                            <Clock className="w-3 h-3 text-surface-800" />
                            <span>
                              {conv.last_message_at
                                ? `Activity ${new Date(conv.last_message_at).toLocaleString()}`
                                : `Created ${new Date(conv.created_at).toLocaleDateString()}`}
                            </span>
                          </div>
                        </div>
                        <ArrowRight className="w-3.5 h-3.5 text-surface-800 shrink-0" />
                      </div>
                    ))}
                  </div>

                  <div className="pt-3 border-t border-surface-100 flex justify-end">
                    <button
                      onClick={() => onNavigate('workspace')}
                      className="inline-flex items-center gap-1 text-xs font-medium text-emerald-800 hover:text-emerald-900 underline"
                    >
                      <span>Open AI Workspace</span>
                      <ArrowRight className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Column (1/3 width on desktop): Merchant Profile & Health Status */}
        <div className="space-y-6">
          <MerchantProfileCard profile={merchant} />
          <HealthIndicator />
        </div>
      </div>
    </div>
  );
};
