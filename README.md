# Signal Hire (WIP)

This is an exploration project focused on **LangChain**, **LangGraph**, and **agentic principles**. It is a work in progress and serves as a sandbox for experimenting with multi-agent workflows and persistent state management in an AI-powered recruitment context.

## 🧪 Exploration Goals

- **Agentic Workflows:** Using LangGraph to orchestrate multiple specialized agents.
- **Persistent Memory:** Leveraging PostgreSQL checkpointers to maintain state across agentic interactions.
- **Contextual Reasoning:** Exploring how agents can "remember" candidate details and achievements to provide better suggestions for specific Job Descriptions (JDs).
- **Human-in-the-loop:** (Experimental) Patterns for real-time interaction via WebSockets.

## 🛠 Tech Stack

- **Backend:** FastAPI (Python 3.11+)
- **AI Orchestration:** LangGraph & LangChain
- **Database:** PostgreSQL with pgvector
- **Frontend:** Angular 19+ (Angular Material)
- **Infrastructure:** Docker Compose (Postgres, MinIO, Flyway)

## 🚀 Setup & Execution

### Prerequisites
- Python 3.11+
- Node.js & npm
- Docker and Docker Compose
- **OpenAI API Key** (Set in `.env`)

### 1. Infrastructure
```bash
docker-compose up -d
```

### 2. Frontend Build
Since the FastAPI server serves the UI, you need to build the Angular application first:
```bash
cd ui
npm install
npm run build
cd ..
```

### 3. Backend & UI Server
```bash
cd server
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.main:app --reload
```
The application will be available at `http://localhost:8000`.

> **Note for Frontend Development:** If you are actively developing the UI, you can still run `npm start` in the `ui` directory to use the Angular development server at `http://localhost:4200` with hot-reloading.

## 📂 Structure
- `server/src/agents/`: Core LangGraph agent definitions.
- `server/src/services/`: Document parsing, embeddings, and storage logic.
- `ui/src/app/`: Angular frontend implementation.

---
*Note: This is not a production-ready application. It is an experimental codebase for agentic AI research.*
