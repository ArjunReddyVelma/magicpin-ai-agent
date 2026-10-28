"""
scripts/report_data.py
Complete data structures and full textual content for the Magicpin AI Agent Final SPSU Internship Report.
"""

from scripts.build_report_content import (
    PROJECT_TITLE, PROJECT_SUBTITLE, DEGREE, BRANCH, BRANCH_SHORT,
    STUDENT_NAME, ENROLLMENT_NO, SEMESTER, ACADEMIC_YEAR,
    UNIVERSITY, CITY_PIN, DEPARTMENT, SCHOOL,
    EXTERNAL_GUIDE_NAME, EXTERNAL_GUIDE_DESIG, EXTERNAL_GUIDE_ORG, EXTERNAL_GUIDE_ADDR, EXTERNAL_GUIDE_WEB,
    INTERNAL_GUIDE_NAME, INTERNAL_GUIDE_DESIG, INTERNAL_GUIDE_AFFIL,
    DEAN_NAME, DEAN_TITLE, DEAN_DEPT, FOOTER_TEMPLATE, LOGO_PATH, ABBREVIATIONS
)

DECLARATION_TEXT = (
    f"I, {STUDENT_NAME}, student of {BRANCH_SHORT}, hereby declare that the 2-Month Summer Internship "
    f"project report titled \"{PROJECT_TITLE}\", submitted to the {DEPARTMENT}, {SCHOOL}, "
    f"{UNIVERSITY}, Udaipur, Rajasthan, towards the partial fulfillment of the requirement for the award "
    f"of the degree of {DEGREE}, is my original work. The work described in this report has not previously "
    f"formed the basis for the award of any degree, diploma, or similar academic recognition."
)

CERTIFICATE_TEXT = (
    f"This is to certify that the 2-Month Summer Internship project entitled '{PROJECT_TITLE}' "
    f"being submitted by {STUDENT_NAME} [{ENROLLMENT_NO}], submitted towards the partial fulfillment "
    f"of the requirement for the award of the degree of {DEGREE} in {BRANCH}, has been carried out "
    f"under my supervision and guidance.\n\n"
    f"The matter embodied in this report has not been submitted, in part or in full, to any other "
    f"university or institute for the award of any degree, diploma or certificate."
)

ACKNOWLEDGEMENT_TEXT = (
    f"I would like to express my sincere gratitude to my project mentor {EXTERNAL_GUIDE_NAME} Sir for providing me "
    f"with the invaluable opportunity to work on the Magicpin AI Agent project. His insightful guidance, technical "
    f"mentorship, and continuous encouragement helped me understand the practical dimensions of modern backend and "
    f"full-stack software engineering, including REST API design, Large Language Model (LLM) integration, multi-tenant "
    f"context grounding, persistent relational storage, automated test suites, and containerized cloud deployment.\n\n"
    f"I also extend my heartfelt appreciation to {DEAN_NAME}, {DEAN_TITLE}, along with the faculty members and staff of "
    f"the {DEPARTMENT}, {SCHOOL}, {UNIVERSITY}, for providing an outstanding academic environment, necessary computing "
    f"facilities, and institutional support throughout my summer internship.\n\n"
    f"Finally, I would like to thank my family, peers, and fellow students for their unceasing encouragement, constructive "
    f"feedback, and moral support during the development, testing, and documentation of this project."
)

