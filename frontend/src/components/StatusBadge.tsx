import React from 'react';

interface StatusBadgeProps {
  status: 'active' | 'archived' | 'pending' | 'approved' | 'dismissed' | 'complete' | 'failed' | 'ready' | 'ok';
  label?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label }) => {
  const displayLabel = label || status;

  const styles: Record<StatusBadgeProps['status'], string> = {
    active: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    ready: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    ok: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    approved: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    complete: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    pending: 'bg-amber-50 text-amber-800 border-amber-200',
    archived: 'bg-slate-100 text-slate-700 border-slate-200',
    dismissed: 'bg-slate-100 text-slate-700 border-slate-200',
    failed: 'bg-rose-50 text-rose-800 border-rose-200',
  };

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded border ${styles[status] || styles.pending}`}
    >
      {displayLabel}
    </span>
  );
};
