# Architectural Decisions & Reconciliations

**Project**: Magicpin AI Agent  
**Version**: 1.0 (MVP)  
**Date**: October 2026  

---

## 1. Source of Truth Hierarchy

In accordance with project guidance, conflicting specifications are resolved using the following strict hierarchy:

1. **Specification Freeze & Final Decisions (`07_Specification_Freeze_and_Final_Decisions.pdf`)** — Canonical source for technical decisions.
2. **OpenAPI Specification (`Magicpin_AI_Agent_OpenAPI_v1.yaml`)** — Canonical API contract for all endpoints, schemas, parameters, and status codes.
3. **Product Requirements Document (PRD v1.0)** — Functional scope, boundaries, and product positioning.
4. **Technical Requirements & Architecture v1.0 & Database & Backend Schema v1.0** — Architectural boundaries, module structure, and database schemas.
5. **User & App Flow v1.0 & UI/UX Wireframes** — Screen behaviors and component interactions.
6. **Implementation Plan v1.0** — Phased delivery sequence and quality gates.

---

## 2. Frozen Decisions

| Area | Decision | Details & Constraints |
|---|---|---|
| **Product Target** | Single Merchant Workspace | Standalone web application for individual merchants. 1 user owns 1 merchant profile in MVP. |
| **Frontend Architecture** | React 18+ / TypeScript / Vite | REST client consuming `/v1`. Tailwind CSS with restrained SaaS design. No purple gradients, pill buttons, fake stats, or AI-slop graphics. |
| **Backend Architecture** | Python 3.11+ / FastAPI Modular Monolith | Single deployable backend (`app/` package) with explicit boundaries: `api/v1/routes`, `schemas`, `services`, `repositories`, `models`, `security`, `db`, `ai`. No microservices. |
| **Database & ORM** | PostgreSQL + SQLAlchemy 2.x + Alembic | UUID primary keys, UTC `timestamptz`, foreign keys, explicit indexes, check constraints. Deprecate pure psycopg3 prototype in favor of SQLAlchemy 2.0 ORM + Alembic migrations. |
| **Authentication & Sessions** | Email/Password + Argon2id + Opaque Sessions | Server-side sessions with sha256 token hashes stored in `user_sessions`. Cookie `mp_session` is `HttpOnly`, `SameSite=Lax`, `Secure` in production. Rotated on login and refresh. Revoked on logout. |
| **CSRF Strategy** | Session-bound CSRF Token | Server issues `csrf_token` in `AuthResponse`; client passes `X-CSRF-Token` header on state-changing requests (`POST`, `PATCH`, `DELETE`). |
| **Authorization / Scoping** | Server-Derived Ownership | Merchant context and identity are ALWAYS extracted from authenticated session. Client never supplies or overrides `merchant_id`. |
| **AI Integration** | Provider Abstraction + Groq Adapter | Server-side Groq integration using `llama-3.3-70b-versatile` behind `LLMProvider` interface. System prompt grounded with active merchant context. Bounded message history. Timeouts, retries, output validation. |
| **Chat Execution Mode** | Synchronous Request / Response | No streaming in MVP. User message is persisted to DB *before* provider invocation. If AI fails, user message status is preserved as `failed` and 502 returned with retry opportunity. |
| **Suggested Actions** | Merchant Approval Workflow | Reply drafts, summaries, and recommendations are created in `suggested_actions` table with status `pending`. Merchant can approve or dismiss. Approvals record a decision in DB; they NEVER trigger external WhatsApp, SMS, email, or financial transactions. |
| **Dashboard Metrics** | Live DB Computations | Counts of conversations, messages, and pending actions computed directly from persisted records. Zero hardcoded demo numbers. |
| **Deployment Target** | Docker / Render | Dockerfile for backend and static build for frontend. Managed PostgreSQL with persistent storage. |
| **Testing Strategy** | Multi-Tier Automated Gates | Pytest unit, repository (PostgreSQL/SQLite fallback for local unit tests), API integration (TestClient), security isolation tests, and frontend build/lint checks. LLM calls mocked in CI/automated runs. |

---

## 3. Scope Reconciliation: Out of Scope for MVP

The following items present in the legacy codebase or general wishlist are explicitly confirmed **OUT OF SCOPE** for MVP:

1. **Automated WhatsApp/SMS outbound delivery** (`/v1/tick` and `/v1/reply` Vera bot automation):
   - In MVP, the assistant is a merchant-facing copilot workspace, NOT an autonomous customer-facing messaging bot.
   - The legacy `services/engagement_planner.py` and `services/reply_service.py` rules will be preserved for reference or adapted into internal draft recommendations, but deprecated from active routes in favor of canonical OpenAPI endpoints.
2. **External financial transactions, refunds, bookings, and integrations with Magicpin internal services.**
3. **Microservices, Kubernetes, Redis, Vector Databases (Chroma/Pinecone), and Celery workers.**
   - Simple PostgreSQL query filtering is sufficient for merchant context retrieval in MVP.