ABSTRACT_TEXT = (
    "The Magicpin AI Agent is a context-aware conversational AI assistant and merchant support workspace "
    "engineered to streamline customer service operations for local commerce and retail merchants. Traditional "
    "stateless chatbot integrations interact with Large Language Models (LLMs) in isolation, leading to frequent "
    "hallucinations, ignorance of store-specific policies, loss of conversational context across turns, and "
    "unmonitored automated responses that risk customer relationships. This project resolves these critical "
    "weaknesses by establishing a production-grade full-stack architecture that combines a high-performance "
    "FastAPI backend, a durable PostgreSQL relational persistence layer with Alembic migrations, and an accessible "
    "React/TypeScript single-page web interface.\n\n"
    "The core system incorporates multi-tenant security featuring Argon2id password hashing, opaque SHA-256 hashed "
    "session tokens, session-bound CSRF protection, and server-derived merchant scoping. Business context—including "
    "store hours, refund policies, and catalog details—is managed with optimistic concurrency control using integer "
    "versioning and HTTP ETag headers. Conversational turns are persisted in PostgreSQL prior to provider invocation, "
    "ensuring zero message loss during upstream failures and facilitating seamless client-driven retries. When eligible "
    "customer support inquiries occur, the system deterministically generates draft responses held in an audited "
    "Human-in-the-Loop (HITL) review queue. Crucially, approving an action updates internal review state without "
    "triggering external dispatches, establishing a strict safety boundary. The architecture is validated against "
    "a comprehensive test hierarchy comprising 77 backend automated tests and 42 frontend tests, deployed on Render "
    "cloud services, and provides a clear blueprint for future extensions such as WhatsApp Business API integration."
)

