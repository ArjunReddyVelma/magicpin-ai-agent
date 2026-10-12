import React, { useEffect, useState } from 'react';
import { Activity, CheckCircle2, AlertCircle, RefreshCw } from 'lucide-react';
import { HealthzResponse, ReadyzResponse } from '../types/api';

export const HealthIndicator: React.FC = () => {
  const [liveness, setLiveness] = useState<'checking' | 'healthy' | 'unhealthy'>('checking');
  const [readiness, setReadiness] = useState<'checking' | 'ready' | 'unready'>('checking');
  const [lastChecked, setLastChecked] = useState<string>('');

  const checkHealth = async () => {
    try {
      setLiveness('checking');
      const res = await fetch('/v1/healthz');
      if (res.ok) {
        const data: HealthzResponse = await res.json();
        setLiveness(data.status === 'ok' ? 'healthy' : 'unhealthy');
      } else {
        setLiveness('unhealthy');
      }
    } catch {
      setLiveness('unhealthy');
    }

    try {
      setReadiness('checking');
      const res = await fetch('/v1/readyz');
      if (res.ok) {
        const data: ReadyzResponse = await res.json();
        setReadiness(data.status === 'ready' ? 'ready' : 'unready');
      } else {
        setReadiness('unready');
      }
    } catch {
      setReadiness('unready');
    }

    setLastChecked(new Date().toLocaleTimeString());
  };

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="bg-white border border-surface-200 rounded p-4 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-emerald-700" />
          <h3 className="text-sm font-semibold text-surface-900">Backend Service Status</h3>
        </div>
        <button
          onClick={checkHealth}
          className="flex items-center gap-1 text-xs text-surface-800 hover:text-emerald-700 font-medium px-2 py-1 rounded border border-surface-200 hover:border-surface-300"
          title="Refresh health status"
        >
          <RefreshCw className="w-3 h-3" />
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs">
        <div className="p-2.5 rounded bg-surface-50 border border-surface-200">
          <div className="text-surface-800 font-medium mb-1">Liveness (healthz)</div>
          <div className="flex items-center gap-1.5 font-medium">
            {liveness === 'healthy' ? (
              <>
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                <span className="text-emerald-800">Process Online</span>
              </>
            ) : liveness === 'checking' ? (
              <span className="text-surface-800">Checking...</span>
            ) : (
              <>
                <AlertCircle className="w-3.5 h-3.5 text-rose-600" />
                <span className="text-rose-800">Process Unreachable</span>
              </>
            )}
          </div>
        </div>

        <div className="p-2.5 rounded bg-surface-50 border border-surface-200">
          <div className="text-surface-800 font-medium mb-1">Readiness (readyz)</div>
          <div className="flex items-center gap-1.5 font-medium">
            {readiness === 'ready' ? (
              <>
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                <span className="text-emerald-800">Dependencies Ready</span>
              </>
            ) : readiness === 'checking' ? (
              <span className="text-surface-800">Checking...</span>
            ) : (
              <>
                <AlertCircle className="w-3.5 h-3.5 text-rose-600" />
                <span className="text-rose-800">Degraded</span>
              </>
            )}
          </div>
        </div>
      </div>

      {lastChecked && (
        <div className="mt-2.5 text-[11px] text-surface-800">
          Last checked at {lastChecked}
        </div>
      )}
    </div>
  );
};
