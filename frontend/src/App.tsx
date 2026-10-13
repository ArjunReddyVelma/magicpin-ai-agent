import { useState } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { LoginPage } from './pages/LoginPage';
import { RegisterPage } from './pages/RegisterPage';
import { Navbar } from './components/Navbar';
import { DashboardPage } from './pages/DashboardPage';
import { ContextPage } from './pages/ContextPage';
import { WorkspacePage } from './pages/WorkspacePage';
import { ActionsPage } from './pages/ActionsPage';
import { SettingsPage } from './pages/SettingsPage';
import { PrivacyPolicyPage } from './pages/PrivacyPolicyPage';
import { TermsOfServicePage } from './pages/TermsOfServicePage';

function AppShell() {
  const { isAuthenticated, isLoading } = useAuth();
  const [authView, setAuthView] = useState<'login' | 'register' | 'privacy' | 'terms'>('login');
  const [activeTab, setActiveTab] = useState<string>('dashboard');
  const [selectedConvId, setSelectedConvId] = useState<string | null>(null);

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
    if (authView === 'privacy') {
      return <PrivacyPolicyPage onBack={() => setAuthView('login')} />;
    }
    if (authView === 'terms') {
      return <TermsOfServicePage onBack={() => setAuthView('login')} />;
    }
    if (authView === 'register') {
      return (
        <RegisterPage
          onSwitchToLogin={() => setAuthView('login')}
          onViewPrivacy={() => setAuthView('privacy')}
          onViewTerms={() => setAuthView('terms')}
        />
      );
    }
    return (
      <LoginPage
        onSwitchToRegister={() => setAuthView('register')}
        onViewPrivacy={() => setAuthView('privacy')}
        onViewTerms={() => setAuthView('terms')}
      />
    );
  }

  const handleNavigate = (tab: string, convId?: string) => {
    if (convId) {
      setSelectedConvId(convId);
    }
    setActiveTab(tab);
  };

  return (
    <div className="min-h-screen flex flex-col bg-surface-50 text-surface-900">
      <Navbar activeTab={activeTab} onTabChange={setActiveTab} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === 'dashboard' && <DashboardPage onNavigate={handleNavigate} />}

        {activeTab === 'workspace' && <WorkspacePage initialConversationId={selectedConvId} />}

        {activeTab === 'context' && <ContextPage />}

        {activeTab === 'actions' && <ActionsPage />}

        {activeTab === 'settings' && <SettingsPage />}

        {activeTab === 'privacy' && <PrivacyPolicyPage onBack={() => setActiveTab('dashboard')} />}

        {activeTab === 'terms' && <TermsOfServicePage onBack={() => setActiveTab('dashboard')} />}
      </main>

      {/* Product Footer */}
      <footer className="border-t border-surface-200 bg-white py-4 mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between text-[11px] text-surface-800 gap-2">
          <div>Magicpin AI Agent &bull; Standalone Merchant Workspace v1.0</div>
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={() => setActiveTab('privacy')}
              className="hover:text-surface-900 underline"
            >
              Privacy Policy
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('terms')}
              className="hover:text-surface-900 underline"
            >
              Terms of Service
            </button>
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