TABLES_DATA = {
    "1.1": {
        "title": "Table 1.1: Project Objectives and Scope Matrix",
        "headers": ["Objective Area", "Architectural Scope", "Verification Criteria"],
        "rows": [
            ["Context Management", "Store, update, and isolate merchant business policies, store hours, and FAQs.", "CRUD API with optimistic versioning (ETag) and multi-tenant isolation."],
            ["Conversational Memory", "Maintain session-based multi-turn conversation history in PostgreSQL.", "Deterministic chronological ordering and bounded history window."],
            ["LLM Grounding", "Construct structured system prompts grounded in verified merchant policies.", "Groq Cloud API integration (llama-3.3-70b-versatile) with anti-hallucination rules."],
            ["Human-in-the-Loop Review", "Generate reply drafts held in a pending review queue requiring merchant approval.", "Deterministic eligibility heuristics and review-only database state transitions."],
            ["Session Security", "Implement secure authentication, session management, and CSRF protection.", "Argon2id password hashing, opaque session token hashing, and CSRF validation."],
            ["Frontend Workspace", "Develop a responsive merchant copilot interface and live metric dashboard.", "React 18, TypeScript, Vite, Tailwind CSS with live database computations."],
            ["Automated Testing", "Validate multi-tenant isolation, database migrations, and concurrency.", "Pytest test suite covering unit, integration, and security test gates."]
        ]
    },
    "3.1": {
        "title": "Table 3.1: Tools, Frameworks, and Technologies Overview",
        "headers": ["Component / Layer", "Technology", "Version", "Role & Engineering Purpose"],
        "rows": [
            ["Backend Framework", "FastAPI", ">= 0.115.0", "Asynchronous ASGI web framework for REST API routing and documentation."],
            ["ASGI Server", "Uvicorn", ">= 0.30.0", "Production ASGI worker server executing asynchronous request loops."],
            ["Database ORM", "SQLAlchemy", ">= 2.0.0", "Typed declarative relational object mapping with ACID transaction support."],
            ["Database Driver", "Psycopg 3", ">= 3.2.0", "High-performance PostgreSQL database adapter for Python."],
            ["Database Migrations", "Alembic", ">= 1.13.0", "Version-controlled database schema migration engine."],
            ["Relational Database", "PostgreSQL", "16.x", "Persistent relational storage for tenants, contexts, and conversations."],
            ["Schema Validation", "Pydantic v2", ">= 2.9.0", "Strict runtime request/response payload typing and serialization."],
            ["Frontend Framework", "React", "^18.3.1", "Component-based single-page merchant copilot application."],
            ["Programming Language", "TypeScript", "^5.5.0", "Static typing for frontend components, API contracts, and state."],
            ["Build Tool", "Vite", "^5.4.0", "Next-generation frontend bundler and local development server."],
            ["Styling Framework", "Tailwind CSS", "^3.4.0", "Utility-first CSS framework for clean, professional SaaS layout."],
            ["AI Inference Provider", "Groq Cloud API", "Llama 3.3 70B", "High-speed inference provider backing conversational reasoning."],
            ["Authentication / Crypt", "Argon2id / Secrets", "Latest", "Cryptographic password hashing and opaque session token generation."],
            ["Cloud Hosting", "Render", "Cloud PaaS", "Dockerized backend web service and managed PostgreSQL hosting."]
        ]
    },
    "4.1": {
        "title": "Table 4.1: Core REST API Resource Endpoints (OpenAPI Contract)",
        "headers": ["HTTP Method", "Endpoint Path", "Resource Scope", "Description & Security Constraints"],
        "rows": [
            ["POST", "/v1/auth/register", "Public Auth", "Registers a new merchant user and initializes an isolated merchant profile."],
            ["POST", "/v1/auth/login", "Public Auth", "Authenticates user with Argon2id; issues opaque session cookie and CSRF token."],
            ["POST", "/v1/auth/logout", "Authenticated", "Revokes active session token and clears client session cookies."],
            ["GET", "/v1/auth/me", "Authenticated", "Retrieves current authenticated merchant user and profile metadata."],
            ["GET", "/v1/merchant/profile", "Merchant Workspace", "Fetches active merchant profile details (business name, category, city)."],
            ["PATCH", "/v1/merchant/profile", "Merchant Workspace", "Updates merchant profile fields; protected by session-bound CSRF token."],
            ["POST", "/v1/context", "Context Manager", "Creates merchant business policy or FAQ; establishes optimistic version 1."],
            ["GET", "/v1/context", "Context Manager", "Lists merchant context items with type filtering and ETag caching headers."],
            ["PATCH", "/v1/context/{id}", "Context Manager", "Updates context content with optimistic locking (If-Match version check)."],
            ["DELETE", "/v1/context/{id}", "Context Manager", "Deletes context item belonging strictly to authenticated merchant."],
            ["POST", "/v1/conversations", "Chat & Memory", "Initializes a persistent conversation session for customer inquiry handling."],
            ["GET", "/v1/conversations", "Chat & Memory", "Lists merchant conversations with pagination, search, and status filters."],
            ["GET", "/v1/conversations/{id}", "Chat & Memory", "Retrieves full conversation session and bounded historical messages."],
            ["POST", "/v1/conversations/{id}/messages", "AI Copilot Turn", "Persists user message turn; invokes grounded Groq AI; handles retry."],
            ["GET", "/v1/actions", "Review Queue", "Lists pending, approved, or dismissed reply drafts in review queue."],
            ["POST", "/v1/actions/{id}/approve", "Human-in-the-Loop", "Approves pending reply draft; updates review state (no external send)."],
            ["POST", "/v1/actions/{id}/dismiss", "Human-in-the-Loop", "Dismisses pending draft action; records rejection audit timestamp."],
            ["GET", "/v1/dashboard/summary", "Analytics", "Computes live PostgreSQL metrics (active contexts, conversations, drafts)."],
            ["GET", "/v1/healthz", "Monitoring", "Liveness probe verifying that the application web service is running."],
            ["GET", "/v1/readyz", "Monitoring", "Readiness probe confirming successful connectivity to PostgreSQL."]
        ]
    },
    "4.2": {
        "title": "Table 4.2: Relational Database Schema Entity Specifications",
        "headers": ["Entity Table", "Primary Key", "Key Attributes & Types", "Relational Constraints & Foreign Keys"],
        "rows": [
            ["users", "id (UUID)", "email (VARCHAR 255), hashed_password (TEXT), is_active (BOOL), created_at, updated_at", "Unique index on email; Argon2id password hash."],
            ["merchant_profiles", "id (UUID)", "business_name (VARCHAR 255), category (VARCHAR 100), city (VARCHAR 100)", "FK: user_id -> users.id (ON DELETE CASCADE); unique user mapping."],
            ["user_sessions", "id (UUID)", "token_hash (VARCHAR 64), expires_at (TIMESTAMPTZ), last_active_at", "FK: user_id -> users.id (ON DELETE CASCADE); SHA-256 unique token hash."],
            ["context_items", "id (UUID)", "item_type (VARCHAR 50), content (TEXT), version (INT), is_active (BOOL)", "FK: merchant_id -> merchant_profiles.id; optimistic lock version."],
            ["conversations", "id (UUID)", "status (VARCHAR 30), archived_at (TIMESTAMPTZ), created_at, updated_at", "FK: merchant_id -> merchant_profiles.id; index on merchant_id."],
            ["messages", "id (UUID)", "role (VARCHAR 20), content (TEXT), status (VARCHAR 20), idempotency_key", "FK: conversation_id -> conversations.id; index on (conversation_id, created_at)."],
            ["suggested_actions", "id (UUID)", "action_type (VARCHAR 50), draft_text (TEXT), status (VARCHAR 20), reviewed_at", "FK: conversation_id -> conversations.id; status enum (pending/approved/dismissed)."],
            ["audit_events", "id (UUID)", "event_type (VARCHAR 100), client_ip (VARCHAR 45), details (JSONB), created_at", "Audit log for login rate limiting and security surveillance."]
        ]
    },
    "5.1": {
        "title": "Table 5.1: Major Software Modules and Architectural Responsibilities",
        "headers": ["Subsystem / Directory", "Core Module Files", "Architectural Responsibility & Function"],
        "rows": [
            ["API Routing Layer", "backend/app/api/v1/routes/*.py", "Exposes REST endpoints; orchestrates HTTP status codes, headers, and dependency injection."],
            ["Core Security & Config", "backend/app/core/security.py, config.py", "Enforces Argon2id hashing, opaque token generation, CSRF validation, and Pydantic settings."],
            ["Data Access Layer", "backend/app/repositories/*.py", "Encapsulates parameterized SQLAlchemy 2.0 ORM queries with strict tenant isolation."],
            ["Business Logic Services", "backend/app/services/*.py", "Coordinates core workflows: auth, context versioning, chat turns, and action reviews."],
            ["AI Provider Abstraction", "backend/app/ai/groq_provider.py, prompt_builder.py", "Manages Groq API integration, dynamic policy grounding, anti-hallucination, and validation."],
            ["Database Persistence", "backend/app/models/*.py, backend/migrations/*", "Defines relational entities, constraints, indexes, and Alembic version-controlled migrations."],
            ["Frontend Single Page App", "frontend/src/pages/*.tsx, frontend/src/api/*.ts", "Delivers interactive React interface: Dashboard, Chat, Context Manager, Actions Queue, Settings."]
        ]
    },
    "6.1": {
        "title": "Table 6.1: Representative Functional Outcomes and Implementation Matrix",
        "headers": ["Functional Domain", "Implemented Capability", "Observed Outcome & Production Verification"],
        "rows": [
            ["Merchant Authentication", "Registration, Login, Logout, Session Rotation", "Argon2id hashing verified; opaque token rotation verified; CSRF protection active."],
            ["Business Context CRUD", "Creation, Retrieval, Patching, Deletion", "Policies grounded; version incrementing verified; HTTP 409 conflict handling active."],
            ["Context-Aware Chat", "Multi-turn inquiry handling grounded in policies", "System prompt injects active store hours/policies; Groq Llama 3.3 inference verified."],
            ["Turn Recovery & Retries", "Persistence before AI execution; retry failed turn", "Message saved prior to AI call; HTTP 502 with failed_message_id enables clean retry."],
            ["Chat-to-Action Pipeline", "Deterministic reply draft creation under row lock", "Customer support inquiries automatically generate pending reply drafts in database."],
            ["Review Queue (HITL)", "Approve or dismiss pending action drafts", "Review-only policy verified: PostgreSQL status updated without unreviewed external dispatch."],
            ["Dashboard Metrics", "Real-time summary calculation from PostgreSQL", "Live computation of active contexts, conversation count, and pending review actions."],
            ["Containerized Deployment", "Docker web service on Render cloud infrastructure", "Liveness (/v1/healthz) and readiness (/v1/readyz) probes operational."]
        ]
    },
    "7.1": {
        "title": "Table 7.1: Multi-Tier Testing Strategy, Quality Gates, and Test Areas",
        "headers": ["Testing Tier", "Test Scope & Directory", "Verified Areas & Assertions"],
        "rows": [
            ["Unit Tests", "backend/tests/unit/", "Argon2id hashing, opaque session token generation, CSRF binding, PromptBuilder grounding, ResponseValidator."],
            ["Repository Integration", "backend/tests/integration/test_repositories.py", "SQLAlchemy CRUD, normalization, deterministic ordering, optimistic concurrency, and tenant isolation."],
            ["Database Migrations", "backend/tests/integration/test_migrations.py", "Alembic full upgrade to head and complete downgrade to base reversibility cycle."],
            ["API Route Testing", "backend/tests/api/", "FastAPI TestClient testing of Auth, Context, Conversations, Messages, Actions, Dashboard, and Health."],
            ["Security & Tenant Isolation", "backend/tests/security/", "Cross-merchant context shielding, conversation isolation, session token hijacking prevention, rate limiting."],
            ["Concurrency & Recovery", "backend/tests/integration/test_chat_concurrency.py", "Row-level locking (with_for_update), provider timeout recovery, and idempotency key deduplication."],
            ["End-to-End User Journey", "backend/tests/integration/test_e2e_user_journey.py", "Simulated lifecycle: registration -> profile setup -> policy creation -> chat -> draft creation -> approval."],
            ["Frontend Test Suite", "frontend/src/__tests__/", "Component rendering, typed API client integration, authentication state management, and production build."]
        ]
    }
}

