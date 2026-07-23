# 🚀 Stateful Cold Email Assistant

> **Enterprise-grade AI-powered cold email automation built with LangGraph, LangChain, FastAPI, and Pydantic.**

⚠️ Important: This repository includes a .env.example template only. To test the complete workflow (LLM generation, Gmail integration, Apollo, Clay, etc.), you must supply your own valid API keys and OAuth credentials. No production secrets are included in this repository for security reasons.

The **Stateful Cold Email Assistant** is a production-ready, multi-agent workflow for automating personalized outbound email campaigns. It combines lead enrichment, AI-powered email generation, human approval, Gmail integration, and reply intelligence into a single stateful pipeline powered by **LangGraph**.

Designed with modularity, security, and scalability in mind, the system supports both **interactive CLI** and **REST API** interfaces, making it suitable for developers, startups, and enterprise sales teams.

---

## ✨ Features

### 🤖 AI-Powered Cold Email Generation

* Generates concise, personalized cold emails using LLMs.
* Optimized for high-response outreach.
* Produces emails under **75 words** with natural, conversational tone.
* Supports both **OpenAI** and **local Ollama models**.

---

### 📊 Lead Enrichment

Automatically enriches prospects using market intelligence including:

* Company information
* Recent funding/news
* Hiring trends
* Technology stack
* Business signals

Supported integrations include:

* Apollo
* Clay
* Custom enrichment providers

---

### 🔄 Stateful Multi-Agent Workflow

Built using **LangGraph**, allowing each execution to maintain persistent state throughout the pipeline.

Workflow includes:

1. Lead Intake
2. Lead Enrichment
3. Email Draft Generation
4. Human Review
5. Gmail Delivery
6. Reply Classification

---

### 🛑 Human-in-the-Loop (HITL)

Instead of automatically sending emails, the workflow pauses before delivery using LangGraph checkpoints.

Available actions:

* ✅ Approve draft
* ✏️ Request revisions
* ❌ Reject and terminate workflow

This enables safe production deployment while maintaining human oversight.

---

### 📧 Gmail Integration

Supports two delivery modes:

* **Draft Mode** *(recommended)* — Creates Gmail drafts for manual review.
* **Send Mode** — Sends emails directly using the Gmail API.

---

### 🧠 Reply Intelligence

Automatically analyzes recipient replies and classifies intent into predefined categories:

| Intent            | Description                               |
| ----------------- | ----------------------------------------- |
| 🔥 HOT_LEAD       | Interested in continuing the conversation |
| ❌ NOT_INTERESTED  | Explicit rejection                        |
| 🏖️ OUT_OF_OFFICE | Automatic vacation reply                  |
| ⏳ NO_REPLY        | No response received                      |

Includes prompt-injection protection when processing external email content.

---

### 🌐 Multiple Interfaces

Choose the interface that best fits your workflow:

* Interactive CLI
* FastAPI REST API
* Browser-based frontend dashboard

---

## 🏗️ Architecture

```text
               ┌───────────────────────┐
               │    1. Lead Intake     │
               └───────────┬───────────┘
                           │
                           ▼
               ┌───────────────────────┐
               │ 2. Enrich Lead Node   │
               └───────────┬───────────┘
                           │
                           ▼
               ┌───────────────────────┐
               │3. Generate Draft Node │◄──────────────┐
               └───────────┬───────────┘               │
                           │                           │
                           ▼                           │
══════════════════════════════════════════════════════════════
         🛑 HUMAN-IN-THE-LOOP APPROVAL (HITL)
══════════════════════════════════════════════════════════════
             │                     │
      Approve│                     │Reject
             ▼                     ▼
     ┌──────────────────┐    ┌─────────────┐
     │ 4. Send Email    │    │ Terminate   │
     └─────────┬────────┘    └─────────────┘
               │
               ▼
     ┌──────────────────┐
     │5. Check Replies  │
     └─────────┬────────┘
               │
               ▼
       Intent Classification
```

---

## 🏛️ Technology Stack

| Layer           | Technologies          |
| --------------- | --------------------- |
| Workflow Engine | LangGraph             |
| LLM Framework   | LangChain             |
| Backend         | FastAPI               |
| Data Validation | Pydantic              |
| Email           | Gmail API             |
| AI Models       | OpenAI / Ollama       |
| Frontend        | HTML, CSS, JavaScript |
| Configuration   | python-dotenv         |
| Logging         | Python Logging        |

---

## 📂 Project Structure

```text
Cold_Email_Assistant/
│
├── config.py              # Configuration, logging & environment validation
├── state.py               # Shared workflow state and Pydantic models
├── services.py            # Gmail, LLM and enrichment services
├── nodes.py               # Individual LangGraph nodes
├── workflow.py            # Graph construction and checkpoint logic
├── main.py                # CLI application
├── server.py              # FastAPI REST server
│
├── frontend/
│   └── index.html         # Browser dashboard
│
├── .env.example
├── requirements.txt
└── README.md
```

