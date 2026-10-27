import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  LifeBuoy,
  Store,
  MapPin,
  Tag,
  Clock,
  CheckCircle2,
  AlertCircle,
  Send,
  Loader2,
  AlertTriangle,
  User,
  ShieldCheck,
  ArrowLeft,
} from 'lucide-react';
import { api, ApiClientError } from '../api/client';
import {
  PublicMerchantProfile,
  CustomerHistoryItem,
} from '../types/api';

interface CustomerSupportPageProps {
  merchantId: string;
  onNavigateHome?: () => void;
}

export const CustomerSupportPage: React.FC<CustomerSupportPageProps> = ({
  merchantId,
  onNavigateHome,
}) => {
  // Merchant public profile
  const [merchant, setMerchant] = useState<PublicMerchantProfile | null>(null);
  const [isLoadingMerchant, setIsLoadingMerchant] = useState(true);
  const [merchantError, setMerchantError] = useState<string | null>(null);

  // In-memory customer session state (NEVER written to localStorage/sessionStorage/URL)
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [customerToken, setCustomerToken] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<'active' | 'closed' | null>(null);
  const [customerName, setCustomerName] = useState('');
  const [isStartingSession, setIsStartingSession] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);

  // Conversation history & composer state
  const [messages, setMessages] = useState<CustomerHistoryItem[]>([]);
  const [inquiryText, setInquiryText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [permanentError, setPermanentError] = useState<string | null>(null);

  // Polling management refs
  const isPollingRef = useRef(false);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isMountedRef = useRef(true);

  // ---------------------------------------------------------------------------
  // 1. Fetch public merchant profile on mount
  // ---------------------------------------------------------------------------
  useEffect(() => {
    isMountedRef.current = true;
    const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(merchantId);
    if (!merchantId || !isUuid) {
      setIsLoadingMerchant(false);
      setMerchantError('Invalid merchant support link. Please check the URL provided by the store.');
      return;
    }

    async function fetchMerchant() {
      setIsLoadingMerchant(true);
      setMerchantError(null);
      try {
        const profile = await api.getPublicMerchantProfile(merchantId);
        if (isMountedRef.current) {
          setMerchant(profile);
        }
      } catch (err: unknown) {
        if (isMountedRef.current) {
          if (err instanceof ApiClientError && err.statusCode === 404) {
            setMerchantError('Merchant not found. This store support channel is unavailable.');
          } else {
            setMerchantError('Unable to load merchant information. Please verify your connection.');
          }
        }
      } finally {
        if (isMountedRef.current) {
          setIsLoadingMerchant(false);
        }
      }
    }

    fetchMerchant();

    return () => {
      isMountedRef.current = false;
    };
  }, [merchantId]);

  // ---------------------------------------------------------------------------
  // 2. Fetch history function (polled and called on demand)
  // ---------------------------------------------------------------------------
  const fetchHistory = useCallback(
    async (sId: string, tok: string, isBackgroundPoll = false) => {
      if (isPollingRef.current || !isMountedRef.current) return;
      isPollingRef.current = true;

      try {
        const res = await api.getCustomerHistory(sId, tok, 100);
        if (isMountedRef.current) {
          setMessages(res.items);
          setPermanentError(null);
        }
      } catch (err: unknown) {
        if (!isMountedRef.current) return;

        if (err instanceof ApiClientError) {
          // Permanent token/session errors: stop polling
          if (err.statusCode === 401 || err.statusCode === 403 || err.statusCode === 404) {
            setPermanentError('Your support session has expired or is invalid. Please start a new session.');
            if (pollIntervalRef.current) {
              clearInterval(pollIntervalRef.current);
              pollIntervalRef.current = null;
            }
            return;
          }
        }
        // For transient errors during background poll, do not crash or disrupt the user
        if (!isBackgroundPoll) {
          // Show error only if triggered manually
          setSendError('Failed to refresh conversation history. Reconnecting...');
        }
      } finally {
        isPollingRef.current = false;
      }
    },
    []
  );

  // ---------------------------------------------------------------------------
  // 3. Automatic Polling Engine (every 4s, pauses when page is hidden)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!sessionId || !customerToken || permanentError || sessionStatus === 'closed') {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      return;
    }

    const POLLING_INTERVAL_MS = 4000;

    const startPolling = () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = setInterval(() => {
        if (document.visibilityState === 'visible' && !isPollingRef.current) {
          fetchHistory(sessionId, customerToken, true);
        }
      }, POLLING_INTERVAL_MS);
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        // Immediate poll on visible, then restart interval
        fetchHistory(sessionId, customerToken, true);
        startPolling();
      } else {
        // Page hidden: pause timer to conserve resources
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
      }
    };

    // Initial fetch of messages
    fetchHistory(sessionId, customerToken, false);
    startPolling();

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [sessionId, customerToken, permanentError, sessionStatus, fetchHistory]);

  // ---------------------------------------------------------------------------
  // 4. Start Support Session
  // ---------------------------------------------------------------------------
  const handleStartSession = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (isStartingSession || !merchantId) return;

    setIsStartingSession(true);
    setSessionError(null);

    try {
      const res = await api.createCustomerSupportSession(
        merchantId,
        customerName.trim() || undefined
      );

      // Store credentials strictly in component memory
      setSessionId(res.session_id);
      setCustomerToken(res.customer_token);
      setSessionStatus(res.status as 'active');
      setPermanentError(null);
      setSendError(null);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        if (err.statusCode === 429) {
          setSessionError('Too many session requests. Please wait a moment and try again.');
        } else {
          setSessionError(err.message);
        }
      } else {
        setSessionError('Unable to start support session. Please check your connection.');
      }
    } finally {
      setIsStartingSession(false);
    }
  };

  // ---------------------------------------------------------------------------
  // 5. Submit Customer Inquiry
  // ---------------------------------------------------------------------------
  const handleSubmitInquiry = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSending || !sessionId || !customerToken) return;

    const content = inquiryText.trim();
    if (!content) {
      setSendError('Please enter a message before sending.');
      return;
    }
    if (content.length > 2000) {
      setSendError('Your inquiry exceeds the maximum allowed length of 2,000 characters.');
      return;
    }

    setIsSending(true);
    setSendError(null);

    try {
      const confirmed = await api.submitCustomerInquiry(sessionId, customerToken, content);

      // Server confirmed persistence: clear input and append inquiry
      setInquiryText('');
      setMessages((prev) => [
        ...prev,
        {
          id: confirmed.id,
          customer_text: confirmed.customer_text,
          reply: null,
          status: confirmed.status,
          delivered_at: null,
          created_at: confirmed.created_at,
        },
      ]);

      // Trigger background sync to confirm server order
      fetchHistory(sessionId, customerToken, true);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        if (err.statusCode === 400 && err.code === 'SESSION_CLOSED') {
          setSessionStatus('closed');
          setSendError('This support session has been closed. Please start a new session to send messages.');
        } else if (err.statusCode === 401 || err.statusCode === 403) {
          setPermanentError('Your session token has expired or is invalid. Please start a new session.');
        } else if (err.statusCode === 429) {
          setSendError('You are sending messages too quickly. Please wait a moment and retry.');
        } else {
          setSendError(err.message || 'Failed to send inquiry.');
        }
      } else {
        setSendError('Network error: Unable to deliver inquiry. Please try again.');
      }
    } finally {
      setIsSending(false);
    }
  };

  // ---------------------------------------------------------------------------
  // 6. Reset / Start New Session
  // ---------------------------------------------------------------------------
  const handleResetSession = () => {
    setSessionId(null);
    setCustomerToken(null);
    setSessionStatus(null);
    setMessages([]);
    setPermanentError(null);
    setSendError(null);
    setSessionError(null);
  };

  // ---------------------------------------------------------------------------
  // Render: Loading State
  // ---------------------------------------------------------------------------
  if (isLoadingMerchant) {
    return (
      <div className="min-h-screen bg-surface-50 flex items-center justify-center p-4">
        <div className="text-center space-y-3">
          <div className="w-10 h-10 rounded-lg bg-emerald-700 mx-auto flex items-center justify-center text-white shadow-sm">
            <LifeBuoy className="w-5 h-5 animate-spin" />
          </div>
          <p className="text-xs font-medium text-surface-800">
            Connecting to merchant customer support...
          </p>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Merchant Error / Unavailable
  // ---------------------------------------------------------------------------
  if (merchantError || !merchant) {
    return (
      <div className="min-h-screen bg-surface-50 flex items-center justify-center p-4">
        <div className="max-w-md w-full bg-white border border-surface-200 rounded-xl p-6 shadow-sm text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-rose-50 border border-rose-200 text-rose-600 flex items-center justify-center mx-auto">
            <AlertCircle className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-base font-bold text-surface-900">
              Support Channel Unavailable
            </h2>
            <p className="text-xs text-surface-800 mt-1.5 leading-relaxed">
              {merchantError || 'This store does not exist or customer support is not configured.'}
            </p>
          </div>
          {onNavigateHome && (
            <button
              onClick={onNavigateHome}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded border border-surface-300 bg-white text-surface-800 hover:bg-surface-50 transition-colors shadow-sm"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Return Home</span>
            </button>
          )}
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: Active Support Chat Interface
  // ---------------------------------------------------------------------------
  return (
    <div className="min-h-screen bg-surface-50 flex flex-col text-surface-900">
      {/* Merchant Branding Header */}
      <header className="bg-white border-b border-surface-200 sticky top-0 z-30 shadow-sm">
        <div className="max-w-3xl w-full mx-auto px-4 py-3.5 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-emerald-700 flex items-center justify-center font-bold text-white shadow-sm flex-shrink-0 text-sm">
              <Store className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-sm font-bold text-surface-900 tracking-tight">
                  {merchant.business_name}
                </h1>
                {merchant.category && (
                  <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded bg-surface-100 text-surface-800 border border-surface-200">
                    <Tag className="w-2.5 h-2.5" />
                    {merchant.category}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-[11px] text-surface-800 mt-0.5">
                {merchant.location && (
                  <span className="flex items-center gap-0.5">
                    <MapPin className="w-3 h-3 text-surface-500" />
                    {merchant.location}
                  </span>
                )}
                <span>&bull;</span>
                <span className="text-emerald-700 font-medium flex items-center gap-1">
                  <ShieldCheck className="w-3 h-3" />
                  Official Web Support
                </span>
              </div>
            </div>
          </div>

          {sessionId && (
            <button
              onClick={handleResetSession}
              className="text-[11px] font-medium text-surface-700 hover:text-surface-900 border border-surface-200 px-2.5 py-1 rounded hover:bg-surface-50 transition-colors shadow-sm"
              title="Start a new session"
            >
              New Session
            </button>
          )}
        </div>
      </header>

      {/* Main Support Workspace */}
      <main className="flex-1 max-w-3xl w-full mx-auto px-4 py-6 flex flex-col">
        {!sessionId ? (
          // Session Initiation Step
          <div className="my-auto max-w-md w-full mx-auto bg-white border border-surface-200 rounded-xl p-6 shadow-sm space-y-5">
            <div className="text-center space-y-2">
              <div className="w-12 h-12 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 flex items-center justify-center mx-auto">
                <LifeBuoy className="w-6 h-6" />
              </div>
              <h2 className="text-base font-bold text-surface-900">
                Welcome to {merchant.business_name} Support
              </h2>
              <p className="text-xs text-surface-800 leading-relaxed max-w-xs mx-auto">
                Have a question about orders, store hours, or menu items? Start a support conversation below.
              </p>
              {merchant.description && (
                <p className="text-[11px] text-surface-700 italic border-t border-surface-100 pt-2 mt-2">
                  &ldquo;{merchant.description}&rdquo;
                </p>
              )}
            </div>

            {sessionError && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-md flex items-center gap-2 text-xs text-rose-900">
                <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
                <span>{sessionError}</span>
              </div>
            )}

            <form onSubmit={handleStartSession} className="space-y-4">
              <div>
                <label
                  htmlFor="customerNameInput"
                  className="block text-xs font-semibold text-surface-800 mb-1"
                >
                  Your Name <span className="text-surface-500 font-normal">(Optional)</span>
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-2.5 flex items-center pointer-events-none text-surface-400">
                    <User className="w-3.5 h-3.5" />
                  </div>
                  <input
                    id="customerNameInput"
                    type="text"
                    maxLength={120}
                    value={customerName}
                    onChange={(e) => setCustomerName(e.target.value)}
                    disabled={isStartingSession}
                    placeholder="e.g. Alex"
                    className="w-full text-xs pl-8 pr-3 py-2 rounded-md border border-surface-300 focus:outline-none focus:ring-1 focus:ring-emerald-600 focus:border-emerald-600 text-surface-900 placeholder:text-surface-400 disabled:opacity-50"
                  />
                </div>
              </div>

              <div className="bg-surface-50 border border-surface-200 rounded-md p-3 text-[11px] text-surface-800 space-y-1">
                <div className="flex items-center gap-1.5 font-medium text-surface-900">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-700" />
                  <span>Secure, In-Memory Session</span>
                </div>
                <p className="text-[10px] leading-relaxed text-surface-700">
                  Your session is private to this browser tab. All replies are reviewed and authorized directly by the store team before delivery.
                </p>
              </div>

              <button
                type="submit"
                disabled={isStartingSession}
                className="w-full inline-flex items-center justify-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-emerald-700 hover:bg-emerald-800 rounded-md transition-colors disabled:opacity-50 shadow-sm"
              >
                {isStartingSession ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Connecting...</span>
                  </>
                ) : (
                  <>
                    <Send className="w-3.5 h-3.5" />
                    <span>Start Support Conversation</span>
                  </>
                )}
              </button>
            </form>
          </div>
        ) : (
          // Active Chat Experience
          <div className="flex-1 flex flex-col bg-white border border-surface-200 rounded-xl shadow-sm overflow-hidden min-h-[500px]">
            {/* Session Status Banner */}
            <div className="px-4 py-2.5 bg-surface-50 border-b border-surface-200 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                <span className="font-semibold text-surface-900">
                  Support Session with {merchant.business_name}
                </span>
                {customerName && (
                  <span className="text-[11px] text-surface-800">
                    &bull; Chatting as <span className="font-medium">{customerName}</span>
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-[11px] text-surface-700">
                <Clock className="w-3 h-3 text-surface-500" />
                <span>Auto-refreshes for merchant replies</span>
              </div>
            </div>

            {/* Permanent Error Notice */}
            {permanentError && (
              <div className="p-3 bg-rose-50 border-b border-rose-200 flex items-center justify-between gap-2 text-xs text-rose-900">
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
                  <span>{permanentError}</span>
                </div>
                <button
                  onClick={handleResetSession}
                  className="font-semibold underline hover:text-rose-950 text-[11px]"
                >
                  Start New Session
                </button>
              </div>
            )}

            {/* Closed Session Banner */}
            {sessionStatus === 'closed' && (
              <div className="p-3 bg-amber-50 border-b border-amber-200 flex items-center justify-between gap-2 text-xs text-amber-900">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />
                  <span>This support conversation has been closed by the store.</span>
                </div>
                <button
                  onClick={handleResetSession}
                  className="font-semibold underline hover:text-amber-950 text-[11px]"
                >
                  Start New Conversation
                </button>
              </div>
            )}

            {/* Conversation Messages Container */}
            <div
              className="flex-1 p-4 sm:p-5 overflow-y-auto space-y-4"
              aria-live="polite"
            >
              {messages.length === 0 ? (
                <div className="text-center py-16 space-y-2 text-surface-800">
                  <LifeBuoy className="w-8 h-8 mx-auto text-surface-400" />
                  <p className="text-xs font-semibold text-surface-900">
                    No messages in this conversation yet
                  </p>
                  <p className="text-[11px] text-surface-700 max-w-xs mx-auto">
                    Type your inquiry below. Store staff will review your question and respond here.
                  </p>
                </div>
              ) : (
                messages.map((item) => {
                  const isDelivered = item.status === 'delivered' && Boolean(item.reply);

                  return (
                    <div key={item.id} className="space-y-2.5">
                      {/* Customer Inquiry Bubble (Right) */}
                      <div className="flex flex-col items-end">
                        <div className="max-w-[85%] bg-emerald-700 text-white rounded-2xl rounded-tr-sm px-4 py-2.5 text-xs shadow-sm whitespace-pre-wrap leading-relaxed">
                          {item.customer_text}
                        </div>
                        <span className="text-[10px] text-surface-700 mt-1 px-1">
                          {new Date(item.created_at).toLocaleTimeString([], {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                      </div>

                      {/* Merchant Reply Bubble or Pending Indicator (Left) */}
                      {isDelivered ? (
                        <div className="flex flex-col items-start">
                          <div className="max-w-[85%] bg-surface-100 border border-surface-200 rounded-2xl rounded-tl-sm px-4 py-2.5 text-xs text-surface-900 shadow-sm space-y-1">
                            <div className="flex items-center gap-1.5 text-[10px] font-bold text-emerald-800 uppercase tracking-wide">
                              <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                              <span>{merchant.business_name} Reply</span>
                            </div>
                            <div className="whitespace-pre-wrap leading-relaxed">
                              {item.reply}
                            </div>
                          </div>
                          {item.delivered_at && (
                            <span className="text-[10px] text-surface-700 mt-1 px-1">
                              Delivered at{' '}
                              {new Date(item.delivered_at).toLocaleTimeString([], {
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </span>
                          )}
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5 text-[11px] text-surface-800 bg-surface-50 border border-surface-200 rounded-lg px-3 py-1.5 w-fit">
                          <Clock className="w-3 h-3 text-amber-600 animate-pulse" />
                          <span>Awaiting merchant review &bull; Stored securely</span>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>

            {/* Composer Error Notice */}
            {sendError && (
              <div className="px-4 py-2 bg-rose-50 border-t border-rose-200 text-rose-900 text-xs flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <AlertCircle className="w-3.5 h-3.5 text-rose-600 flex-shrink-0" />
                  <span>{sendError}</span>
                </div>
                <button
                  onClick={() => setSendError(null)}
                  className="text-rose-700 hover:text-rose-900 text-xs font-bold"
                >
                  &times;
                </button>
              </div>
            )}

            {/* Message Composer Area */}
            <form
              onSubmit={handleSubmitInquiry}
              className="p-3.5 bg-surface-50/80 border-t border-surface-200 space-y-2"
            >
              <div className="flex items-center justify-between text-[11px] text-surface-800">
                <span className="flex items-center gap-1">
                  <ShieldCheck className="w-3 h-3 text-emerald-700" />
                  Replies require merchant approval before delivery
                </span>
                <span
                  className={
                    inquiryText.length > 1900
                      ? 'text-rose-600 font-semibold'
                      : 'text-surface-700'
                  }
                >
                  {inquiryText.length}/2000
                </span>
              </div>

              <div className="flex gap-2">
                <textarea
                  value={inquiryText}
                  onChange={(e) => {
                    if (e.target.value.length <= 2000) {
                      setInquiryText(e.target.value);
                    }
                  }}
                  disabled={isSending || sessionStatus === 'closed' || Boolean(permanentError)}
                  placeholder={
                    sessionStatus === 'closed'
                      ? 'This support session is closed. Start a new session to send a message.'
                      : 'Type your inquiry for the store team (up to 2,000 characters)...'
                  }
                  rows={2}
                  className="flex-1 text-xs p-2.5 rounded-lg border border-surface-300 focus:outline-none focus:ring-1 focus:ring-emerald-600 focus:border-emerald-600 text-surface-900 placeholder:text-surface-400 disabled:opacity-50 resize-none leading-relaxed"
                />

                <button
                  type="submit"
                  disabled={
                    isSending ||
                    !inquiryText.trim() ||
                    sessionStatus === 'closed' ||
                    Boolean(permanentError)
                  }
                  className="inline-flex items-center justify-center px-4 py-2 bg-emerald-700 hover:bg-emerald-800 text-white rounded-lg text-xs font-medium transition-colors disabled:opacity-50 shadow-sm self-end h-[42px]"
                  title="Send Inquiry"
                >
                  {isSending ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                </button>
              </div>
            </form>
          </div>
        )}
      </main>

      {/* Public Customer Footer */}
      <footer className="border-t border-surface-200 bg-white py-3 text-center text-[11px] text-surface-700">
        <div>
          Powered by Magicpin Web Support &bull; Human-in-the-Loop Customer Assistance
        </div>
      </footer>
    </div>
  );
};

export default CustomerSupportPage;