FIGURES_DATA = {
    "4.1": {
        "path": "docs/figures/report_media/image2.png",
        "caption": "Figure 4.1: High-Level System Architecture and Layered Monolith Structure",
        "desc": "Architectural block diagram showing client communication with FastAPI, layered modular services, prompt builder, memory manager, Groq LLM service, and persistent PostgreSQL storage."
    },
    "4.2": {
        "path": "docs/figures/report_media/image3.png",
        "caption": "Figure 4.2: End-to-End Request, Grounding, and Failure Recovery Workflow",
        "desc": "Sequential workflow illustrating user message ingress, persistence before AI invocation, context retrieval, prompt construction, Groq LLM execution, response processing, and safe retry recovery."
    },
    "4.3": {
        "path": "docs/figures/generated/figure_4_3_erd.png",
        "caption": "Figure 4.3: Magicpin AI Agent — PostgreSQL Relational Schema (ERD)",
        "desc": "Entity-Relationship Diagram depicting users, merchant_profiles, user_sessions, context_items, conversations, messages, suggested_actions, and audit_events with foreign keys and UUIDs."
    },
    "4.4": {
        "path": "docs/figures/generated/figure_4_4_hitl.png",
        "caption": "Figure 4.4: Human-in-the-Loop Suggested Actions Review State Machine",
        "desc": "State transition diagram illustrating inbound turn classification, draft creation in pending state, merchant approval or dismissal, and the strict zero-external-side-effect security boundary."
    },
    "4.5": {
        "path": "docs/figures/generated/figure_4_5_whatsapp.png",
        "caption": "Figure 4.5: Proposed Future WhatsApp Business Integration Architecture",
        "desc": "End-to-end proposed integration flow connecting WhatsApp users to the merchant copilot via Meta Cloud API webhooks, grounded AI drafting, human review, and authorized dispatch."
    },
    "6.1": {
        "path": "docs/figures/report_media/image4.png",
        "caption": "Figure 6.1: Cloud Deployment and Containerized Service Architecture",
        "desc": "Deployment topology showing the browser/application client communicating over HTTPS to the Render web service running FastAPI and Uvicorn in Docker, connected to managed PostgreSQL and Groq LLM API."
    },
    "A.1": {
        "path": "docs/figures/annexure/figure_a1_render.png",
        "caption": "Figure A.1: Deployed Magicpin AI Agent Service on Render Cloud",
        "desc": "Dashboard verification showing the active, deployed web service instance running in Docker on Render cloud infrastructure."
    },
    "A.2": {
        "path": "docs/figures/annexure/figure_a2_swagger.png",
        "caption": "Figure A.2: FastAPI Interactive Swagger API Documentation Interface",
        "desc": "Interactive OpenAPI documentation interface (/docs) exposing verified REST endpoints for authentication, context, conversations, chat turns, and suggested actions."
    },
    "A.3": {
        "path": "docs/figures/annexure/figure_a3_healthz.png",
        "caption": "Figure A.3: Production API Health Check Endpoint Response (GET /v1/healthz)",
        "desc": "HTTP 200 OK liveness response from the production deployment confirming active application health."
    },
    "A.4": {
        "path": "docs/figures/annexure/figure_a4_context_req.png",
        "caption": "Figure A.4: Merchant Context Storage Request Payload (POST /v1/context)",
        "desc": "JSON request body demonstrating merchant context ingestion containing store name, category, city, operating hours, and cancellation policy."
    },
    "A.5": {
        "path": "docs/figures/annexure/figure_a5_context_res.png",
        "caption": "Figure A.5: Context Creation and Persistence Acknowledgment Response",
        "desc": "HTTP 200 response returning acknowledgment ID and ETag version tag confirming persistent storage of merchant business context."
    },
    "A.6": {
        "path": "docs/figures/annexure/figure_a6_chat_res.png",
        "caption": "Figure A.6: Context-Aware Chat Turn Grounded in Merchant Profile",
        "desc": "End-to-end chat turn demonstrating factual AI response generation grounded strictly in the merchant's saved business policies without hallucination."
    },
    "A.7": {
        "path": "docs/figures/annexure/figure_a7_memory_res.png",
        "caption": "Figure A.7: Persistent Conversation Session Memory Retrieval (GET /v1/conversations/{id})",
        "desc": "Retrieved conversation session payload demonstrating multi-turn message history preservation, deterministic timestamps, and role-based tracking."
    }
}