---

# 🚀 Getting Started

## Prerequisites

* Python 3.10+
* Git
* Gmail API credentials
* (Optional) OpenAI API Key
* (Optional) Ollama for local inference

---

## Installation

Clone the repository:

```bash
git clone https://github.com/your-username/Cold_Email_Assistant.git

cd Cold_Email_Assistant
```

Create a virtual environment:

### Windows

```bash
python -m venv venv

venv\Scripts\activate
```

### macOS / Linux

```bash
python3 -m venv venv

source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt

pip install email-validator
```

---

# ⚙️ Environment Configuration

Create a local environment file:

```bash
cp .env.example .env
```

Example configuration:

```env
LOG_LEVEL=INFO

GMAIL_DELIVERY_MODE=draft

DRY_RUN=true

OPENAI_API_KEY=your-openai-key

APOLLO_API_KEY=your-apollo-key

CLAY_API_KEY=your-clay-key
```

---

# ▶️ Running the Application

## Option 1 — Interactive CLI

```bash
python main.py
```

---

## Option 2 — FastAPI Server

```bash
uvicorn server:app --reload --port 8000
```

After the server starts:

```
frontend/
└── index.html
```

Open `frontend/index.html` in your browser.

---

# 🏠 Running Completely Offline (Ollama)

Install Ollama:

https://ollama.com

Download a model:

```bash
ollama run llama3.2
```

Install the Ollama integration:

```bash
pip install langchain-ollama
```

Configure your application to use:

```python
from langchain_ollama import ChatOllama

llm = ChatOllama(model="llama3.2")
```

No OpenAI API key is required.

---

# 🔒 Security

The project follows secure-by-default practices.

### Environment Variables

* Secrets are never hardcoded.
* API keys are loaded from `.env`.
* `.env` should never be committed.

---

### Safe Email Delivery

Default configuration:

```env
GMAIL_DELIVERY_MODE=draft

DRY_RUN=true
```

This prevents accidental email delivery during development.

---

### Prompt Injection Protection

Incoming email replies are treated as **untrusted input** before LLM processing.

Security measures include:

* Input delimitation
* Prompt isolation
* Intent-only classification

---

# 📈 Workflow Summary

```text
Lead
   │
   ▼
Lead Enrichment
   │
   ▼
AI Email Generation
   │
   ▼
Human Approval
   │
   ├── Reject
   │
   └── Approve
          │
          ▼
 Gmail Draft / Send
          │
          ▼
 Reply Monitoring
          │
          ▼
Intent Classification
```

---

# 🎯 Use Cases

* AI Sales Outreach
* B2B Lead Generation
* SDR Automation
* Founder Outreach
* Recruitment Campaigns
* Customer Success Follow-ups
* Enterprise Email Automation

---

# 🛣️ Roadmap

* [ ] Multi-step email sequences
* [ ] CRM integrations (HubSpot, Salesforce)
* [ ] Calendar scheduling
* [ ] Email A/B testing
* [ ] Analytics dashboard
* [ ] PostgreSQL persistence
* [ ] Multi-user authentication
* [ ] Docker deployment
* [ ] Kubernetes support
* [ ] Role-Based Access Control (RBAC)

---

# 🤝 Contributing

Contributions are welcome.

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push your branch
5. Open a Pull Request

Please ensure all new features include appropriate tests and documentation.

---

## 🔑 API Keys & Environment Variables

This repository includes a **`.env.example`** file containing all the required environment variables. **No real API keys, OAuth credentials, or secrets are included** for security reasons.

To run the complete pipeline, you must create your own `.env` file and provide valid credentials for the services you intend to use.

### Required Configuration

Depending on your setup, you may need to provide:

* `OPENAI_API_KEY` *(or configure Ollama for local inference)*
* `GMAIL_CLIENT_ID`
* `GMAIL_CLIENT_SECRET`
* `GMAIL_REFRESH_TOKEN`
* `APOLLO_API_KEY` *(optional for lead enrichment)*
* `CLAY_API_KEY` *(optional for lead enrichment)*

Create your local environment file by copying the example:

```bash
cp .env.example .env
```

Then replace the placeholder values with your own credentials.

> **Note:** The application **will not function with the placeholder values** included in `.env.example`. These are intentionally left blank (or populated with dummy values) to protect sensitive information and follow security best practices.

### Why are the API keys not included?

For security and privacy reasons:

* ✅ No production API keys are committed to GitHub.
* ✅ No Gmail OAuth credentials are included.
* ✅ No access tokens or refresh tokens are stored in the repository.
* ✅ Every user must configure their own credentials before running the application.

This follows industry-standard practices for securely managing secrets in open-source projects.
, stateful AI workflow for modern outbound sales automation.
