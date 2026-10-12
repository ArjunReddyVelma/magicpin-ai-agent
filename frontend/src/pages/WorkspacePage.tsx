import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  MessageSquare,
  Plus,
  Search,
  RefreshCw,
  AlertCircle,
  Archive,
  ArchiveRestore,
  Trash2,
  Edit2,
  Send,
  Loader2,
  Clock,
  BookOpen,
  AlertTriangle,
  X,
  ChevronDown,
} from 'lucide-react';
import { api, ApiClientError } from '../api/client';
import { Conversation, Message, ContextUsedItem } from '../types/api';

function generateUUID(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

interface WorkspacePageProps {
  initialConversationId?: string | null;
}

export const WorkspacePage: React.FC<WorkspacePageProps> = ({ initialConversationId }) => {
  // Conversation List State
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoadingConversations, setIsLoadingConversations] = useState(true);
  const [conversationsError, setConversationsError] = useState<string | null>(null);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(initialConversationId || null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'archived'>('all');
  const [searchQuery, setSearchQuery] = useState('');

  // Messages State
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [messagesError, setMessagesError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalMessages, setTotalMessages] = useState(0);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  // Composer State
  const [draftContent, setDraftContent] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const [retryingMessageId, setRetryingMessageId] = useState<string | null>(null);

  // Modal States
  const [isNewModalOpen, setIsNewModalOpen] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [createModalError, setCreateModalError] = useState<string | null>(null);

  const [isRenameModalOpen, setIsRenameModalOpen] = useState(false);
  const [renameTitle, setRenameTitle] = useState('');
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameModalError, setRenameModalError] = useState<string | null>(null);

  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [deletingConv, setDeletingConv] = useState<Conversation | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteModalError, setDeleteModalError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const selectedConversation = conversations.find((c) => c.id === selectedConversationId) || null;

  // Auto-scroll messages to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Fetch conversations
  const fetchConversations = useCallback(async () => {
    setIsLoadingConversations(true);
    setConversationsError(null);
    try {
      const res = await api.listConversations({
        status: statusFilter === 'all' ? undefined : statusFilter,
        query: searchQuery.trim() || undefined,
        page: 1,
        page_size: 50,
      });
      setConversations(res.items);

      // Auto-select first conversation if none selected or selected was deleted
      if (res.items.length > 0) {
        if (!selectedConversationId || !res.items.some((c) => c.id === selectedConversationId)) {
          setSelectedConversationId(res.items[0].id);
        }
      } else {
        setSelectedConversationId(null);
      }
    } catch (err) {
      if (err instanceof ApiClientError) {
        setConversationsError(err.message);
      } else {
        setConversationsError('Failed to load conversations.');
      }
    } finally {
      setIsLoadingConversations(false);
    }
  }, [statusFilter, searchQuery, selectedConversationId]);

  useEffect(() => {
    fetchConversations();
  }, [statusFilter, searchQuery]);

  // Fetch messages for active conversation
  const fetchMessages = useCallback(async (conversationId: string, page = 1) => {
    if (page === 1) {
      setIsLoadingMessages(true);
      setMessages([]);
    } else {
      setIsLoadingMore(true);
    }
    setMessagesError(null);
    setSendError(null);

    try {
      const res = await api.listMessages(conversationId, {
        page,
        page_size: 50,
      });

      if (page === 1) {
        setMessages(res.items);
      } else {
        // Prepend older messages
        setMessages((prev) => [...res.items, ...prev]);
      }
      setTotalMessages(res.total);
      setCurrentPage(page);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setMessagesError(err.message);
      } else {
        setMessagesError('Failed to load message history.');
      }
    } finally {
      setIsLoadingMessages(false);
      setIsLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    if (selectedConversationId) {
      fetchMessages(selectedConversationId, 1);
    } else {
      setMessages([]);
      setTotalMessages(0);
    }
  }, [selectedConversationId]);

  useEffect(() => {
    if (messages.length > 0 && currentPage === 1) {
      scrollToBottom();
    }
  }, [messages.length, currentPage]);

  // Load older messages
  const handleLoadMoreMessages = () => {
    if (!selectedConversationId || isLoadingMore) return;
    const nextPage = currentPage + 1;
    fetchMessages(selectedConversationId, nextPage);
  };

  // Create Conversation
  const handleCreateConversation = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newTitle.trim();
    if (!trimmed) {
      setCreateModalError('Conversation title cannot be empty.');
      return;
    }
    if (trimmed.length > 200) {
      setCreateModalError('Title must not exceed 200 characters.');
      return;
    }

    setIsCreating(true);
    setCreateModalError(null);
    try {
      const created = await api.createConversation(trimmed);
      setConversations((prev) => [created, ...prev]);
      setSelectedConversationId(created.id);
      setIsNewModalOpen(false);
      setNewTitle('');
    } catch (err) {
      if (err instanceof ApiClientError) {
        setCreateModalError(err.message);
      } else {
        setCreateModalError('Failed to create conversation.');
      }
    } finally {
      setIsCreating(false);
    }
  };

  // Rename Conversation
  const handleRenameConversation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedConversation) return;

    const trimmed = renameTitle.trim();
    if (!trimmed) {
      setRenameModalError('Conversation title cannot be empty.');
      return;
    }
    if (trimmed.length > 200) {
      setRenameModalError('Title must not exceed 200 characters.');
      return;
    }

    setIsRenaming(true);
    setRenameModalError(null);
    try {
      const updated = await api.updateConversation(selectedConversation.id, { title: trimmed });
      setConversations((prev) =>
        prev.map((c) => (c.id === updated.id ? { ...c, title: updated.title } : c))
      );
      setIsRenameModalOpen(false);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setRenameModalError(err.message);
      } else {
        setRenameModalError('Failed to rename conversation.');
      }
    } finally {
      setIsRenaming(false);
    }
  };

  // Toggle Archive Status
  const handleToggleArchive = async (conv: Conversation) => {
    const targetStatus = conv.status === 'active' ? 'archived' : 'active';
    try {
      const updated = await api.updateConversation(conv.id, { status: targetStatus });
      setConversations((prev) =>
        prev.map((c) => (c.id === updated.id ? { ...c, status: updated.status } : c))
      );
    } catch (err) {
      if (err instanceof ApiClientError) {
        alert(`Failed to update conversation status: ${err.message}`);
      } else {
        alert('Failed to update conversation status.');
      }
    }
  };

  // Delete Conversation
  const handleDeleteConversation = async () => {
    if (!deletingConv) return;
    setIsDeleting(true);
    setDeleteModalError(null);
    try {
      await api.deleteConversation(deletingConv.id);
      setConversations((prev) => prev.filter((c) => c.id !== deletingConv.id));
      if (selectedConversationId === deletingConv.id) {
        const remaining = conversations.filter((c) => c.id !== deletingConv.id);
        setSelectedConversationId(remaining.length > 0 ? remaining[0].id : null);
      }
      setIsDeleteModalOpen(false);
      setDeletingConv(null);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setDeleteModalError(err.message);
      } else {
        setDeleteModalError('Failed to delete conversation.');
      }
    } finally {
      setIsDeleting(false);
    }
  };

  // Send Message
  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!selectedConversationId || !selectedConversation) return;

    if (selectedConversation.status === 'archived') {
      setSendError('Cannot send messages to an archived conversation.');
      return;
    }

    const trimmed = draftContent.trim();
    if (!trimmed) return;

    if (trimmed.length > 4000) {
      setSendError('Message content cannot exceed 4000 characters.');
      return;
    }

    if (isSending) return; // Prevent duplicate submissions

    setIsSending(true);
    setSendError(null);

    const idempotencyKey = generateUUID();

    try {
      const response = await api.sendMessage(selectedConversationId, {
        content: trimmed,
        idempotency_key: idempotencyKey,
      });

      // Append user and assistant messages
      setMessages((prev) => [...prev, response.user_message, response.assistant_message]);
      setTotalMessages((prev) => prev + 2);
      setDraftContent(''); // Clear draft only on success

      // Update conversation last_message_at
      setConversations((prev) =>
        prev.map((c) =>
          c.id === selectedConversationId
            ? { ...c, last_message_at: response.assistant_message.created_at }
            : c
        )
      );
      scrollToBottom();
    } catch (err) {
      if (err instanceof ApiClientError) {
        if (err.statusCode === 502) {
          // LLM Provider failure: user message was persisted as 'failed' in backend
          const failedId = (err.details as Record<string, unknown>)?.failed_message_id as string | undefined;
          setSendError(
            err.message || 'AI service is temporarily unavailable. Your message failed and can be retried.'
          );
          // Refresh message history to surface the persisted failed turn
          if (failedId) {
            fetchMessages(selectedConversationId, 1);
          }
        } else {
          setSendError(err.message);
        }
      } else {
        setSendError('Network error. Unable to send message.');
      }
      // Note: draftContent is preserved on error so merchant does not lose unsent input!
    } finally {
      setIsSending(false);
    }
  };

  // Retry Failed Message
  const handleRetryMessage = async (failedMsg: Message) => {
    if (!selectedConversationId || !selectedConversation) return;

    if (selectedConversation.status === 'archived') {
      setSendError('Cannot retry messages in an archived conversation.');
      return;
    }

    setRetryingMessageId(failedMsg.id);
    setSendError(null);

    const retryIdempotencyKey = generateUUID();

    try {
      const response = await api.sendMessage(selectedConversationId, {
        content: failedMsg.content,
        retry_message_id: failedMsg.id,
        idempotency_key: retryIdempotencyKey,
      });

      // Update user message to 'complete' and append assistant message
      setMessages((prev) => [
        ...prev.map((m) => (m.id === failedMsg.id ? response.user_message : m)),
        response.assistant_message,
      ]);
      setTotalMessages((prev) => prev + 1);

      // Update conversation last_message_at
      setConversations((prev) =>
        prev.map((c) =>
          c.id === selectedConversationId
            ? { ...c, last_message_at: response.assistant_message.created_at }
            : c
        )
      );
      scrollToBottom();
    } catch (err) {
      if (err instanceof ApiClientError) {
        setSendError(`Retry failed: ${err.message}`);
      } else {
        setSendError('Network error during retry.');
      }
    } finally {
      setRetryingMessageId(null);
    }
  };

  // Keyboard shortcut: Enter to send, Shift+Enter for new line
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="flex flex-col lg:flex-row h-[calc(100vh-8.5rem)] bg-white border border-surface-200 rounded shadow-sm overflow-hidden">
      {/* Sidebar: Conversations List */}
      <div className="w-full lg:w-80 flex-shrink-0 border-r border-surface-200 flex flex-col bg-surface-50/50">
        {/* Sidebar Header */}
        <div className="p-3 border-b border-surface-200 space-y-2.5 bg-white">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <MessageSquare className="w-4 h-4 text-emerald-700" />
              <h2 className="text-xs font-semibold uppercase tracking-wider text-surface-900">
                Conversations
              </h2>
            </div>
            <button
              onClick={() => {
                setNewTitle('New Conversation');
                setCreateModalError(null);
                setIsNewModalOpen(true);
              }}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-emerald-800 bg-emerald-50 hover:bg-emerald-100 border border-emerald-300 rounded transition-colors"
              title="Start New Conversation"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>New Chat</span>
            </button>
          </div>

          {/* Search Input */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-surface-800 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search conversations..."
              className="w-full pl-8 pr-3 py-1.5 text-xs bg-surface-50 border border-surface-200 rounded focus:outline-none focus:ring-1 focus:ring-emerald-600 focus:bg-white text-surface-900 placeholder:text-surface-800"
            />
          </div>

          {/* Status Tabs */}
          <div className="flex rounded border border-surface-200 bg-surface-100 p-0.5 text-[11px]">
            {(['all', 'active', 'archived'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setStatusFilter(tab)}
                className={`flex-1 py-1 font-medium capitalize rounded transition-colors ${
                  statusFilter === tab
                    ? 'bg-white text-surface-900 shadow-xs'
                    : 'text-surface-800 hover:text-surface-900'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>

        {/* Sidebar List */}
        <div className="flex-1 overflow-y-auto divide-y divide-surface-100">
          {isLoadingConversations ? (
            <div className="p-6 text-center text-xs text-surface-800">
              <RefreshCw className="w-4 h-4 animate-spin mx-auto mb-2 text-surface-800" />
              Loading conversations...
            </div>
          ) : conversationsError ? (
            <div className="p-4 m-3 rounded bg-red-50 border border-red-200 text-xs text-red-800 space-y-2">
              <div className="flex items-center gap-1.5">
                <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
                <span className="font-medium">Failed to load</span>
              </div>
              <p className="text-[11px] text-red-700">{conversationsError}</p>
              <button
                onClick={fetchConversations}
                className="text-[11px] font-semibold underline text-red-900"
              >
                Try Again
              </button>
            </div>
          ) : conversations.length === 0 ? (
            <div className="p-6 text-center text-xs text-surface-800 space-y-2">
              <MessageSquare className="w-6 h-6 text-surface-800 mx-auto" />
              <p className="font-medium text-surface-900">No conversations</p>
              <p className="text-[11px] text-surface-800 max-w-[200px] mx-auto">
                {searchQuery
                  ? 'No conversations match your search filter.'
                  : 'Start a conversation to query store policies with AI.'}
              </p>
            </div>
          ) : (
            conversations.map((conv) => {
              const isSelected = conv.id === selectedConversationId;
              return (
                <div
                  key={conv.id}
                  onClick={() => setSelectedConversationId(conv.id)}
                  className={`p-3 cursor-pointer text-left transition-colors relative ${
                    isSelected
                      ? 'bg-emerald-50/70 border-l-3 border-emerald-700'
                      : 'hover:bg-surface-100/70'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className={`text-xs font-semibold truncate ${isSelected ? 'text-emerald-950' : 'text-surface-900'}`}>
                      {conv.title}
                    </p>
                    <span
                      className={`text-[9px] uppercase font-bold px-1.5 py-0.5 rounded border shrink-0 ${
                        conv.status === 'active'
                          ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                          : 'bg-slate-100 text-slate-700 border-slate-300'
                      }`}
                    >
                      {conv.status}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-surface-800 mt-1">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3 text-surface-800" />
                      {conv.last_message_at
                        ? new Date(conv.last_message_at).toLocaleDateString([], {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })
                        : new Date(conv.created_at).toLocaleDateString([], {
                            month: 'short',
                            day: 'numeric',
                          })}
                    </span>

                    <div className="flex items-center gap-1 opacity-70 hover:opacity-100">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleToggleArchive(conv);
                        }}
                        title={conv.status === 'active' ? 'Archive conversation' : 'Activate conversation'}
                        className="p-1 hover:text-surface-900 rounded"
                      >
                        {conv.status === 'active' ? (
                          <Archive className="w-3 h-3 text-surface-800" />
                        ) : (
                          <ArchiveRestore className="w-3 h-3 text-emerald-700" />
                        )}
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeletingConv(conv);
                          setDeleteModalError(null);
                          setIsDeleteModalOpen(true);
                        }}
                        title="Delete conversation"
                        className="p-1 hover:text-red-700 rounded"
                      >
                        <Trash2 className="w-3 h-3 text-surface-800 hover:text-red-600" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col bg-surface-50/20 overflow-hidden">
        {selectedConversation ? (
          <>
            {/* Conversation Header */}
            <div className="p-3.5 border-b border-surface-200 bg-white flex items-center justify-between gap-3 shadow-2xs">
              <div className="min-w-0 flex-1 flex items-center gap-2.5">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h1 className="text-sm font-semibold text-surface-900 truncate">
                      {selectedConversation.title}
                    </h1>
                    <button
                      onClick={() => {
                        setRenameTitle(selectedConversation.title);
                        setRenameModalError(null);
                        setIsRenameModalOpen(true);
                      }}
                      className="text-surface-800 hover:text-emerald-800 p-1 rounded"
                      title="Rename conversation"
                    >
                      <Edit2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div className="flex items-center gap-2 text-[11px] text-surface-800">
                    <span
                      className={`font-medium ${
                        selectedConversation.status === 'active'
                          ? 'text-emerald-700'
                          : 'text-slate-600'
                      }`}
                    >
                      Status: {selectedConversation.status}
                    </span>
                    <span>•</span>
                    <span>
                      Created: {new Date(selectedConversation.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              </div>

              {/* Actions Header */}
              <div className="flex items-center gap-1.5 shrink-0">
                <button
                  onClick={() => handleToggleArchive(selectedConversation)}
                  className={`inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded border transition-colors ${
                    selectedConversation.status === 'active'
                      ? 'bg-surface-50 text-surface-800 hover:bg-surface-100 border-surface-300'
                      : 'bg-emerald-50 text-emerald-800 hover:bg-emerald-100 border-emerald-300'
                  }`}
                >
                  {selectedConversation.status === 'active' ? (
                    <>
                      <Archive className="w-3.5 h-3.5" />
                      <span>Archive</span>
                    </>
                  ) : (
                    <>
                      <ArchiveRestore className="w-3.5 h-3.5" />
                      <span>Activate</span>
                    </>
                  )}
                </button>

                <button
                  onClick={() => {
                    setDeletingConv(selectedConversation);
                    setDeleteModalError(null);
                    setIsDeleteModalOpen(true);
                  }}
                  className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-red-700 hover:text-red-800 bg-red-50 hover:bg-red-100 border border-red-200 rounded transition-colors"
                  title="Delete conversation"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Delete</span>
                </button>
              </div>
            </div>

            {/* Archived Warning Banner */}
            {selectedConversation.status === 'archived' && (
              <div className="bg-amber-50 border-b border-amber-200 px-4 py-2 flex items-center justify-between text-xs text-amber-900">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-700 shrink-0" />
                  <span>
                    This conversation is archived. Message sending is disabled unless reactivated.
                  </span>
                </div>
                <button
                  onClick={() => handleToggleArchive(selectedConversation)}
                  className="font-semibold underline hover:text-amber-950"
                >
                  Reactivate Conversation
                </button>
              </div>
            )}

            {/* Messages Viewport */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {/* Pagination / Load More */}
              {totalMessages > messages.length && (
                <div className="text-center py-1">
                  <button
                    onClick={handleLoadMoreMessages}
                    disabled={isLoadingMore}
                    className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium text-surface-800 bg-white border border-surface-200 hover:bg-surface-50 rounded shadow-xs transition-colors"
                  >
                    {isLoadingMore ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-surface-800" />
                    ) : (
                      <ChevronDown className="w-3.5 h-3.5 rotate-180" />
                    )}
                    <span>Load earlier messages ({totalMessages - messages.length} remaining)</span>
                  </button>
                </div>
              )}

              {isLoadingMessages ? (
                <div className="py-16 text-center text-xs text-surface-800 space-y-2">
                  <Loader2 className="w-6 h-6 animate-spin mx-auto text-emerald-700" />
                  <p>Loading conversation messages...</p>
                </div>
              ) : messagesError ? (
                <div className="p-4 rounded bg-red-50 border border-red-200 text-xs text-red-800 space-y-2">
                  <div className="flex items-center gap-1.5">
                    <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
                    <span className="font-semibold">Unable to load messages</span>
                  </div>
                  <p>{messagesError}</p>
                  <button
                    onClick={() => fetchMessages(selectedConversation.id, 1)}
                    className="font-semibold underline text-red-900"
                  >
                    Retry loading
                  </button>
                </div>
              ) : messages.length === 0 ? (
                <div className="py-16 text-center max-w-md mx-auto space-y-3">
                  <div className="w-10 h-10 rounded-full bg-emerald-50 border border-emerald-200 flex items-center justify-center mx-auto text-emerald-700">
                    <MessageSquare className="w-5 h-5" />
                  </div>
                  <h3 className="text-sm font-semibold text-surface-900">
                    Grounded AI Assistant Ready
                  </h3>
                  <p className="text-xs text-surface-800 leading-relaxed">
                    Ask questions regarding your business policies, return conditions, menu facts,
                    operating hours, or customer inquiries. Answers are strictly grounded in your active
                    business context items.
                  </p>
                </div>
              ) : (
                messages.map((msg) => {
                  const isUser = msg.role === 'user';
                  const isFailed = msg.status === 'failed';
                  const isRetrying = retryingMessageId === msg.id;

                  // Extract sources from context_metadata if present
                  const sources: ContextUsedItem[] =
                    (msg.context_metadata as { sources?: ContextUsedItem[] })?.sources || [];

                  return (
                    <div
                      key={msg.id}
                      className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
                    >
                      <div className="flex items-center gap-1.5 text-[10px] text-surface-800 mb-1 px-1">
                        <span className="font-semibold uppercase tracking-wider">
                          {isUser ? 'Merchant' : 'Assistant'}
                        </span>
                        <span>•</span>
                        <span>
                          {new Date(msg.created_at).toLocaleTimeString([], {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                        {!isUser && msg.model && (
                          <>
                            <span>•</span>
                            <span className="font-mono text-surface-800">{msg.model}</span>
                          </>
                        )}
                      </div>

                      {/* Message Bubble */}
                      <div
                        className={`max-w-[85%] sm:max-w-[75%] rounded p-3.5 text-xs leading-relaxed space-y-2 ${
                          isUser
                            ? isFailed
                              ? 'bg-red-50/80 border border-red-300 text-red-950'
                              : 'bg-surface-100 text-surface-900 border border-surface-200'
                            : 'bg-white text-surface-900 border border-surface-200 shadow-xs'
                        }`}
                      >
                        <p className="whitespace-pre-wrap">{msg.content}</p>

                        {/* User Failed State with Retry affordance */}
                        {isUser && isFailed && (
                          <div className="pt-2 border-t border-red-200 flex items-center justify-between gap-3 text-[11px]">
                            <div className="flex items-center gap-1.5 text-red-700 font-medium">
                              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                              <span>Generation failed</span>
                            </div>
                            <button
                              onClick={() => handleRetryMessage(msg)}
                              disabled={isRetrying || selectedConversation.status === 'archived'}
                              className="inline-flex items-center gap-1 px-2 py-0.5 font-semibold text-xs bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 rounded transition-colors shadow-2xs"
                              title="Safely re-attempt generation for this message"
                            >
                              {isRetrying ? (
                                <>
                                  <Loader2 className="w-3 h-3 animate-spin" />
                                  <span>Retrying...</span>
                                </>
                              ) : (
                                <>
                                  <RefreshCw className="w-3 h-3" />
                                  <span>Retry Turn</span>
                                </>
                              )}
                            </button>
                          </div>
                        )}

                        {/* Assistant Grounding / Context Sources Metadata */}
                        {!isUser && sources.length > 0 && (
                          <div className="pt-2 mt-2 border-t border-surface-100 space-y-1.5">
                            <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-800">
                              <BookOpen className="w-3 h-3 text-emerald-700" />
                              <span>Context Grounding ({sources.length} sources used)</span>
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                              {sources.map((src, idx) => (
                                <span
                                  key={src.context_id || idx}
                                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-50 border border-emerald-200 text-[10px] font-medium text-emerald-900"
                                >
                                  <span className="text-emerald-700 uppercase text-[9px] font-bold">
                                    [{src.item_type}]
                                  </span>
                                  <span>{src.title}</span>
                                  <span className="text-emerald-600 text-[9px]">v{src.version}</span>
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })
              )}

              {/* In-flight Sending User Indicator */}
              {isSending && (
                <div className="flex flex-col items-end">
                  <div className="flex items-center gap-1.5 text-[10px] text-surface-800 mb-1 px-1">
                    <span className="font-semibold uppercase tracking-wider">Merchant</span>
                    <span>•</span>
                    <span>Sending...</span>
                  </div>
                  <div className="max-w-[75%] rounded p-3.5 text-xs leading-relaxed bg-surface-100 text-surface-900 border border-surface-200 opacity-80">
                    <p className="whitespace-pre-wrap">{draftContent}</p>
                    <div className="pt-2 mt-2 border-t border-surface-200 flex items-center gap-2 text-[11px] text-surface-800">
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-emerald-700" />
                      <span>Grounding with merchant context and generating response...</span>
                    </div>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Send Error Alert */}
            {sendError && (
              <div className="mx-4 mb-2 p-2.5 rounded bg-red-50 border border-red-200 text-xs text-red-800 flex items-center justify-between gap-2 shadow-2xs">
                <div className="flex items-center gap-1.5">
                  <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
                  <span>{sendError}</span>
                </div>
                <button
                  onClick={() => setSendError(null)}
                  className="text-red-700 hover:text-red-900 p-0.5 rounded"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {/* Message Composer Area */}
            <div className="p-3.5 border-t border-surface-200 bg-white">
              <form onSubmit={handleSendMessage} className="space-y-2">
                <div className="relative">
                  <textarea
                    ref={textareaRef}
                    rows={3}
                    value={draftContent}
                    onChange={(e) => setDraftContent(e.target.value)}
                    onKeyDown={handleKeyDown}
                    disabled={isSending || selectedConversation.status === 'archived'}
                    placeholder={
                      selectedConversation.status === 'archived'
                        ? 'This conversation is archived. Re-activate it to send messages.'
                        : 'Ask a question or simulate customer queries grounded on your store facts... (Press Enter to send, Shift+Enter for newline)'
                    }
                    className="w-full p-2.5 text-xs bg-surface-50 border border-surface-200 rounded focus:outline-none focus:ring-1 focus:ring-emerald-600 focus:bg-white text-surface-900 placeholder:text-surface-800 resize-none disabled:opacity-60 disabled:cursor-not-allowed"
                    maxLength={4000}
                  />

                  <div className="absolute right-2.5 bottom-2.5 flex items-center gap-2 text-[11px] text-surface-800 pointer-events-none">
                    <span>{draftContent.length} / 4000</span>
                  </div>
                </div>

                <div className="flex items-center justify-between text-xs">
                  <p className="text-[11px] text-surface-800">
                    Answers adhere strictly to active merchant context policies and facts.
                  </p>

                  <button
                    type="submit"
                    disabled={
                      !draftContent.trim() ||
                      isSending ||
                      selectedConversation.status === 'archived'
                    }
                    className="inline-flex items-center gap-1.5 px-4 py-2 font-medium text-white bg-emerald-700 hover:bg-emerald-800 disabled:opacity-50 disabled:cursor-not-allowed rounded transition-colors shadow-2xs"
                  >
                    {isSending ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>Sending...</span>
                      </>
                    ) : (
                      <>
                        <Send className="w-3.5 h-3.5" />
                        <span>Send Message</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center space-y-3">
            <div className="w-12 h-12 rounded-full bg-surface-100 border border-surface-200 flex items-center justify-center text-surface-800">
              <MessageSquare className="w-6 h-6" />
            </div>
            <h2 className="text-sm font-semibold text-surface-900">No Conversation Selected</h2>
            <p className="text-xs text-surface-800 max-w-sm">
              Select an existing conversation from the sidebar or start a new one to query your store's
              grounded knowledge.
            </p>
            <button
              onClick={() => {
                setNewTitle('New Conversation');
                setCreateModalError(null);
                setIsNewModalOpen(true);
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-emerald-800 bg-emerald-50 hover:bg-emerald-100 border border-emerald-300 rounded transition-colors shadow-2xs"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Start New Conversation</span>
            </button>
          </div>
        )}
      </div>

      {/* Modal: Create Conversation */}
      {isNewModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded border border-surface-200 shadow-lg max-w-sm w-full p-5 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-surface-100">
              <h3 className="text-xs font-bold uppercase tracking-wider text-surface-900">
                New Conversation
              </h3>
              <button
                onClick={() => setIsNewModalOpen(false)}
                className="text-surface-800 hover:text-surface-900"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {createModalError && (
              <div className="p-2.5 rounded bg-red-50 border border-red-200 text-xs text-red-800">
                {createModalError}
              </div>
            )}

            <form onSubmit={handleCreateConversation} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-surface-900 mb-1">
                  Conversation Title
                </label>
                <input
                  type="text"
                  required
                  maxLength={200}
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="e.g., Return Policy Query, Catering Inquiry"
                  className="w-full px-3 py-1.5 text-xs bg-surface-50 border border-surface-200 rounded focus:outline-none focus:ring-1 focus:ring-emerald-600 focus:bg-white text-surface-900"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsNewModalOpen(false)}
                  className="px-3 py-1.5 text-xs font-medium text-surface-800 hover:text-surface-900 rounded border border-surface-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isCreating || !newTitle.trim()}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-emerald-700 hover:bg-emerald-800 disabled:opacity-50 rounded shadow-xs"
                >
                  {isCreating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                  <span>Create Conversation</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Rename Conversation */}
      {isRenameModalOpen && selectedConversation && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded border border-surface-200 shadow-lg max-w-sm w-full p-5 space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-surface-100">
              <h3 className="text-xs font-bold uppercase tracking-wider text-surface-900">
                Rename Conversation
              </h3>
              <button
                onClick={() => setIsRenameModalOpen(false)}
                className="text-surface-800 hover:text-surface-900"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {renameModalError && (
              <div className="p-2.5 rounded bg-red-50 border border-red-200 text-xs text-red-800">
                {renameModalError}
              </div>
            )}

            <form onSubmit={handleRenameConversation} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-surface-900 mb-1">
                  Title
                </label>
                <input
                  type="text"
                  required
                  maxLength={200}
                  value={renameTitle}
                  onChange={(e) => setRenameTitle(e.target.value)}
                  className="w-full px-3 py-1.5 text-xs bg-surface-50 border border-surface-200 rounded focus:outline-none focus:ring-1 focus:ring-emerald-600 focus:bg-white text-surface-900"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsRenameModalOpen(false)}
                  className="px-3 py-1.5 text-xs font-medium text-surface-800 hover:text-surface-900 rounded border border-surface-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isRenaming || !renameTitle.trim()}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-emerald-700 hover:bg-emerald-800 disabled:opacity-50 rounded shadow-xs"
                >
                  {isRenaming ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                  <span>Save Title</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Delete Confirmation */}
      {isDeleteModalOpen && deletingConv && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded border border-surface-200 shadow-lg max-w-sm w-full p-5 space-y-4">
            <div className="flex items-center gap-2 text-red-700">
              <AlertCircle className="w-5 h-5 shrink-0" />
              <h3 className="text-sm font-semibold">Delete Conversation</h3>
            </div>

            <p className="text-xs text-surface-800 leading-relaxed">
              Are you sure you want to permanently delete{' '}
              <strong className="text-surface-900">"{deletingConv.title}"</strong> and all its
              associated messages? This action is irreversible.
            </p>

            {deleteModalError && (
              <div className="p-2.5 rounded bg-red-50 border border-red-200 text-xs text-red-800">
                {deleteModalError}
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => {
                  setIsDeleteModalOpen(false);
                  setDeletingConv(null);
                }}
                className="px-3 py-1.5 text-xs font-medium text-surface-800 hover:text-surface-900 rounded border border-surface-200"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteConversation}
                disabled={isDeleting}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-red-700 hover:bg-red-800 disabled:opacity-50 rounded shadow-xs"
              >
                {isDeleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                <span>Delete Permanently</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
