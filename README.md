# Signal Hire (WIP)

This is an exploration project focused on **LangChain**, **LangGraph**, and **agentic principles**. It is a work in progress and serves as a sandbox for experimenting with multi-agent workflows and persistent state management in an AI-powered recruitment context.

## 🧪 Exploration Goals

- **Agentic Workflows:** Using LangGraph to orchestrate multiple specialized agents.
- **Persistent Memory:** Leveraging PostgreSQL checkpointers to maintain state across agentic interactions.
- **Contextual Reasoning:** Exploring how agents can "remember" candidate details and achievements to provide better suggestions for specific Job Descriptions (JDs).
- **Human-in-the-loop:** Experimental patterns for real-time interaction.

## 🛠 Tech Stack

- **Backend:** FastAPI (Python 3.11+)
- **AI Orchestration:** LangGraph & LangChain
- **Database:** PostgreSQL with pgvector
- **Infrastructure:** Docker Compose (Postgres, MinIO, Flyway)

## 🚀 Setup & Execution

### Prerequisites
- Python 3.11+
- Docker and Docker Compose
- **OpenAI API Key** (Set in `.env`)

### 1. Infrastructure
```bash
docker-compose up -d
```

### 2. Backend Server
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.main:app --reload
```
The API will be available at `http://localhost:8000`.

### 3. Environment Variables
Create a `.env` file in the root directory and add the following:
- `OPENAI_API_KEY`: Your OpenAI API key.
- `DB_NAME`: Database name.
- `DB_USER`: Database username.
- `DB_PASSWORD`: Database password.
- `DB_HOST`: Database host.
- `DB_PORT`: Database port.
- `AUTH0_DOMAIN`: Your Auth0 domain (e.g., `dev-xxx.us.auth0.com`).
- `AUTH0_AUDIENCE`: Your Auth0 API Identifier.

## 📂 Structure
- `src/agents/`: Core LangGraph agent definitions.
- `src/services/`: Document parsing, embeddings, and storage logic.

---
*Note: This is not a production-ready application. It is an experimental codebase for agentic AI research.*
