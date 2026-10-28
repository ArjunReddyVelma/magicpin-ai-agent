"""
scripts/build_report_content.py
Defines the authoritative text, tables, figures, citations, and structure
for the Magicpin AI Agent Final SPSU Internship Report.
"""

PROJECT_TITLE = "MAGICPIN AI AGENT – CONTEXT-AWARE CONVERSATIONAL AI BACKEND"
PROJECT_SUBTITLE = "2-Month Summer Internship Report"
DEGREE = "Bachelor of Technology"
BRANCH = "Computer Science and Engineering"
BRANCH_SHORT = "B.Tech. (CSE)"
STUDENT_NAME = "Arjun Reddy"
ENROLLMENT_NO = "23CS002692"
SEMESTER = "VII"
ACADEMIC_YEAR = "2026"

UNIVERSITY = "Sir Padampat Singhania University"
CITY_PIN = "Udaipur, 313601, Rajasthan, India"
DEPARTMENT = "Department of Computing and Informatics"
SCHOOL = "School of Engineering & Sciences"

EXTERNAL_GUIDE_NAME = "Ashuthosh Gupta"
EXTERNAL_GUIDE_DESIG = "Senior Engineering Mentor / Industry Guide"
EXTERNAL_GUIDE_ORG = "Magicpin (Quickheal Technologies / External Sponsor)"
EXTERNAL_GUIDE_ADDR = "Gurugram / Remote Mentorship Office"
EXTERNAL_GUIDE_WEB = "https://magicpin.in"

INTERNAL_GUIDE_NAME = "[Name of the Internal Faculty Guide]"
INTERNAL_GUIDE_DESIG = "Assistant Professor / Faculty Mentor"
INTERNAL_GUIDE_AFFIL = f"{DEPARTMENT}, {SCHOOL}, {UNIVERSITY}"

DEAN_NAME = "Dr. Amit Kumar Goel"
DEAN_TITLE = "Professor and Dean"
DEAN_DEPT = f"{DEPARTMENT},\n{SCHOOL},\n{UNIVERSITY},\n{CITY_PIN}"

FOOTER_TEMPLATE = f"{STUDENT_NAME.upper()} /{BRANCH_SHORT}/SPSU/ MAGICPIN AI AGENT/{ACADEMIC_YEAR}/{SEMESTER}/"

LOGO_PATH = "docs/figures/format_media/image1.png"

ABBREVIATIONS = [
    ("ACID", "Atomicity, Consistency, Isolation, Durability"),
    ("AI", "Artificial Intelligence"),
    ("API", "Application Programming Interface"),
    ("Argon2id", "Key Derivation / Cryptographic Password Hashing Algorithm"),
    ("ASGI", "Asynchronous Server Gateway Interface"),
    ("CRUD", "Create, Read, Update, Delete"),
    ("CSRF", "Cross-Site Request Forgery"),
    ("DB", "Database"),
    ("ERD", "Entity-Relationship Diagram"),
    ("ETag", "Entity Tag (HTTP Header for Cache & Optimistic Concurrency)"),
    ("FIFO", "First-In, First-Out"),
    ("FK", "Foreign Key"),
    ("HITL", "Human-in-the-Loop"),
    ("HMAC", "Hash-based Message Authentication Code"),
    ("HTTP", "Hypertext Transfer Protocol"),
    ("HTTPS", "Hypertext Transfer Protocol Secure"),
    ("IDOR", "Insecure Direct Object Reference"),
    ("JSON", "JavaScript Object Notation"),
    ("LLM", "Large Language Model"),
    ("MVP", "Minimum Viable Product"),
    ("OAS", "OpenAPI Specification"),
    ("ORM", "Object-Relational Mapping"),
    ("PK", "Primary Key"),
    ("PRD", "Product Requirements Document"),
    ("RAG", "Retrieval-Augmented Generation"),
    ("REST", "Representational State Transfer"),
    ("SHA-256", "Secure Hash Algorithm 256-bit"),
    ("SPA", "Single-Page Application"),
    ("SQL", "Structured Query Language"),
    ("SSE", "Server-Sent Events"),
    ("UI / UX", "User Interface / User Experience"),
    ("URI / URL", "Uniform Resource Identifier / Uniform Resource Locator"),
    ("UTC", "Coordinated Universal Time"),
    ("UUID", "Universally Unique Identifier"),
    ("Vite", "Frontend Build Tool and Development Server"),
    ("WABA", "WhatsApp Business Account")
]

print("Loaded report metadata and abbreviations.")
