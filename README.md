# 🤖 Magicpin AI Agent

![Python](https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green?style=for-the-badge&logo=fastapi)
![React](https://img.shields.io/badge/React-18.3+-61DAFB?style=for-the-badge&logo=react)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=for-the-badge&logo=postgresql)
![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)

A standalone **Merchant Support Copilot and Knowledge Management Workspace** built with **FastAPI**, **PostgreSQL**, and **React (TypeScript + Tailwind CSS)**.

The application enables merchants to maintain their business context and operating policies, conduct AI-assisted support conversations grounded in their active knowledge base, and safely review AI-generated customer reply drafts through an audited **Human-in-the-Loop** review queue.

## Current development and deployment status

- **Current feature branch:** [`feature/whatsapp-mock-mode`](https://github.com/ArjunReddyVelma/magicpin-ai-agent/tree/feature/whatsapp-mock-mode)
- **Latest WhatsApp Mock Mode commit:** [`71ecd68`](https://github.com/ArjunReddyVelma/magicpin-ai-agent/commit/71ecd686212669a7d734d4c77cb945faef15bab0)
- **CI:** [CI Quality Gate run](https://github.com/ArjunReddyVelma/magicpin-ai-agent/actions/runs/39904782653) — passed for the feature commit.
- **Deployment boundary:** WhatsApp Mock Mode is published on this feature branch for development and review only. It has **not** been merged into the live website branch and must not be treated as deployed.
- **Mock-mode safety:** Set `WHATSAPP_MODE=mock` only in a local development environment. Keep the live deployment in `live` mode; mock endpoints are intentionally unavailable in live mode.

### Deployed application links

These are the Render URLs configured/used for the deployed application. Confirm the frontend hostname in the Render dashboard if Render assigned a suffixed hostname.

| Service | URL | Purpose |
|---|---|---|
| Frontend web app | [https://magicpin-frontend.onrender.com](https://magicpin-frontend.onrender.com) | Live merchant dashboard (deployed version; does not include the unmerged mock-mode feature) |
| Backend API | [https://magicpin-backend.onrender.com](https://magicpin-backend.onrender.com) | Live FastAPI service |
| Backend readiness | [https://magicpin-backend.onrender.com/v1/readyz](https://magicpin-backend.onrender.com/v1/readyz) | Health/readiness check; expected JSON includes database status |
| Swagger API docs | [https://magicpin-backend.onrender.com/docs](https://magicpin-backend.onrender.com/docs) | Interactive API documentation, if enabled by the deployed configuration |
| ReDoc | [https://magicpin-backend.onrender.com/redoc](https://magicpin-backend.onrender.com/redoc) | Alternative API documentation, if enabled by the deployed configuration |
| GitHub feature branch | [feature/whatsapp-mock-mode](https://github.com/ArjunReddyVelma/magicpin-ai-agent/tree/feature/whatsapp-mock-mode) | Review source changes without merging or deploying |
| CI verification | [GitHub Actions run](https://github.com/ArjunReddyVelma/magicpin-ai-agent/actions/runs/39904782653) | Automated backend/frontend quality checks |

> **Important:** the live site and its backend remain on their existing deployment version. Pushing this feature branch does not merge it into production. Do not enable mock mode in Render or send real WhatsApp messages while testing this feature.

---

## 1. Problem Statement and Objectives

Small and medium merchants operating on local discovery and commerce platforms face high volumes of customer inquiries concerning delayed deliveries, refund requests, store operating hours, cancellations, and order modifications. Without dedicated support staff, merchants struggle with response latency and policy consistency.

Generic AI chatbots often fail in this domain because they hallucinate store policies, lack business context, or autonomously dispatch unreviewed communications that damage merchant-customer relationships.

### Core Objectives

- **Context-Grounded Assistance**: Ground all AI interactions in verified, merchant-controlled policies, menus, and operational guidelines.
- **Human-in-the-Loop Review**: Enforce a strict boundary where AI assists but never sends external messages automatically. Drafts are held in a pending review queue until a merchant explicitly approves or dismisses them.
- **Enterprise-Grade Resilience**: Provide transaction atomicity, message persistence before AI execution, failed-turn recovery, and idempotent retries.
- **Defensive Multi-Tenant Security**: Enforce strict server-derived merchant scoping, Argon2id password hashing, opaque session tokens, and session-bound CSRF protection.

---

## 2. Key Implemented Features

- **Merchant Authentication & Session Security**:
  - Email and password registration with Argon2id cryptographic hashing.
  - Opaque 64-character hex session tokens stored as SHA-256 hashes in `user_sessions`.
  - Secure `mp_session` cookie management (`HttpOnly`, `SameSite=Lax`, `Secure` in production).
  - Session-bound HMAC CSRF protection (`X-CSRF-Token`) on all state-changing endpoints.
  - In-memory rate limiting on login attempts (5 attempts per 15-minute window).
  - Irreversible account deletion requiring password confirmation with cascading database cleanup.
- **Merchant Profile Management**:
  - Single-tenant workspace model linking each user to their distinct merchant profile.
  - Profile viewing and updating with validation for business name, category, and metadata.
- **Merchant Context & Policy Management**:
  - Full CRUD operations for business knowledge items across four canonical types: `policy`, `faq`, `store_info`, and `catalog`.
  - Filtering by context type and active/inactive status.
  - Optimistic concurrency control via integer versioning and `If-Match` ETag headers.
- **AI Workspace & Grounded Chat**:
  - Conversational interface with persistent message history stored in PostgreSQL.
  - Dynamic system prompt construction injecting the merchant's active business policies and profile.
  - Production AI integration with Groq (`llama-3.3-70b-versatile` / `openai/gpt-oss-120b`) plus an offline `MockLLMProvider` for testing.
  - System prompt anti-hallucination rules restricting responses strictly to verified merchant knowledge.
- **Conversation Durability & Safe Recovery**:
  - User messages persisted to the database prior to provider invocation.
  - Provider failure isolation: unhandled AI timeouts or upstream outages preserve the turn as `failed` and return an HTTP 502 with `failed_message_id`.
  - Client-driven retry workflow: recover failed turns without retyping using `retry_message_id`.
  - Idempotent request handling via `Idempotency-Key` headers preventing duplicate messages.
- **Automated Chat-to-Action Generation**:
  - Deterministic eligibility heuristics (`ChatService._is_draft_eligible`) analyzing user intent (`draft`, `reply`, `respond`, `apologize`) and support context (`customer`, `order`, `delayed`, `refund`, etc.).
  - Atomic database transactions creating pending `reply_draft` records alongside assistant responses under a conversation row lock.
  - Idempotency guards preventing duplicate action creation upon turn replay.
- **Suggested Actions & Human-in-the-Loop Review Queue**:
  - Dedicated review queue displaying pending reply drafts, associated conversation context, and creation timestamps.
  - Status filtering (`pending`, `approved`, `dismissed`) and paginated listing.
  - Atomic state transitions: merchants can approve or dismiss pending actions.
  - **Review-Only Guarantee**: Approving or dismissing an action exclusively updates PostgreSQL review columns (`status`, `reviewed_at`). The application never dispatches external messages, emails, SMS, or financial transactions.
- **Dashboard Overview**:
  - Live metric computation directly from PostgreSQL tables (active contexts, total conversations, pending review queue count).
  - Quick action links and real-time operational status.
- **Accessible Legal Disclosures**:
  - Dedicated Privacy Policy and Terms of Service interfaces.
  - Transparent draft disclosures indicating that legal review is pending and highlighting areas requiring product-owner confirmation.

---

## 3. Current Implementation Status

| Feature Area | Status | Verification & Evidence |
|---|---|---|
| **PostgreSQL Persistence & Migrations** | Implemented | SQLAlchemy models, Alembic migration history, migration tests |
| **Authentication & Session Security** | Implemented | Argon2id password hashing, session cookies, CSRF validation, tenant isolation tests |
| **Merchant Context Management** | Implemented | CRUD API + ETag optimistic locking verified |
| **Chat & Context Grounding** | Implemented | Prompt grounding, Groq provider, response validator |
| **Failed-Turn Recovery & Idempotency** | Implemented | HTTP 502 recovery, retry message ID, idempotency keys |
| **Chat-to-Action Generation** | Implemented | 7 integration tests passing; atomic row-locked transactions |
| **Suggested Actions Review Queue** | Implemented | Paginated queue, state machine, zero side-effects verified |
| **Frontend Single-Page Application** | Implemented | 55 frontend tests reported passing; lint and production build passed on the mock-mode feature branch |
| **Full-Stack Integration Audit** | Implemented | 126 backend tests passed, 1 skipped; 55 frontend tests passed on the mock-mode feature branch |
| **Legal Pages (Privacy & Terms)** | Draft Implemented | Reachable in UI; operational disclosures with pending-review notices |
| **Live Production Deployment** | Deployed separately from this feature branch | Existing Render frontend/backend links are listed above; WhatsApp Mock Mode remains feature-branch-only |

---

## 4. Technology Stack

### Backend
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.11+)
- **Server**: [Uvicorn](https://www.uvicorn.org/) (ASGI standard worker)
- **Database ORM**: [SQLAlchemy 2.0](https://www.sqlalchemy.org/) (typed declarative models)
- **Database Driver**: [Psycopg 3](https://www.psycopg.org/psycopg3/) (`psycopg[binary]>=3.2.0`)
- **Schema Validation**: [Pydantic v2](https://docs.pydantic.dev/) & [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- **Database Migrations**: [Alembic](https://alembic.sqlalchemy.org/)
- **Password Hashing**: [Argon2-cffi](https://argon2-cffi.readthedocs.io/)
- **AI Integration**: [Groq Python SDK](https://github.com/groq/groq-python) / OpenAI-compatible API
- **Test Framework**: [Pytest](https://docs.pytest.org/) & HTTPX TestClient

### Frontend
- **Framework**: [React 18](https://react.dev/) with [TypeScript](https://www.typescriptlang.org/)
- **Build Tooling**: [Vite 5](https://vitejs.dev/)
- **Styling**: [Tailwind CSS 3](https://tailwindcss.com/)
- **Icons**: [Lucide React](https://lucide.dev/)
- **Test Runner**: Node.js built-in test runner (`node --test`)

### Infrastructure & Persistence
- **Database**: PostgreSQL 16
- **Deployment Specification**: Render Infrastructure-as-Code (`render.yaml`)

---

## 5. System Architecture and Request Flow

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Browser / Client                                 │
│                   React 18 SPA (TypeScript + Tailwind)                     │
└───────────────────────┬─────────────────────────────▲───────────────────────┘
                        │ HTTP / JSON                 │
                        │ Credentials: include        │ Cookie: mp_session
                        │ Header: X-CSRF-Token        │ JSON Responses
                        ▼                             │
┌─────────────────────────────────────────────────────┴───────────────────────┐
│                           FastAPI Application                               │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    Security & Session Middleware                       │ │
│  │  - Cookie Session Validator (SHA-256 token lookup in user_sessions)   │ │
│  │  - HMAC CSRF Verification (on POST, PATCH, DELETE)                     │ │
│  │  - Strict Merchant Ownership Scoping (session -> user -> merchant)     │ │
│  └───────────────────────────────────┬────────────────────────────────────┘ │
│                                      │                                      │
│                                      ▼                                      │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                       API Route Controllers (/v1)                      │ │
│  │  /auth  •  /merchant  •  /context  •  /conversations  •  /actions       │ │
│  └───────────────────────────────────┬────────────────────────────────────┘ │
│                                      │                                      │
│                                      ▼                                      │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        Core Service Layer                              │ │
│  │  ┌─────────────────────────┐            ┌────────────────────────────┐ │ │
│  │  │       ChatService       │            │      ContextRetriever      │ │ │
│  │  │  - Row lock on conv     │◄───────────┤  - Active merchant items   │ │ │
│  │  │  - Persist user message │            └────────────────────────────┘ │ │
│  │  │  - Action eligibility   │            ┌────────────────────────────┐ │ │
│  │  │  - Atomic commit        │───────────►│       PromptBuilder        │ │ │
│  │  └────────────┬────────────┘            │  - Grounded system prompt  │ │ │
│  │               │                         └────────────────────────────┘ │ │
│  └───────────────┼────────────────────────────────────────────────────────┘ │
└──────────────────┼──────────────────────────────────────────────────────────┘
                   │                                         │
                   ▼                                         ▼
┌─────────────────────────────────────┐   ┌───────────────────────────────────┐
│             AI Provider             │   │            PostgreSQL 16          │
│   Groq API (Llama 3.3 70B)          │   │  - users                          │
│   OR Offline MockLLMProvider        │   │  - user_sessions                  │
│                                     │   │  - merchant_profiles              │
│   - Grounded context injection      │   │  - context_items                  │
│   - Output validation & guardrails  │   │  - conversations                  │
│   - Timeout & retry handling        │   │  - messages                       │
│                                     │   │  - suggested_actions              │
└─────────────────────────────────────┘   └───────────────────────────────────┘
```

### End-to-End Chat & Suggested Action Workflow

1. **Client Dispatches Message**: The merchant sends a message to `POST /v1/conversations/{id}/messages` with an `Idempotency-Key` header, `X-CSRF-Token`, and the `mp_session` cookie.
2. **Session & Scoping**: The dependency layer resolves the session, verifies the CSRF token, and extracts the merchant profile. The client cannot supply or alter the `merchant_id`.
3. **Transaction Initiation & Row Lock**: A database transaction is opened with a pessimistic row lock on the conversation record (`with_for_update()`).
4. **Pre-Invocation Durability**: The user message is persisted immediately with status `failed` (`commit=False`) to ensure durability if the AI provider fails.
5. **Context Retrieval & Prompt Construction**: The `ContextRetriever` loads active context items. The `PromptBuilder` formats the grounding system prompt and bounds conversation history to recent turns.
6. **AI Provider Invocation**: The configured LLM provider (`GroqProvider` or `MockLLMProvider`) executes the completion request. If an exception occurs, the user message remains `failed`, the transaction is rolled back, and an HTTP 502 with `failed_message_id` is returned.
7. **Deterministic Action Eligibility**: Upon successful generation, `_is_draft_eligible` evaluates whether the merchant requested customer-support drafting assistance. If eligible, a `SuggestedAction` (`action_type="reply_draft"`, `status="pending"`) is created within the same open transaction.
8. **Atomic Commit**: The user message status transitions to `complete`, the assistant message is persisted, conversation `last_message_at` is updated, and the suggested action is committed in a single atomic database operation (`db.commit()`).
9. **Review Queue Presentation**: The merchant reviews the generated draft in the Suggested Actions tab.
10. **Review Decision**: The merchant approves (`POST /v1/actions/{id}/approve`) or dismisses (`POST /v1/actions/{id}/dismiss`) the draft. The status is updated to `approved` or `dismissed` with `reviewed_at` timestamp. **No external messages are transmitted.**

---

## 6. Repository Structure

```text
magicpin-ai-agent/
├── backend/
│   ├── alembic.ini                   # Alembic database migration configuration
│   ├── requirements.txt              # Production Python dependencies
│   ├── app/
│   │   ├── main.py                   # FastAPI entrypoint, middleware, exception handlers
│   │   ├── ai/                       # AI provider layer
│   │   │   ├── provider.py           # Abstract LLMProvider interface & custom exceptions
│   │   │   ├── groq_provider.py      # Groq API provider implementation
│   │   │   ├── mock_provider.py      # Deterministic mock provider for tests/offline
│   │   │   ├── context_retriever.py  # Merchant policy and context retrieval logic
│   │   │   ├── prompt_builder.py     # Grounded system prompt & message payload builder
│   │   │   └── response_validator.py # Output validation & safety guardrails
│   │   ├── api/v1/
│   │   │   ├── router.py             # Main v1 router assembly
│   │   │   └── routes/               # Modular REST route handlers
│   │   │       ├── health.py         # /healthz and /readyz probes
│   │   │       ├── auth.py           # Registration, login, logout, refresh, delete
│   │   │       ├── merchant.py       # Merchant profile viewing & editing
│   │   │       ├── context.py        # Context item CRUD with ETag versioning
│   │   │       ├── conversations.py  # Conversations, message history, chat turns
│   │   │       └── actions.py        # Suggested actions listing, approval, dismissal
│   │   ├── core/
│   │   │   ├── config.py             # Pydantic Settings & environment validation
│   │   │   ├── dependencies.py       # Session, merchant scoping, and CSRF dependencies
│   │   │   ├── logging.py            # Structured logging configuration
│   │   │   └── security.py           # Argon2id hashing, session tokens, CSRF HMAC
│   │   ├── db/
│   │   │   ├── base.py               # SQLAlchemy declarative Base class
│   │   │   └── session.py            # Engine, sessionmaker, connectivity check
│   │   ├── models/                   # SQLAlchemy ORM models
│   │   │   ├── user.py               # User account model
│   │   │   ├── user_session.py       # Opaque session token model
│   │   │   ├── merchant_profile.py   # 1:1 merchant workspace model
│   │   │   ├── context_item.py       # Knowledge base items with integer versioning
│   │   │   ├── conversation.py       # Conversation container model
│   │   │   ├── message.py            # Message turns with status & token metadata
│   │   │   └── suggested_action.py   # Reply drafts with status & review timestamps
│   │   ├── repositories/             # Scoped database access layer
│   │   └── schemas/                  # Pydantic v2 request & response schemas
│   ├── migrations/                   # Alembic migration environment and versions
│   └── tests/                        # Comprehensive test suite
│       ├── unit/                     # Pure unit tests (security, validators)
│       ├── integration/              # Database & repository integration tests
│       ├── api/                      # Full API route tests using TestClient
│       └── security/                 # CSRF and cross-tenant isolation tests
├── frontend/
│   ├── index.html                    # Single-page application entrypoint
│   ├── package.json                  # Frontend scripts and dependencies
│   ├── tsconfig.json                 # TypeScript strict configuration
│   ├── vite.config.ts                # Vite build and development configuration
│   ├── src/
│   │   ├── App.tsx                   # Main application router and state container
│   │   ├── api/                      # Typed REST API client & error handling
│   │   ├── components/               # Reusable UI components (Navbar, Modals, Cards)
│   │   ├── layouts/                  # AppLayout and AuthLayout containers
│   │   ├── pages/                    # Views: Dashboard, Context, Chat, Actions, Settings, Legal
│   │   └── types/                    # TypeScript data models and interfaces
│   └── test/                         # Node.js frontend test suite (42 unit tests)
├── docs/
│   ├── DECISIONS.md                  # Architecture decision records & constraints
│   ├── IMPLEMENTATION_STATUS.md      # Detailed phase-by-phase implementation audit
│   └── Magicpin_AI_Agent_OpenAPI_v1.yaml # Canonical OpenAPI 3.1 specification
├── render.yaml                       # Render blueprint for cloud deployment
├── .env.example                      # Safe template of environment variables
├── .gitignore                        # Git ignore rules protecting secrets
└── README.md                         # Project documentation
```

---

## 7. Authentication and Security Architecture

1. **Password Security**: Passwords are cryptographically hashed using **Argon2id** (`argon2-cffi`), which provides superior memory-hard resistance against GPU brute-force attacks compared to legacy bcrypt.
2. **Opaque Server-Side Sessions**: 
   - Sessions are not stateless JWTs; they are cryptographically random 64-character hex tokens.
   - The plain token is sent to the client in an `HttpOnly`, `SameSite=Lax` cookie (`mp_session`).
   - The database stores only the `SHA-256` hash of the token in `user_sessions`. If the database is compromised, active session tokens cannot be recovered.
3. **Session-Bound CSRF Defense**:
   - For every active session, a unique CSRF token is derived via `HMAC-SHA256(CSRF_SECRET, session_id + user_id)`.
   - The frontend transmits this token via the `X-CSRF-Token` header on all unsafe state-changing requests (`POST`, `PATCH`, `DELETE`).
   - Requests lacking a valid matching token are rejected with `403 FORBIDDEN`.
4. **Tenant Isolation by Construction**:
   - The application does not accept `merchant_id` in request payloads for authorization.
   - The current merchant profile is derived exclusively by the `get_current_merchant` FastAPI dependency: `Session Cookie -> Valid User -> Linked MerchantProfile`.
   - All repository queries filter explicitly by the authenticated `merchant_id`. Cross-tenant queries return `404 NOT FOUND`.
5. **Rate Limiting**:
   - In-memory rate limiting monitors failed login attempts per client IP and email.
   - Enforces a ceiling of 5 attempts within a 900-second (15-minute) sliding window to prevent brute-force credential stuffing.
6. **Account Erasure**:
   - `DELETE /v1/auth/account` allows merchants to permanently delete their account.
   - Requires explicit password confirmation and cascades deletion across all sessions, profile records, context items, conversations, messages, and suggested actions.

---

## 8. AI Provider Integration & Merchant-Context Grounding

### Provider Abstraction
The system uses an abstract interface, `LLMProvider`, defined in [`backend/app/ai/provider.py`](file:///Users/reddy/Desktop/magicpin-ai-agent-main/backend/app/ai/provider.py):
- **`GroqProvider`**: Uses the Groq SDK to run high-speed inference on `llama-3.3-70b-versatile` (or `openai/gpt-oss-120b`).
- **`MockLLMProvider`**: Provides deterministic, reproducible responses for automated tests and offline local development without requiring an API key.

### Grounding and Anti-Hallucination Guardrails
Before sending a prompt to the AI provider:
1. Active context items belonging to the merchant are retrieved by `ContextRetriever`.
2. The `PromptBuilder` constructs a system prompt establishing the merchant's business identity (name, category) and injects active policies into dedicated context blocks.
3. Strict instructions are applied:
   - *"Answer customer inquiries based ONLY on the provided merchant policies and details."*
   - *"Do not fabricate discounts, operating hours, delivery promises, or refund guarantees not present in the context."*
   - *"If the policy does not cover the customer query, acknowledge the inquiry and state that a store manager will confirm details."*
4. Completed responses pass through `ResponseValidator` to enforce minimum length, detect error fallbacks, and strip unexpected formatting artifacts.

---

## 9. Chat History, Recovery, Idempotency & Retries

### Two-Phase Message Persistence
To guarantee message durability, the backend uses a two-phase persistence pattern:
1. **Phase 1 (Pre-Call)**: When the user submits a message, it is inserted into the `messages` table with `status="failed"`. The database transaction remains open with a row lock on the conversation.
2. **Phase 2 (Post-Call)**: If the LLM call succeeds, the user message status is updated to `"complete"`, the assistant message is created, and the transaction is committed.
3. **Failure Isolation**: If the LLM provider times out or returns an error, the user message remains marked `"failed"`, the conversation row lock is released, and an HTTP 502 error is returned containing:
   ```json
   {
     "error": {
       "code": "LLM_PROVIDER_ERROR",
       "message": "The AI service is temporarily unavailable. Your message has been saved as failed and can be retried.",
       "details": {
         "failed_message_id": "uuid-here",
         "retryable": true
       }
     }
   }
   ```

### Client Retry Workflow
The merchant's drafted input is never lost. The frontend captures the `failed_message_id` and allows the merchant to click **Retry**. The retry request supplies `retry_message_id`, which re-executes the turn against the saved message without creating duplicate database records.

### Idempotency Protection
Clients supply an `Idempotency-Key` HTTP header. If network retries resubmit the same request, the server detects the existing key in `messages.context_metadata`, verifies that the previous turn completed, and returns the cached response without re-invoking the AI model.

---

## 10. Suggested Actions & Human-in-the-Loop Review Queue

### Deterministic Draft Generation
Rather than triggering LLM function-calling on every prompt, the backend applies a deterministic heuristic ([`ChatService._is_draft_eligible`](file:///Users/reddy/Desktop/magicpin-ai-agent-main/backend/app/services/chat_service.py#L50-104)):
- **Drafting Intent**: Matches intent terms such as `draft`, `reply`, `respond`, `apologize`, `how should i reply`, `what should i say`.
- **Customer Context**: Matches operational nouns such as `customer`, `client`, `order`, `delivery`, `refund`, `complaint`, `delayed`, `cancel`.
- **Exclusion Filters**: Ignores casual greetings ("hello", "thanks"), general questions, or provider error messages.

### Atomic Action Creation
When eligible, `ActionRepository.create(..., commit=False)` creates a record in `suggested_actions`:
- `action_type`: `"reply_draft"`
- `title`: Auto-generated title summarizing the inquiry (e.g., `Customer Reply: Delayed Order Policy`)
- `description`: The complete AI-drafted reply text
- `payload`: Contains `generated_reply`, `user_message_id`, and `conversation_id`
- `status`: `"pending"`

This record is committed atomically within the same database transaction as the chat turn.

### Decision Recording (No External Side Effects)
The review queue allows merchants to review pending actions:
- **Approve**: `POST /v1/actions/{id}/approve` -> updates `status="approved"`, sets `reviewed_at=NOW()`.
- **Dismiss**: `POST /v1/actions/{id}/dismiss` -> updates `status="dismissed"`, sets `reviewed_at=NOW()`.
- **State Conflict Prevention**: Actions already in an `approved` or `dismissed` state cannot be transitioned again; attempts return `409 CONFLICT` (`INVALID_ACTION_STATE`).
- **No Side Effects**: Decisions are recorded purely for auditing and UI tracking. **The application never sends WhatsApp messages, SMS, emails, or initiates financial transactions.**

---

## 11. Database Schema and Migrations

The database consists of 7 normalized tables managed with SQLAlchemy 2.0 and Alembic:

```text
┌─────────────────┐       ┌───────────────────────┐
│      users      │1 ─── 1│   merchant_profiles   │
└────────┬────────┘       └───────────┬───────────┘
         │1                           │1
         │                            │
         ▼*                           ├───────────────┐*
┌─────────────────┐                   ▼*              ▼
│  user_sessions  │       ┌──────────────────────┐  ┌─────────────────────┐
└─────────────────┘       │    context_items     │  │    conversations    │
                          └──────────────────────┘  └──────────┬──────────┘
                                                               │1
                                                               │
                                                               ▼*
┌─────────────────────────┐* 1                                ┌─────────────────────┐
│    suggested_actions    │◄──────────────────────────────────┤      messages       │
└─────────────────────────┘                                   └─────────────────────┘
```

- **`users`**: UUID primary key, `email` (unique, lowercase), `password_hash`, `full_name`, `is_active`, timestamps.
- **`user_sessions`**: UUID primary key, `user_id` (FK), `token_hash` (unique SHA-256), `expires_at`, `ip_address`, `user_agent`.
- **`merchant_profiles`**: UUID primary key, `user_id` (unique FK), `business_name`, `category`, `settings` (JSONB).
- **`context_items`**: UUID primary key, `merchant_id` (FK), `item_type` (`policy`, `faq`, `store_info`, `catalog`), `title`, `content`, `is_active`, `version` (integer for optimistic concurrency).
- **`conversations`**: UUID primary key, `merchant_id` (FK), `title`, `status` (`active`, `archived`), `last_message_at`.
- **`messages`**: UUID primary key, `conversation_id` (FK), `role` (`user`, `assistant`), `content`, `status` (`complete`, `failed`), `provider`, `model`, `tokens`, `context_metadata` (JSONB).
- **`suggested_actions`**: UUID primary key, `merchant_id` (FK), `conversation_id` (FK), `action_type`, `title`, `description`, `payload` (JSONB), `status` (`pending`, `approved`, `dismissed`), `reviewed_at`.

---

## 12. API Documentation and Endpoint Reference

When running locally, interactive API documentation is available at:
- **Swagger UI**: `http://127.0.0.1:8000/docs`
- **ReDoc**: `http://127.0.0.1:8000/redoc`
- **OpenAPI JSON**: `http://127.0.0.1:8000/openapi.json`

### Summary of REST Endpoints

| Group | Method | Path | Description | Auth Required |
|---|---|---|---|---|
| **Health** | `GET` | `/` | Root service status and version | No |
| | `GET` | `/v1/healthz` | Process liveness probe | No |
| | `GET` | `/v1/readyz` | Readiness probe (verifies database `SELECT 1`) | No |
| **Auth** | `POST` | `/v1/auth/register` | Register user and 1:1 merchant workspace | No |
| | `POST` | `/v1/auth/login` | Authenticate and issue `mp_session` cookie | No (Rate Limited) |
| | `POST` | `/v1/auth/logout` | Revoke session and clear cookie | Yes + CSRF |
| | `GET` | `/v1/auth/me` | Fetch active user session details | Yes |
| | `POST` | `/v1/auth/refresh` | Rotate session token and issue new CSRF token | Yes + CSRF |
| | `DELETE` | `/v1/auth/account` | Permanently delete account (requires password) | Yes + CSRF |
| **Merchant** | `GET` | `/v1/merchant` | Get current merchant profile (alias: `/profile`) | Yes |
| | `PATCH` | `/v1/merchant` | Update merchant business profile (alias: `/profile`) | Yes + CSRF |
| **Context** | `GET` | `/v1/context` | List context items with pagination and filters | Yes |
| | `POST` | `/v1/context` | Create new context item | Yes + CSRF |
| | `GET` | `/v1/context/{id}` | Get context item details | Yes |
| | `PATCH` | `/v1/context/{id}` | Update context item (supports `If-Match` ETag) | Yes + CSRF |
| | `DELETE` | `/v1/context/{id}` | Delete context item | Yes + CSRF |
| **Conversations**| `GET` | `/v1/conversations` | List merchant conversations with search/status | Yes |
| | `POST` | `/v1/conversations` | Create new conversation container | Yes + CSRF |
| | `GET` | `/v1/conversations/{id}` | Get conversation metadata | Yes |
| | `PATCH` | `/v1/conversations/{id}` | Update title or status (`active`/`archived`) | Yes + CSRF |
| | `DELETE` | `/v1/conversations/{id}` | Delete conversation and messages | Yes + CSRF |
| **Messages** | `GET` | `/v1/conversations/{id}/messages` | List paginated message history | Yes |
| | `POST` | `/v1/conversations/{id}/messages` | Send message and receive AI response | Yes + CSRF |
| **Actions** | `GET` | `/v1/actions` | List suggested actions (`pending`/`approved`/`dismissed`) | Yes |
| | `GET` | `/v1/actions/{id}` | Get suggested action details | Yes |
| | `POST` | `/v1/actions/{id}/approve` | Record merchant approval decision | Yes + CSRF |
| | `POST` | `/v1/actions/{id}/dismiss` | Record merchant dismissal decision | Yes + CSRF |

---

## 13. Environment Variable Reference

All configuration is managed using Pydantic Settings in [`backend/app/core/config.py`](file:///Users/reddy/Desktop/magicpin-ai-agent-main/backend/app/core/config.py) and loaded from `.env`:

| Variable | Default Value | Description |
|---|---|---|
| `APP_ENV` | `development` | Environment mode (`development` or `production`). |
| `APP_NAME` | `Magicpin AI Agent` | Display name of the application. |
| `API_V1_STR` | `/v1` | URL prefix for v1 API routes. |
| `HOST` | `0.0.0.0` | Bind host address for Uvicorn. |
| `PORT` | `8000` | Bind port for Uvicorn. |
| `DATABASE_URL` | `postgresql+psycopg://...` | Connection URI for PostgreSQL database. |
| `SECRET_KEY` | *(insecure dev string)* | Secret key used for cryptographic operations. Must be overridden in production. |
| `CSRF_SECRET` | *(insecure dev string)* | Secret key used for HMAC CSRF tokens. Must be overridden in production. |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | Allowed CORS origin for frontend requests. |
| `LLM_PROVIDER` | `groq` | Provider selection: `groq` for live AI or `mock` for deterministic offline testing. |
| `LLM_API_KEY` | *(empty)* | Groq API Key (required when `LLM_PROVIDER=groq`). |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | Model name on Groq (e.g., `llama-3.3-70b-versatile` or `openai/gpt-oss-120b`). |
| `LLM_TIMEOUT_SECONDS` | `30` | Maximum request duration before aborting LLM calls. |
| `LLM_MAX_RETRIES` | `2` | Maximum retry attempts for transient AI provider errors. |
| `COOKIE_SECURE` | `false` | When `true`, session cookies require HTTPS (automatically `true` in production). |
| `COOKIE_SAMESITE` | `lax` | SameSite cookie policy (`lax`, `strict`, or `none`). |
| `COOKIE_NAME` | `mp_session` | Name of the authentication session cookie. |
| `SESSION_TTL_MINUTES` | `10080` | Session duration (10,080 minutes = 7 days). |
| `RATE_LIMIT_LOGIN_MAX_ATTEMPTS` | `5` | Maximum failed login attempts allowed per window. |
| `RATE_LIMIT_LOGIN_WINDOW_SECONDS` | `900` | Duration of rate limiting window (900 seconds = 15 minutes). |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |

---

## 14. Database Setup & Migration Architecture

### PostgreSQL Requirements
- **Version**: PostgreSQL 16 (or 14+)
- **Database Name**: `magicpin_ai_agent`

To create the database locally:
```bash
createdb magicpin_ai_agent
# Alternatively, via psql:
psql -U postgres -c "CREATE DATABASE magicpin_ai_agent;"
```

### Alembic Migration Architecture
The Alembic configuration in `backend/alembic.ini` uses `script_location = %(here)s/migrations`. This configuration dynamically anchors the migration script path to the directory containing `alembic.ini`, allowing migrations to run seamlessly from the repository root, from within `backend/`, or inside deployment containers:

```bash
.venv/bin/alembic -c backend/alembic.ini upgrade head
```

---

## 15. Automated Testing and Verification

The repository includes comprehensive automated test suites for both backend and frontend layers:

### Backend Tests (Pytest)
```bash
.venv/bin/pytest backend/tests -v
```
**Results on the WhatsApp Mock Mode feature branch**: **126 passed, 1 skipped** (reported by the branch verification run)
- 7 tests in `backend/tests/api/test_chat_action_generation.py` (atomic action generation, retry idempotency, error rollbacks)
- 6 tests in `backend/tests/api/test_actions.py` (review queue endpoints, status transitions, conflicts)
- 34 tests in other API suites (auth, context CRUD, conversations, health)
- 13 integration tests (repositories, database constraints)
- 10 security tests (Argon2id, CSRF token verification, cross-tenant isolation)
- 7 unit tests (response validation, prompt builder)

### Frontend Tests (Node.js Test Runner)
```bash
npm --prefix frontend test
```
**Results on the WhatsApp Mock Mode feature branch**: **55 passed**
- Actions Review Queue & Decision Recording (7 tests)
- API Client & Error/CSRF Handling (4 tests)
- Context Management & Optimistic Concurrency (6 tests)
- Merchant Profile & Dashboard (5 tests)
- Legal Pages Routing & Disclosures (5 tests)
- Account Deletion & Session Logout (7 tests)
- Conversations, Message Retries & Provider Failure Recovery (8 tests)

### Frontend Linting (ESLint)
```bash
npm --prefix frontend run lint
```
**Results**: Clean linting with zero warnings and zero errors across all TypeScript and React source files (`eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0`).

### Frontend Production Build
```bash
npm --prefix frontend run build
```
**Results**: Clean production compilation with TypeScript typechecking (`tsc && vite build`), generating optimized bundles in `frontend/dist`.

### Continuous Integration (GitHub Actions)
The repository defines an automated CI workflow in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) that executes on all pushes and pull requests across `main`, `feature/**`, and `chore/**` branches:
- **Backend Quality**: Runs with a dedicated PostgreSQL 16 service container, checks Alembic migrations from root, and executes the backend test suite with `LLM_PROVIDER=mock`.
- **Frontend Quality**: Sets up Node.js 20, runs ESLint (`npm run lint`), Node.js unit tests (`npm test`), and the production build (`npm run build`).

---

## 16. Current Limitations and Future Improvements

### Current Limitations
1. **WhatsApp Mock Mode is not deployed**: the mock inbox simulation exists on `feature/whatsapp-mock-mode` only. It records simulated delivery locally and does not contact Meta Graph API. It is not part of the current live website until explicitly reviewed, merged, and separately deployed.
2. **Synchronous Chat Turns**: Message turns execute as synchronous request/response HTTP cycles. Token streaming (Server-Sent Events / WebSockets) is not implemented in the current MVP.
2. **Single User per Merchant**: The data model supports 1 user owning 1 merchant profile. Multi-user organizations and role-based access control (e.g., manager vs. support agent) are planned for a subsequent phase.
3. **Single Provider Configuration**: Provider selection is configured globally via environment variables rather than on a per-merchant basis.
4. **Relational Keyword Context Retrieval**: Context items are retrieved via active status and exact/metadata queries. High-dimensional vector embeddings and similarity search (e.g., `pgvector`) are not yet integrated.
5. **No Outbound Messaging Automation**: In compliance with the Human-in-the-Loop review constraint, the system does not integrate external WhatsApp, SMS, or email dispatch APIs. Approvals record decisions only.
6. **Default Branch History Alignment**: The GitHub repository's default branch `main` contains an unrelated Git history from an early single-directory prototype. The modular redesign resides on active feature branches (`origin/feature/frontend-core` containing merged PR #1 and `chore/repository-alignment-hardening`). Merging or reconciling the default branch is documented as an outstanding item pending project consensus.

### Planned Improvements
- Integration of `pgvector` for semantic context retrieval across extensive merchant catalogs.
- Server-Sent Events (SSE) streaming for real-time token display.
- Multi-user merchant teams with granular role permissions.
- Outbound messaging integration with merchant confirmation webhooks.
- Multi-channel support (inbound WhatsApp/Zendesk integration).
- Reconcile `main` branch with the modular architecture baseline.

---

## 17. Deployment Readiness Notes

A complete turnkey deployment specification is provided in [`render.yaml`](file:///Users/reddy/Desktop/magicpin-ai-agent-main/render.yaml):
- **Managed PostgreSQL**: PostgreSQL 16 managed database (`magicpin-postgres`).
- **Backend Web Service**: Python runtime running pre-deploy migrations and Uvicorn. Auto-generates `SECRET_KEY` and `CSRF_SECRET`.
- **Frontend Static Site**: Built with Vite and served with reverse-proxy rewrites routing `/v1/*` to the backend service.

### Production Pre-Deployment Checklist
- [ ] Provision managed PostgreSQL instance.
- [ ] Configure strong production random values for `SECRET_KEY` and `CSRF_SECRET`.
- [ ] Securely provide `LLM_API_KEY` in server environment settings (do not commit to Git).
- [ ] Ensure `APP_ENV=production`, which enforces `COOKIE_SECURE=true` and restricts CORS to `FRONTEND_ORIGIN`.
- [ ] Conduct formal legal counsel review of the draft Privacy Policy and Terms of Service before public launch.

---

## 18. License and Authorship

- **Author**: Arjun Reddy Velma
- **GitHub**: [https://github.com/ArjunReddyVelma](https://github.com/ArjunReddyVelma)
- **License**: MIT License (see repository badges)

---

## Running the Frontend and Backend Locally

Follow these exact steps to run the complete Magicpin AI Agent full-stack application on your local machine.

### 1. Clone the Repository and Check Out Branch
```bash
git clone https://github.com/ArjunReddyVelma/magicpin-ai-agent.git
cd magicpin-ai-agent
git checkout feature/whatsapp-mock-mode
```

### 2. Create and Activate the Python Virtual Environment
On macOS or Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Backend Dependencies
Install the required Python packages into `.venv`:
```bash
pip install -r backend/requirements.txt
```

### 4. Install Frontend Dependencies
Install the Node.js packages for the React application:
```bash
npm --prefix frontend install
```

### 5. Configure Environment Variables
Copy the safe example configuration to `.env`:
```bash
cp .env.example .env
```

Open `.env` and verify the settings:
- **Database**: Ensure `DATABASE_URL` matches your local PostgreSQL configuration:
  ```env
  DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/magicpin_ai_agent
  ```
- **AI Provider**:
  - **Option A (Live Groq AI)**: Set your Groq API key:
    ```env
    LLM_PROVIDER=groq
    LLM_API_KEY=your_actual_groq_api_key_here
    LLM_MODEL=llama-3.3-70b-versatile
    ```
  - **Option B (Offline Mock Provider)**: For local testing without an API key, use the built-in mock provider:
    ```env
    LLM_PROVIDER=mock
    LLM_API_KEY=
    ```

### 6. Create the Database and Apply Migrations
Ensure PostgreSQL is running, create the development database, and apply migrations directly using Alembic:
```bash
createdb magicpin_ai_agent

# Apply database migrations
.venv/bin/alembic -c backend/alembic.ini upgrade head
```

### 7. Start the Backend Server
Start the FastAPI server using Uvicorn in your first terminal window:
```bash
.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```
*The backend will start and listen at `http://127.0.0.1:8000`.*

### 8. Start the Frontend Server in a Separate Terminal
Open a **new, separate terminal window**, navigate to the project directory, and start the Vite development server:
```bash
cd /path/to/magicpin-ai-agent
npm --prefix frontend run dev
```
*The frontend development server will start and listen at `http://localhost:5173`.*

### 9. Open the Application and API Documentation
Open your web browser and navigate to:
- **Frontend Web Application**: [http://localhost:5173](http://localhost:5173)
- **FastAPI Interactive Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **FastAPI Alternative ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

### 10. Stopping the Development Servers
When you are finished testing:
- In the frontend terminal window, press `Ctrl + C`.
- In the backend terminal window, press `Ctrl + C`.
- To deactivate the Python virtual environment:
  ```bash
  deactivate
  ```
