import React from 'react';
import { Store, MessageSquare, BookOpen, CheckSquare, Settings, LogOut, ShieldCheck, MessageCircle, LifeBuoy } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

interface NavbarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
}

export const Navbar: React.FC<NavbarProps> = ({ activeTab, onTabChange }) => {
  const { user, merchant, logout } = useAuth();

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: Store },
    { id: 'workspace', label: 'AI Workspace', icon: MessageSquare },
    { id: 'context', label: 'Merchant Context', icon: BookOpen },
    { id: 'actions', label: 'Drafts & Actions', icon: CheckSquare },
    { id: 'support', label: 'Support Inbox', icon: LifeBuoy },
    { id: 'whatsapp', label: 'WhatsApp Inbox', icon: MessageCircle },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <header className="bg-slate-900 border-b border-slate-800 text-white sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-emerald-700 flex items-center justify-center font-bold text-white text-sm">
              M
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-semibold tracking-tight text-white text-sm">
                  {merchant?.business_name || 'Magicpin AI Agent'}
                </span>
                <span className="text-[10px] font-medium bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded border border-slate-700">
                  {merchant?.category || 'Merchant'}
                </span>
              </div>
              {user && (
                <div className="text-[10px] text-slate-400">
                  {user.email}
                </div>
              )}
            </div>
          </div>

          <nav className="flex space-x-1" aria-label="Main Navigation">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => onTabChange(item.id)}
                  className={`flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded transition-colors ${
                    isActive
                      ? 'bg-slate-800 text-white border border-slate-700'
                      : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>

          <div className="flex items-center gap-4">
            <div className="hidden md:flex items-center gap-1.5 text-xs text-slate-300">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-[11px]">Protected Session</span>
            </div>
            <button
              onClick={logout}
              title="Sign Out"
              className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded border border-slate-700 bg-slate-800/80 text-slate-300 hover:text-white hover:bg-slate-700 transition-colors"
            >
              <LogOut className="w-3.5 h-3.5 text-slate-400" />
              <span>Sign Out</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};
