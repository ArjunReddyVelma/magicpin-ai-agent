import { useState } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { Navbar } from './components/Navbar';
import { DashboardPage } from './pages/DashboardPage';
import { ContextPage } from './pages/ContextPage';
import { MessageSquare, CheckSquare, Settings } from 'lucide-react';

function AppShell() {
  const { isAuthenticated, isLoading } = useAuth();
  const [authView, setAuthView] = useState<'login' | 'register'>('login');
  const [activeTab, setActiveTab] = useState<string>('dashboard');

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-50 text-surface-900">
        <div className="text-center space-y-3">
          <div className="w-8 h-8 rounded bg-emerald-700 mx-auto flex items-center justify-center text-white font-bold animate-pulse text-sm">
            M
          </div>
          <p className="text-xs font-medium text-surface-800">
            Connecting to merchant workspace...
          </p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    if (authView === 'register') {
      return <RegisterPage onSwitchToLogin={() => setAuthView('login')} />;
    }
    return <LoginPage onSwitchToRegister={() => setAuthView('register')} />;
  }

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
              Persistent context-grounded AI chat with bounded message history and safe retry capabilities.
            </p>
            <button
              onClick={() => setActiveTab('dashboard')}
              className="text-xs font-medium text-emerald-800 underline"
            >
              Return to Dashboard
            </button>
          </div>
        )}

        {activeTab === 'context' && <ContextPage />}

        {activeTab === 'actions' && (
          <div className="bg-white border border-surface-200 rounded p-8 text-center space-y-3">
            <CheckSquare className="w-10 h-10 text-emerald-700 mx-auto" />
            <h2 className="text-base font-semibold text-surface-900">Drafts & Suggested Actions</h2>
            <p className="text-xs text-surface-800 max-w-md mx-auto">
              Merchant-controlled review queue for reply drafts and customer recommendations.
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
              Merchant profile configuration, timezone selection, and account controls.
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

export function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}

export default App;
