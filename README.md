# 🤖 Magicpin AI Agent

![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-Framework-green?style=for-the-badge&logo=fastapi)
![GitHub last commit](https://img.shields.io/github/last-commit/ArjunReddyVelma/magicpin-ai-agent?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)

An **AI-powered Merchant Assistant** built using **FastAPI** that enables merchants to interact with an intelligent chatbot capable of understanding merchant-specific business context and maintaining conversation memory across sessions.

The project demonstrates modern backend development practices, modular software architecture, REST API design, and Large Language Model (LLM) integration.

---

# 📖 Table of Contents

- Overview
- Features
- Tech Stack
- System Architecture
- Project Structure
- API Endpoints
- Installation
- Running the Project
- Example Workflow
- Screenshots
- Future Improvements
- Learning Outcomes
- Author

---

# 🚀 Overview

Magicpin AI Agent is designed to simulate an intelligent merchant assistant capable of:

- Understanding merchant business information
- Maintaining conversation history
- Generating contextual AI responses
- Managing merchant-specific sessions
- Building dynamic prompts for LLMs

The application follows a modular architecture where each component has a dedicated responsibility, making the project scalable and maintainable.

---

# ✨ Features

✅ Merchant Context Management

✅ Session-Based Conversation Memory

✅ AI-powered Chat Responses

✅ Prompt Engineering

✅ RESTful APIs

✅ Modular Service Architecture

✅ FastAPI Backend

✅ OpenAPI (Swagger) Documentation

✅ Environment Variable Configuration

✅ Easy to Extend

---

# 🛠 Tech Stack

| Category | Technology |
|----------|------------|
| Language | Python |
| Backend Framework | FastAPI |
| AI Integration | OpenAI Compatible LLM |
| Validation | Pydantic |
| API Server | Uvicorn |
| Storage | In-Memory Storage |
| Documentation | Swagger UI |
| Version Control | Git & GitHub |

---

# 🏗 System Architecture

```text
                    Client
                       │
                       │ HTTP Request
                       ▼
                FastAPI Application
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
 Context Manager  Memory Manager   LLM Service
        │              │              │
        └──────────Prompt Builder─────┘
                       │
                       ▼
             Response Processor
                       │
                       ▼
                  JSON Response
```

---

# 📂 Project Structure

```text
magicpin-ai-agent/
│
├── api/
│   ├── routes.py
│   ├── schemas.py
│   └── __init__.py
│
├── services/
│   ├── context_manager.py
│   ├── memory_manager.py
│   ├── llm_service.py
│   ├── prompt_builder.py
│   ├── response_processor.py
│   └── __init__.py
│
├── storage/
│   ├── context_store.py
│   ├── conversation_store.py
│   └── __init__.py
│
├── tests/
│
├── utils/
│
├── config.py
├── main.py
├── requirements.txt
└── README.md
```

---

# 🔄 Application Workflow

```text
Save Merchant Context
          │
          ▼
Create Conversation
          │
          ▼
Receive User Message
          │
          ▼
Retrieve Merchant Context
          │
          ▼
Retrieve Conversation Memory
          │
          ▼
Generate Prompt
          │
          ▼
LLM Generates Response
          │
          ▼
Store Conversation
          │
          ▼
Return AI Response
```

---

# 🌐 REST API Endpoints

## 1️⃣ Save Merchant Context

```
POST /v1/context
```

Example Request

```json
{
    "merchant_id":"merchant_001",
    "context":{
        "name":"Paradise Biryani",
        "category":"Restaurant",
        "city":"Hyderabad"
    }
}
```

---

## 2️⃣ Create Conversation

```
POST /v1/conversations
```

Example Request

```json
{
    "merchant_id":"merchant_001"
}
```

Example Response

```json
{
    "session_id":"abc123xyz"
}
```

---

## 3️⃣ Chat with AI

```
POST /v1/chat
```

Example Request

```json
{
    "merchant_id":"merchant_001",
    "session_id":"abc123xyz",
    "message":"Suggest marketing ideas."
}
```

---

## 4️⃣ Get Conversation History

```
GET /v1/conversations/{session_id}
```

---

# ⚙ Installation

Clone the repository

```bash
git clone https://github.com/ArjunReddyVelma/magicpin-ai-agent.git
```

Move into project

```bash
cd magicpin-ai-agent
```

Create virtual environment

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### macOS/Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

Install dependencies

```bash
pip install -r requirements.txt
```

---

# ▶ Running the Project

```bash
uvicorn main:app --reload
```

Server starts at

```
http://127.0.0.1:8000
```

Swagger Documentation

```
http://127.0.0.1:8000/docs
```

ReDoc Documentation

```
http://127.0.0.1:8000/redoc
```

---

# 🧪 Testing API

Swagger UI allows testing all APIs directly from the browser.

Example flow:

1. Save Merchant Context

↓

2. Create Conversation

↓

3. Chat with AI

↓

4. Retrieve Conversation History

---

# 🚀 Future Improvements

- PostgreSQL Integration
- MongoDB Support
- Redis Conversation Memory
- Docker Deployment
- JWT Authentication
- Role-Based Access Control
- Streaming AI Responses
- Kubernetes Deployment
- Unit Testing
- CI/CD using GitHub Actions
- Cloud Deployment on AWS

---

# 📚 Learning Outcomes

Through this project I gained hands-on experience with:

- FastAPI Backend Development
- REST API Design
- Python Project Structuring
- Prompt Engineering
- Large Language Models
- Conversation Memory
- Context Management
- Software Architecture
- API Documentation
- Git and GitHub Workflow

---

# 🎯 Why This Project?

This project was built to demonstrate backend engineering skills and AI integration by developing an intelligent merchant assistant capable of handling contextual conversations using modular software architecture and RESTful APIs.

---

# 👨‍💻 Author

**Arjun Reddy Velma**

📧 Email: velma.btech2023@spsu.ac.in

🔗 GitHub: https://github.com/ArjunReddyVelma

---


