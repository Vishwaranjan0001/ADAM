'use client';

import { useState, useEffect } from 'react';
import IconRail, { type NavTab } from '@/components/IconRail';
import ChatWindow from '@/components/ChatWindow';
import ConversationHistory from '@/components/ConversationHistory';
import DocumentsView from '@/components/DocumentsView';
import PrecedentsView from '@/components/PrecedentsView';
import AuditView from '@/components/AuditView';
import SourcesView from '@/components/SourcesView';
import ReviewView from '@/components/ReviewView';
import SettingsModal from '@/components/SettingsModal';
import { Sparkles, ChevronDown, Search, Plus, Check, Shield } from 'lucide-react';
import type { DepartmentItem, ModelInfo } from '@/lib/types';
import { fetchModels, fetchVocabularies } from '@/lib/api';

const DEFAULT_OFFICER_ID = 'officer_dev_001';

export default function HomePage() {
  const [activeNavTab, setActiveNavTab] = useState<NavTab>('home');
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Officer Identity & Clearance State
  const [officerUserId, setOfficerUserId] = useState(DEFAULT_OFFICER_ID);
  const [clearanceLevel, setClearanceLevel] = useState('PUBLIC');
  const [departmentId, setDepartmentId] = useState('ALL');

  // Real Backend Data State
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<ModelInfo | null>(null);
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [departments, setDepartments] = useState<DepartmentItem[]>([]);
  const [searchFilter, setSearchFilter] = useState('');

  // Initial Load from API
  useEffect(() => {
    const loadModels = () => {
      void fetchModels().then((mList) => {
        setModels(mList);
        const installed = mList.filter((m) => m.is_installed);
        setSelectedModel((current) => {
          if (current && installed.some((model) => model.id === current.id)) return current;
          return installed.find((model) => model.is_primary) || installed[0] || mList.find((model) => model.is_primary) || null;
        });
      });
    };
    loadModels();
    const modelRefresh = window.setInterval(loadModels, 15_000);

    fetchVocabularies().then((v) => {
      setDepartments(v.departments || []);
    });
    return () => window.clearInterval(modelRefresh);
  }, []);

  const handleNewThread = () => {
    setActiveNavTab('home');
    setActiveSessionId(null);
    setIsHistoryOpen(false);
  };

  return (
    <main className="w-screen h-screen min-h-[600px] bg-[#f8fafc] overflow-hidden">
      <div className="w-full h-full bg-white flex overflow-hidden relative">
        {/* Left Navigation Rail */}
        <IconRail
          activeTab={activeNavTab}
          onSelectTab={(tab) => {
            setActiveNavTab(tab);
            setIsHistoryOpen(false);
          }}
          onToggleHistory={() => setIsHistoryOpen((v) => !v)}
          isHistoryOpen={isHistoryOpen}
          onOpenSettings={() => setSettingsOpen(true)}
          userName={officerUserId}
          clearanceLevel={clearanceLevel}
        />

        {/* Slide-out Session History Drawer */}
        {isHistoryOpen && (
          <ConversationHistory
            userId={officerUserId}
            activeSessionId={activeSessionId}
            onSelectSession={(id) => {
              setActiveSessionId(id);
              setActiveNavTab('home');
              setIsHistoryOpen(false);
            }}
            onClose={() => setIsHistoryOpen(false)}
            searchFilter={searchFilter}
          />
        )}

        {/* Main Application Area */}
        <div className="flex-1 flex flex-col h-full overflow-hidden">
          {/* Top Header Bar */}
          <header className="h-[68px] px-4 sm:px-6 border-b border-[#eaecf0] flex items-center justify-between bg-white shrink-0 z-10">
            {/* Installed artifacts are selectable; unavailable artifacts remain visible but frozen. */}
            <div className="relative">
              <button
                type="button"
                onClick={() => setModelDropdownOpen((open) => !open)}
                className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-[#e4e7ec] bg-white hover:border-purple-200 hover:bg-purple-50/40 text-xs font-medium text-gray-700 shadow-sm transition-all"
                title="Select an installed model"
              >
                <Sparkles className="w-3.5 h-3.5 text-purple-600" />
                <span className="font-semibold">{selectedModel?.name || 'ADAM model'}</span>
                {selectedModel?.quantization && (
                  <span className="px-1.5 py-0.5 rounded bg-gray-100 text-[10px] font-mono text-gray-500">
                    {selectedModel.quantization}
                  </span>
                )}
                <ChevronDown className="w-3 h-3 text-gray-400" />
              </button>
              {modelDropdownOpen && (
                <div className="absolute left-0 top-full mt-2 w-80 bg-white rounded-2xl border border-[#eaecf0] shadow-[0_16px_36px_rgba(16,24,40,0.12)] py-1.5 z-30">
                  <div className="px-3 py-1 text-[10px] uppercase tracking-wider font-semibold text-gray-400">
                    Local model inventory
                  </div>
                  {models.map((model) => (
                    <button
                      key={model.id}
                      type="button"
                      disabled={!model.is_installed}
                      onClick={() => {
                        setSelectedModel(model);
                        setModelDropdownOpen(false);
                      }}
                      title={model.is_installed ? `Use ${model.name}` : model.unavailable_reason || 'Not installed'}
                      className={`w-full text-left px-3 py-2 text-xs flex items-center justify-between transition-colors ${
                        model.is_installed
                          ? 'hover:bg-purple-50 text-gray-700'
                          : 'opacity-45 cursor-not-allowed bg-gray-50/70 text-gray-400'
                      }`}
                    >
                      <div className="min-w-0 pr-2">
                        <div className="flex items-center gap-1.5">
                          <p className="font-medium truncate">{model.name}</p>
                          {!model.is_installed && <span className="text-[9px] uppercase">Not installed</span>}
                        </div>
                        <p className="text-[10px] text-gray-400 mt-0.5">
                          {model.is_installed ? `${model.quantization} • ready locally` : model.unavailable_reason}
                        </p>
                      </div>
                      {selectedModel?.id === model.id && <Check className="w-3.5 h-3.5 text-purple-600 shrink-0" />}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Top-Right: Search Threads + Clearance Indicator + New Thread */}
            <div className="flex items-center gap-2.5">
              {/* Search Thread Filter */}
              <div className="hidden md:flex items-center gap-2 px-3 py-2 rounded-xl border border-[#e4e7ec] bg-[#fcfcfd] text-xs text-gray-600 focus-within:border-purple-300 focus-within:bg-white transition-all">
                <Search className="w-3.5 h-3.5 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search threads"
                  value={searchFilter}
                  onChange={(e) => {
                    setSearchFilter(e.target.value);
                    if (!isHistoryOpen) setIsHistoryOpen(true);
                  }}
                  className="bg-transparent outline-none w-28 text-xs placeholder-gray-400"
                />
              </div>

              {/* Clearance Badge */}
              <button
                type="button"
                onClick={() => setSettingsOpen(true)}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-[#e4e7ec] bg-white hover:bg-gray-50 text-xs font-semibold text-gray-700 transition-all"
                title="Click to view or change officer clearance"
              >
                <Shield className="w-3.5 h-3.5 text-purple-600" />
                <span>{clearanceLevel}</span>
              </button>

              {/* + New Thread Button */}
              <button
                type="button"
                onClick={handleNewThread}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#292c33] hover:bg-[#17191d] active:scale-[0.98] text-white text-xs font-semibold shadow-sm transition-all"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>New Thread</span>
              </button>
            </div>
          </header>

          {/* Dynamic Main View Switcher */}
          <section className="flex-1 overflow-hidden relative">
            {activeNavTab === 'home' && (
              <ChatWindow
                userId={officerUserId}
                sessionId={activeSessionId}
                onSessionCreated={(id) => setActiveSessionId(id)}
                userName={officerUserId}
                clearanceLevel={clearanceLevel}
                modelId={selectedModel?.id}
                departments={departments}
                onOpenUpload={() => setActiveNavTab('docs')}
              />
            )}

            {activeNavTab === 'docs' && (
              <DocumentsView
                userId={officerUserId}
                clearanceLevel={clearanceLevel}
                departments={departments}
              />
            )}

            {activeNavTab === 'network' && <PrecedentsView />}

            {activeNavTab === 'audit' && <AuditView />}

            {activeNavTab === 'database' && <SourcesView />}

            {activeNavTab === 'review' && <ReviewView userId={officerUserId} />}
          </section>
        </div>
      </div>

      {/* Settings & Officer Clearance Governance Modal */}
      <SettingsModal
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        userId={officerUserId}
        onUpdateUserId={(id) => setOfficerUserId(id)}
        clearanceLevel={clearanceLevel}
        onUpdateClearanceLevel={(lvl) => setClearanceLevel(lvl)}
        departmentId={departmentId}
        onUpdateDepartmentId={(dept) => setDepartmentId(dept)}
        departments={departments}
      />
    </main>
  );
}
