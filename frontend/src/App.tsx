import { useState } from 'react';
import { Navbar } from './components/Navbar';
import { DashboardPage } from './pages/DashboardPage';
import { BookOpen, MessageSquare, CheckSquare, Settings } from 'lucide-react';

export function App() {
  const [activeTab, setActiveTab] = useState<string>('dashboard');

  return (
    <div className="min-h-screen flex flex-col bg-surface-50 text-surface-900">
      <Navbar activeTab={activeTab} onTabChange={setActiveTab} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === 'dashboard' && <DashboardPage onNavigate={setActiveTab} />}

        {activeTab === 'workspace' && (
          <div className="bg-white border border-surface-200 rounded p-8 text-center space-y-3">
            <MessageSquare className="w-10 h-10 text-emerald-700 mx-auto" />
            <h2 className="text-base font-semibold text-surface-900">AI Chat Workspace</h2>
            <p className="text-xs text-surface-800 max-w-md mx-auto">
              Persistent context-grounded AI chat with bounded message history will be connected in Phase 5 after authentication and context persistence are established.
            </p>
            <button
              onClick={() => setActiveTab('dashboard')}
              className="text-xs font-medium text-emerald-800 underline"
            >
              Return to Dashboard
            </button>
          </div>
        )}

        {activeTab === 'context' && (
          <div className="bg-white border border-surface-200 rounded p-8 text-center space-y-3">
            <BookOpen className="w-10 h-10 text-emerald-700 mx-auto" />
            <h2 className="text-base font-semibold text-surface-900">Merchant Context Management</h2>
            <p className="text-xs text-surface-800 max-w-md mx-auto">
              CRUD interface for FAQs, policies, and business facts with optimistic version concurrency will be enabled in Phase 4.
            </p>
            <button
              onClick={() => setActiveTab('dashboard')}
              className="text-xs font-medium text-emerald-800 underline"
            >
              Return to Dashboard
            </button>
          </div>
        )}

        {activeTab === 'actions' && (
          <div className="bg-white border border-surface-200 rounded p-8 text-center space-y-3">
            <CheckSquare className="w-10 h-10 text-emerald-700 mx-auto" />
            <h2 className="text-base font-semibold text-surface-900">Drafts & Suggested Actions</h2>
            <p className="text-xs text-surface-800 max-w-md mx-auto">
              Merchant-controlled review queue for reply drafts and recommendations will be connected in Phase 7.
            </p>
            <button
              onClick={() => setActiveTab('dashboard')}
              className="text-xs font-medium text-emerald-800 underline"
            >
              Return to Dashboard
            </button>
          </div>
        )}

        {activeTab === 'settings' && (
          <div className="bg-white border border-surface-200 rounded p-8 text-center space-y-3">
            <Settings className="w-10 h-10 text-emerald-700 mx-auto" />
            <h2 className="text-base font-semibold text-surface-900">Merchant Settings</h2>
            <p className="text-xs text-surface-800 max-w-md mx-auto">
              Merchant profile configuration, timezone selection, and password security management.
            </p>
            <button
              onClick={() => setActiveTab('dashboard')}
              className="text-xs font-medium text-emerald-800 underline"
            >
              Return to Dashboard
            </button>
          </div>
        )}
      </main>

      {/* Product Footer */}
      <footer className="border-t border-surface-200 bg-white py-4 mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between text-[11px] text-surface-800 gap-2">
          <div>Magicpin AI Agent &bull; Standalone Merchant Workspace v1.0</div>
          <div className="flex items-center gap-4">
            <a href="#privacy" className="hover:text-surface-900 underline">Privacy Policy</a>
            <a href="#terms" className="hover:text-surface-900 underline">Terms of Service</a>
            <span>Isolated Merchant Deployment</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