REFERENCES = [
    "[1] S. Yao, J. Zhao, D. Yu, N. Du, I. Shafran, K. Narasimhan, and Y. Cao, \"ReAct: Synergizing Reasoning and Acting in Language Models,\" arXiv preprint arXiv:2210.03629, 2022.",
    "[2] P. Lewis, E. Perez, A. Piktus, F. Petroni, V. Karpukhin, N. Goyal, H. Küttler, M. Lewis, W.-t. Yih, T. Rocktäschel, S. Riedel, and D. Kiela, \"Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks,\" in Advances in Neural Information Processing Systems, vol. 33, pp. 9459–9474, 2020.",
    "[3] Groq Inc., \"Groq LPU Inference Engine and API Architecture Documentation,\" Groq Cloud Documentation, 2024. [Online]. Available: https://groq.com/docs",
    "[4] FastAPI Authors, \"FastAPI: Modern, Fast (High-Performance), Web Framework for Building APIs with Python 3.8+,\" [Online]. Available: https://fastapi.tiangolo.com/",
    "[5] PostgreSQL Global Development Group, \"PostgreSQL 16 Documentation: Concurrency Control and ACID Transactions,\" 2024. [Online]. Available: https://www.postgresql.org/docs/16/",
    "[6] SQLAlchemy Authors, \"SQLAlchemy 2.0 Unified Documentation and Declarative Mapping,\" 2024. [Online]. Available: https://docs.sqlalchemy.org/en/20/",
    "[7] M. Fowler, \"MonolithFirst: Why Starting with a Monolith is Often Best,\" Martin Fowler Architecture Blog, 2015. [Online]. Available: https://martinfowler.com/bliki/MonolithFirst.html",
    "[8] Alembic Authors, \"Alembic: Lightweight Database Migration Tool for Usage with SQLAlchemy,\" 2024. [Online]. Available: https://alembic.sqlalchemy.org/",
    "[9] React Authors, \"React 18: The Library for Web and Native User Interfaces,\" Meta Open Source, 2024. [Online]. Available: https://react.dev/",
    "[10] Meta Platforms Inc., \"WhatsApp Business Platform Cloud API Overview and Webhook Security,\" Meta for Developers, 2026. [Online]. Available: https://developers.facebook.com/docs/whatsapp/cloud-api",
    "[11] OWASP Foundation, \"OWASP Top 10 API Security Risks: Broken Object Level Authorization and SSRF Prevention,\" 2023. [Online]. Available: https://owasp.org/API-Security/",
    "[12] Render Services Inc., \"Render Cloud Application Hosting and Managed PostgreSQL Architecture,\" 2024. [Online]. Available: https://render.com/docs"
]

print("Loaded all report data, tables, figures, and references.")
