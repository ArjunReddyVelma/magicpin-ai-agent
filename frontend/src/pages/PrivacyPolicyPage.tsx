import React from 'react';
import { ArrowLeft, Shield, AlertTriangle, FileText, Database, Cpu, Trash2, HelpCircle } from 'lucide-react';

interface LegalPageProps {
  onBack: () => void;
}

export const PrivacyPolicyPage: React.FC<LegalPageProps> = ({ onBack }) => {
  return (
    <div className="max-w-4xl mx-auto py-8 px-4 sm:px-6 lg:px-8 space-y-6">
      {/* Navigation header */}
      <div className="flex items-center justify-between border-b border-surface-200 pb-4">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-800 hover:text-emerald-900 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Return to Workspace</span>
        </button>
        <span className="text-[11px] text-surface-800 font-mono">Status: Pre-Publication Draft</span>
      </div>

      {/* Header */}
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <Shield className="w-5 h-5 text-emerald-700" />
          <h1 className="text-xl font-bold text-surface-900 tracking-tight">Privacy Policy</h1>
        </div>
        <p className="text-xs text-surface-800">
          Operational Data Handling & Privacy Architecture for Magicpin AI Agent Merchant Workspace
        </p>
        <p className="text-[11px] text-surface-800">Last Updated: October 2026 &bull; Version: 1.0 (Draft)</p>
      </div>

      {/* Notice box: Legal / Product Owner Confirmation Required */}
      <div className="bg-amber-50 border border-amber-200 rounded p-4 text-xs text-amber-900 space-y-2 shadow-2xs">
        <div className="flex items-center gap-2 font-semibold text-amber-950">
          <AlertTriangle className="w-4 h-4 text-amber-700 shrink-0" />
          <span>Notice: Draft Operational Disclosure &bull; Legal Confirmation Pending</span>
        </div>
        <p className="text-[11px] leading-relaxed">
          This document describes the current technical architecture and operational data flows of the Magicpin AI Agent software.
          <strong> Formal legal review has not yet been completed.</strong> The specific items marked with callouts below require explicit product-owner and legal confirmation prior to commercial launch.
        </p>
      </div>

      {/* Policy Content Sections */}
      <div className="space-y-6 text-xs text-surface-900 leading-relaxed">
        {/* Section 1 */}
        <section className="bg-white border border-surface-200 rounded p-5 space-y-3 shadow-xs">
          <h2 className="text-sm font-semibold text-surface-900 flex items-center gap-2">
            <FileText className="w-4 h-4 text-emerald-700" />
            <span>1. Information We Collect</span>
          </h2>
          <p>
            When merchants register and operate their workspace, the application collects and stores the following categories of information:
          </p>
          <ul className="list-disc pl-5 space-y-1 text-surface-800">
            <li><strong>Merchant Identity:</strong> Full name, login email address, Argon2id-hashed credentials, and session authentication records.</li>
            <li><strong>Store Profile:</strong> Business name, retail/dining category, location/city, timezone, and business descriptions.</li>
            <li><strong>Business Context Items:</strong> Store return policies, FAQs, operating hours, delivery parameters, and key business facts provided by the merchant.</li>
            <li><strong>Conversational History:</strong> User prompts, bounded message histories, simulated customer inquiries, and assistant turns.</li>
            <li><strong>Suggested Actions:</strong> Assistant-generated reply drafts, recommendations, follow-up flags, and merchant review decisions (approved/dismissed).</li>
            <li><strong>Technical Security Logs:</strong> Hashed session identifiers, CSRF validation metadata, and audit events for security rate limiting.</li>
          </ul>
        </section>

        {/* Section 2: AI Processing (Explicit Confirmation Flag) */}
        <section className="bg-white border border-surface-200 rounded p-5 space-y-3 shadow-xs">
          <h2 className="text-sm font-semibold text-surface-900 flex items-center gap-2">
            <Cpu className="w-4 h-4 text-emerald-700" />
            <span>2. AI Provider Processing & Grounded Knowledge</span>
          </h2>
          <p>
            To generate context-grounded responses, the application transmits merchant prompts alongside active business context items to our configured LLM provider (Groq API hosting models such as openai/gpt-oss-120b and Meta Llama).
          </p>
          <p className="text-surface-800">
            Requests are processed ephemerally for response generation. The application does not use merchant proprietary context to train generalized public foundation models.
          </p>

          <div className="p-3 bg-surface-50 border-l-3 border-amber-600 rounded text-surface-800 space-y-1">
            <div className="font-semibold text-surface-900 flex items-center gap-1.5">
              <HelpCircle className="w-3.5 h-3.5 text-amber-700" />
              <span>[Requires Legal / Product-Owner Confirmation]</span>
            </div>
            <p className="text-[11px]">
              Confirm formal Data Processing Agreements (DPA) and contractual zero-data-retention commitments with external LLM API providers (Groq Inc.). Verify cross-border data transfer disclosure requirements for end-merchant data.
            </p>
          </div>
        </section>

        {/* Section 3: Data Retention (Explicit Confirmation Flag) */}
        <section className="bg-white border border-surface-200 rounded p-5 space-y-3 shadow-xs">
          <h2 className="text-sm font-semibold text-surface-900 flex items-center gap-2">
            <Database className="w-4 h-4 text-emerald-700" />
            <span>3. Data Retention Policies</span>
          </h2>
          <p>
            Current technical operational parameters maintain data according to the following rules:
          </p>
          <ul className="list-disc pl-5 space-y-1 text-surface-800">
            <li><strong>Active Sessions:</strong> Session tokens automatically expire after 7 days (10,080 minutes) of inactivity or upon explicit logout.</li>
            <li><strong>Context Items & Conversations:</strong> Persist indefinitely within PostgreSQL storage until modified, archived, or deleted by the merchant.</li>
            <li><strong>Audit Events:</strong> Login attempt and security rate-limiting records are evaluated over a rolling 15-minute sliding window.</li>
          </ul>

          <div className="p-3 bg-surface-50 border-l-3 border-amber-600 rounded text-surface-800 space-y-1">
            <div className="font-semibold text-surface-900 flex items-center gap-1.5">
              <HelpCircle className="w-3.5 h-3.5 text-amber-700" />
              <span>[Requires Legal / Product-Owner Confirmation]</span>
            </div>
            <p className="text-[11px]">
              Establish statutory data retention limits for inactive accounts, routine audit event purge schedules, and disaster-recovery backup retention windows.
            </p>
          </div>
        </section>

        {/* Section 4: Account Deletion (Explicit Confirmation Flag) */}
        <section className="bg-white border border-surface-200 rounded p-5 space-y-3 shadow-xs">
          <h2 className="text-sm font-semibold text-surface-900 flex items-center gap-2">
            <Trash2 className="w-4 h-4 text-emerald-700" />
            <span>4. Merchant Account Deletion & Right to Erasure</span>
          </h2>
          <p>
            Merchants may initiate permanent account deletion at any time via Settings by providing explicit password confirmation.
          </p>
          <p className="text-surface-800">
            Upon successful verification, the database executes an atomic deletion cascade (<code className="bg-surface-100 px-1 py-0.5 rounded font-mono text-[11px]">ON DELETE CASCADE</code>) purging the user record, merchant profile, all context items, conversation histories, message turns, suggested actions, and user sessions.
          </p>

          <div className="p-3 bg-surface-50 border-l-3 border-amber-600 rounded text-surface-800 space-y-1">
            <div className="font-semibold text-surface-900 flex items-center gap-1.5">
              <HelpCircle className="w-3.5 h-3.5 text-amber-700" />
              <span>[Requires Legal / Product-Owner Confirmation]</span>
            </div>
            <p className="text-[11px]">
              Confirm compliance procedures under applicable data privacy frameworks (e.g. India Digital Personal Data Protection Act, GDPR) regarding encrypted database backup purging timelines and irreversible erasure verification.
            </p>
          </div>
        </section>

        {/* Section 5: Security Architecture */}
        <section className="bg-white border border-surface-200 rounded p-5 space-y-3 shadow-xs">
          <h2 className="text-sm font-semibold text-surface-900 flex items-center gap-2">
            <Shield className="w-4 h-4 text-emerald-700" />
            <span>5. Technical & Organizational Security Measures</span>
          </h2>
          <ul className="list-disc pl-5 space-y-1 text-surface-800">
            <li><strong>Credential Hashing:</strong> Passwords hashed with Argon2id using unique cryptographic salts; plaintext passwords are never logged or stored.</li>
            <li><strong>Session Security:</strong> Hashed opaque tokens stored in <code className="bg-surface-100 px-1 py-0.5 rounded font-mono text-[11px]">HttpOnly; SameSite=Lax; Secure</code> cookies.</li>
            <li><strong>CSRF Defense:</strong> Cryptographically generated, session-bound CSRF tokens validated on all state-changing endpoints.</li>
            <li><strong>Tenant Isolation:</strong> Strict server-side authorization ensuring merchants cannot view or modify data of other tenants.</li>
          </ul>
        </section>
      </div>

      {/* Footer Return */}
      <div className="pt-4 border-t border-surface-200 text-center">
        <button
          onClick={onBack}
          className="px-4 py-2 text-xs font-medium text-white bg-emerald-700 hover:bg-emerald-800 rounded shadow-xs transition-colors"
        >
          Return to Workspace
        </button>
      </div>
    </div>
  );
};
