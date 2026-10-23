import { FormEvent, useCallback, useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, MessageCircle, RefreshCw, Send, ShieldAlert } from 'lucide-react';
import { api } from '../api/client';
import { WhatsAppAccountStatus, WhatsAppInboxMessage } from '../types/api';

export function WhatsAppInboxPage() {
  const [account, setAccount] = useState<WhatsAppAccountStatus | null>(null);
  const [items, setItems] = useState<WhatsAppInboxMessage[]>([]);
  const [phone, setPhone] = useState('');
  const [business, setBusiness] = useState('');
  const [token, setToken] = useState('');
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  // Simulation form state
  const [simPhone, setSimPhone] = useState('919876543210');
  const [simName, setSimName] = useState('Test Customer');
  const [simText, setSimText] = useState('');

  const load = useCallback(async () => {
    try {
      const [a, m] = await Promise.all([api.getWhatsAppAccount(), api.listWhatsAppMessages()]);
      setAccount(a);
      setItems(m.items);
      setDrafts(prev => {
        const n = { ...prev };
        m.items.forEach(i => {
          if (n[i.id] === undefined) n[i.id] = i.suggested_reply || '';
        });
        return n;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load WhatsApp inbox.');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const a = await api.saveWhatsAppAccount({
        phone_number_id: phone.trim(),
        business_account_id: business.trim() || undefined,
        access_token: token.trim(),
      });
      setAccount(a);
      setToken('');
      setNotice('Connection saved. Access token is not shown again.');
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save account.');
    } finally {
      setBusy(false);
    }
  };

  const send = async (item: WhatsAppInboxMessage) => {
    const text = (drafts[item.id] || '').trim();
    if (!text) {
      setError('Enter a reply first.');
      return;
    }
    let force = false;
    if (item.status === 'send_ambiguous') {
      if (!window.confirm('Previous send timed out and outcome is unconfirmed with Meta. Retrying may deliver a duplicate message if the customer already received it. Confirm retry?')) return;
      force = true;
    } else if (!window.confirm('Send this reply to this customer in the same WhatsApp chat?')) {
      return;
    }
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await api.sendWhatsAppReply(item.id, text, force);
      setNotice(account?.mode === 'mock' ? 'Simulated reply sent locally (Meta API was not called).' : 'Reply sent to the customer through WhatsApp.');
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'WhatsApp send failed.');
      await load();
    } finally {
      setBusy(false);
    }
  };

  const simulateInbound = async (e: FormEvent) => {
    e.preventDefault();
    if (!simText.trim()) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await api.simulateInboundWhatsAppMessage({
        customer_wa_id: simPhone.trim(),
        customer_name: simName.trim() || undefined,
        message_text: simText.trim(),
      });
      setSimText('');
      setNotice('Simulated inbound message created with AI-generated draft proposal.');
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to simulate message.');
    } finally {
      setBusy(false);
    }
  };

  const triggerSimStatus = async (id: string, status: string, errorMsg?: string) => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await api.simulateWhatsAppStatus(id, status, errorMsg);
      setNotice(`Simulated status updated to ${status}.`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update simulation status.');
    } finally {
      setBusy(false);
    }
  };

  const fillMockCredentials = () => {
    setPhone('109876543210');
    setBusiness('mock-business-acc');
    setToken('mock_access_token_at_least_20_chars');
  };

  const isMockMode = account?.mode === 'mock';

  return (
    <div className="max-w-5xl mx-auto pb-12 space-y-6">
      <header className="flex justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold text-surface-900">WhatsApp Business Inbox</h1>
          <p className="mt-1 text-xs text-surface-800">Review incoming messages, edit the AI draft, and explicitly approve it by sending.</p>
        </div>
        <button onClick={() => void load()} disabled={busy} className="inline-flex items-center gap-2 border border-surface-300 bg-white px-3 py-2 text-xs rounded">
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </button>
      </header>

      {isMockMode && (
        <div role="status" className="p-3 border border-amber-300 bg-amber-50 text-amber-900 text-xs rounded flex flex-wrap items-center justify-between gap-2 font-medium">
          <span className="flex items-center gap-2">
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-amber-600 animate-pulse" />
            Mock Mode Active — Meta API Disabled
          </span>
          <span className="text-[11px] font-normal text-amber-800">
            Outbound sends and customer inbounds are simulated locally. No network requests are made to Meta Graph API.
          </span>
        </div>
      )}

      {error && (
        <div role="alert" className="p-3 border border-red-200 bg-red-50 text-red-800 text-xs flex gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}
      {notice && (
        <div role="status" className="p-3 border border-emerald-200 bg-emerald-50 text-emerald-800 text-xs flex gap-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" />
          {notice}
        </div>
      )}

      <section className="bg-white border border-surface-200 p-5 space-y-3">
        <h2 className="text-sm font-semibold flex items-center gap-2">
          <MessageCircle className="w-4 h-4 text-emerald-700" />
          WhatsApp connection
        </h2>
        {account?.connected ? (
          <div className="text-xs text-surface-800 space-y-1">
            <p className="text-emerald-700 font-semibold">Connection details saved</p>
            <p>Phone Number ID: <code>{account.phone_number_id}</code></p>
            <p>Business Account ID: {account.business_account_id || 'Not supplied'}</p>
            <p>The access token is encrypted at rest and never returned by the API.</p>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <p className="text-xs text-surface-800">
              {isMockMode
                ? 'Enter mock Phone Number ID and token to enable local inbox simulation.'
                : 'Enter Meta WhatsApp Cloud API credentials. Server environment must also have webhook and encryption secrets configured.'}
            </p>
            {isMockMode && (
              <button
                type="button"
                onClick={fillMockCredentials}
                className="text-xs text-amber-800 underline hover:text-amber-950 font-medium"
              >
                Use mock sample credentials
              </button>
            )}
          </div>
        )}
        <form onSubmit={save} className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <label className="text-xs font-medium space-y-1">
            Phone Number ID
            <input required value={phone} onChange={e => setPhone(e.target.value)} className="block w-full border border-surface-300 p-2 rounded text-sm" />
          </label>
          <label className="text-xs font-medium space-y-1">
            Business Account ID (optional)
            <input value={business} onChange={e => setBusiness(e.target.value)} className="block w-full border border-surface-300 p-2 rounded text-sm" />
          </label>
          <label className="text-xs font-medium space-y-1 md:col-span-2">
            Access token
            <input required type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} className="block w-full border border-surface-300 p-2 rounded text-sm" placeholder={isMockMode ? 'Mock token (at least 20 chars)' : 'Token is never displayed after saving'} />
          </label>
          <div className="md:col-span-2">
            <button disabled={busy} className="bg-emerald-700 text-white px-4 py-2 rounded text-xs font-semibold disabled:opacity-50">
              {busy ? 'Saving…' : 'Save WhatsApp connection'}
            </button>
          </div>
        </form>
      </section>

      {isMockMode && account?.connected && (
        <section className="bg-amber-50/60 border border-amber-200 p-4 rounded space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-amber-950 flex items-center gap-1.5">
              <ShieldAlert className="w-4 h-4 text-amber-700" />
              Simulate Inbound Customer Message (Mock Mode)
            </h3>
            <span className="text-[10px] text-amber-800 uppercase tracking-wider font-semibold">Offline Sandbox</span>
          </div>
          <form onSubmit={simulateInbound} className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <input
              placeholder="Customer WhatsApp ID"
              value={simPhone}
              onChange={e => setSimPhone(e.target.value)}
              required
              className="border border-surface-300 p-2 rounded text-xs bg-white"
            />
            <input
              placeholder="Customer Name (optional)"
              value={simName}
              onChange={e => setSimName(e.target.value)}
              className="border border-surface-300 p-2 rounded text-xs bg-white"
            />
            <div className="flex gap-2 md:col-span-3">
              <input
                placeholder="Simulate customer message (e.g. What are your opening hours today?)"
                value={simText}
                onChange={e => setSimText(e.target.value)}
                required
                className="flex-1 border border-surface-300 p-2 rounded text-xs bg-white"
              />
              <button
                type="submit"
                disabled={busy || !simText.trim()}
                className="bg-amber-800 text-white px-3 py-2 rounded text-xs font-semibold hover:bg-amber-900 disabled:opacity-50 whitespace-nowrap"
              >
                {busy ? 'Simulating…' : 'Simulate message'}
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="space-y-3">
        <div className="flex justify-between">
          <h2 className="text-sm font-semibold">Incoming messages</h2>
          <span className="text-xs text-surface-800">{items.length} messages</span>
        </div>
        {!items.length && (
          <div className="bg-white border border-surface-200 p-8 text-center text-xs text-surface-800">
            {isMockMode
              ? 'No messages yet. Use the simulation box above to simulate an incoming customer message.'
              : 'No messages yet. Configure Meta webhook after deploying the backend to receive customer messages.'}
          </div>
        )}
        {items.map(item => (
          <article key={item.id} className="bg-white border border-surface-200 p-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-sm font-semibold">{item.customer_name || item.customer_wa_id}</p>
                <p className="text-[11px] text-surface-800">{item.customer_wa_id} · {new Date(item.received_at).toLocaleString()}</p>
              </div>
              <span className={`text-[10px] uppercase font-semibold px-2 py-1 rounded ${
                item.status === 'sent' && isMockMode
                  ? 'bg-amber-100 text-amber-900 border border-amber-300'
                  : 'bg-surface-100 text-surface-800'
              }`}>
                {item.status === 'sent' && isMockMode ? 'Simulated Sent' : item.status.replace('_', ' ')}
              </span>
            </div>
            <div className="bg-surface-50 border border-surface-200 p-3 rounded text-sm whitespace-pre-wrap">{item.inbound_text}</div>
            <label className="block text-xs font-semibold space-y-1">
              AI-suggested reply — review and edit
              <textarea
                rows={3}
                value={drafts[item.id] ?? ''}
                onChange={e => setDrafts(p => ({ ...p, [item.id]: e.target.value }))}
                disabled={item.status === 'sent' || item.status === 'sending'}
                className="block w-full border border-surface-300 p-3 rounded text-sm font-normal"
              />
            </label>
            {item.last_error && <p className="text-xs text-red-700">{item.last_error}</p>}
            {item.status === 'sent' && isMockMode && (
              <p className="text-[11px] text-amber-800 italic">Mock delivery recorded locally — Meta Graph API was not contacted.</p>
            )}
            <div className="flex flex-wrap items-center justify-between gap-2">
              {isMockMode && item.status !== 'needs_review' ? (
                <div className="flex items-center gap-1.5 text-[11px] text-surface-500">
                  <span>Simulate:</span>
                  <button type="button" onClick={() => void triggerSimStatus(item.id, 'send_failed', 'Simulated Meta 131026: Message undeliverable')} className="text-red-700 hover:underline">
                    Failure
                  </button>
                  <span>·</span>
                  <button type="button" onClick={() => void triggerSimStatus(item.id, 'send_ambiguous', 'Simulated network timeout waiting for Meta response')} className="text-amber-800 hover:underline">
                    Timeout
                  </button>
                </div>
              ) : <div />}
              {item.status !== 'sent' && (
                <div className="flex justify-end">
                  <button
                    onClick={() => void send(item)}
                    disabled={busy || item.status === 'sending' || !(drafts[item.id] || '').trim()}
                    className="inline-flex items-center gap-2 bg-emerald-700 text-white px-4 py-2 rounded text-xs font-semibold disabled:opacity-50"
                  >
                    <Send className="w-3.5 h-3.5" />
                    {item.status === 'sending'
                      ? 'Sending…'
                      : item.status === 'send_failed'
                      ? 'Retry send'
                      : item.status === 'send_ambiguous'
                      ? 'Retry send (unconfirmed)'
                      : 'Approve & send reply'}
                  </button>
                </div>
              )}
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}