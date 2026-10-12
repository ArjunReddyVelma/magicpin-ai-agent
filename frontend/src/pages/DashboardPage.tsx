import React from 'react';
import { HealthIndicator } from '../components/HealthIndicator';
import { MessageSquare, Plus, FileText, CheckCircle2, AlertTriangle } from 'lucide-react';

interface DashboardPageProps {
  onNavigate: (tab: string) => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({ onNavigate }) => {
  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-surface-200 pb-4">
        <div>
          <h1 className="text-xl font-bold text-surface-900 tracking-tight">Merchant Workspace Dashboard</h1>
          <p className="text-xs text-surface-800 mt-1">
            Grounded AI support assistance configured with your merchant policies, FAQs, and business context.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onNavigate('context')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded border border-surface-300 bg-white text-surface-900 hover:bg-surface-50 shadow-sm"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Context Item
          </button>
          <button
            onClick={() => onNavigate('workspace')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded bg-emerald-700 text-white hover:bg-emerald-800 shadow-sm"
          >
            <MessageSquare className="w-3.5 h-3.5" />
            Start AI Chat
          </button>
        </div>
      </div>

      {/* Grid: Health Status & Operational Foundation */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-1">
          <HealthIndicator />
        </div>

        <div className="md:col-span-2 bg-white border border-surface-200 rounded p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-surface-100 pb-3">
            <h2 className="text-sm font-semibold text-surface-900">Workspace Verification & Setup Status</h2>
            <span className="text-[11px] font-medium text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
              Phase 1 Active
            </span>
          </div>

          <div className="space-y-3 text-xs">
            <div className="flex items-start gap-2.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
              <div>
                <span className="font-semibold text-surface-900">Repository & Application Skeleton:</span>
                <p className="text-surface-800">
                  Clean modular monolith foundation with React + TypeScript + Vite frontend and FastAPI backend.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-2.5">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
              <div>
                <span className="font-semibold text-surface-900">Validated Health Endpoints:</span>
                <p className="text-surface-800">
                  <code className="bg-surface-100 px-1 py-0.5 rounded">/v1/healthz</code> (liveness) and{' '}
                  <code className="bg-surface-100 px-1 py-0.5 rounded">/v1/readyz</code> (readiness) implemented strictly against OpenAPI specification.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-2.5">
              <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
              <div>
                <span className="font-semibold text-surface-900">Persistent Database Gate (Phase 2):</span>
                <p className="text-surface-800">
                  PostgreSQL models, Alembic migrations, and persistent repositories are scheduled in Phase 2. Currently operating in clean local foundation mode.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Honest Empty States for Core Workflows */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Context Status */}
        <div className="bg-white border border-surface-200 rounded p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-surface-900">Configured Business Context</h3>
            <span className="text-xs text-surface-800">0 items</span>
          </div>
          <div className="rounded border border-dashed border-surface-200 p-6 text-center">
            <FileText className="w-8 h-8 text-surface-800 mx-auto mb-2" />
            <p className="text-xs font-medium text-surface-900">No context items configured</p>
            <p className="text-[11px] text-surface-800 max-w-sm mx-auto mt-1 mb-3">
              Add your store refund policies, cancellation rules, and operating FAQs so the AI assistant gives grounded answers.
            </p>
            <button
              onClick={() => onNavigate('context')}
              className="inline-flex items-center gap-1 text-xs font-medium text-emerald-800 hover:text-emerald-900 px-2.5 py-1 rounded border border-emerald-300 bg-emerald-50 hover:bg-emerald-100"
            >
              Add First FAQ / Policy
            </button>
          </div>
        </div>

        {/* Conversation History */}
        <div className="bg-white border border-surface-200 rounded p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-surface-900">Recent Conversations</h3>
            <span className="text-xs text-surface-800">0 active</span>
          </div>
          <div className="rounded border border-dashed border-surface-200 p-6 text-center">
            <MessageSquare className="w-8 h-8 text-surface-800 mx-auto mb-2" />
            <p className="text-xs font-medium text-surface-900">No conversations recorded</p>
            <p className="text-[11px] text-surface-800 max-w-sm mx-auto mt-1 mb-3">
              Conversations persist across sessions and allow drafting customer replies and reviewing suggested actions.
            </p>
            <button
              onClick={() => onNavigate('workspace')}
              className="inline-flex items-center gap-1 text-xs font-medium text-emerald-800 hover:text-emerald-900 px-2.5 py-1 rounded border border-emerald-300 bg-emerald-50 hover:bg-emerald-100"
            >
              Open AI Workspace
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
