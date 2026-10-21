# AI Invoice Auditor

A containerized, multilingual invoice validation system that monitors an incoming directory, extracts and translates invoice data, validates it against ERP records, stores a durable audit trail in PostgreSQL, indexes processed content in Qdrant for RAG, and exposes a Streamlit human-in-the-loop dashboard.

## Features

- **Automated monitoring** of a mounted invoice drop folder
- **Checksum-based duplicate detection** independent of filenames
- **PDF, DOCX, and PNG extraction** with OCR fallback
- **Multilingual translation** with AWS Bedrock and Redis caching
- **Rule-driven invoice validation** using configurable YAML rules
- **Mock ERP boundary** enforced through HTTP APIs only
- **Durable audit schema** in PostgreSQL with separate invoice lines, discrepancies, and human feedback
- **RAG querying** over persisted invoice text and reports using LangGraph + Qdrant + LiteLLM
- **Human-in-the-loop dashboard** for review, correction, revalidation, and querying
- **Single-command deployment** with Docker Compose, health checks, named volumes, and service-name networking

## Architecture

```mermaid
flowchart LR
    Browser[Browser] --> UI[Streamlit UI\n:8501]
    UI -->|HTTP| Agent[Agent API\nFastAPI + LangGraph\n:8000]
    UI -->|read-only SQL| Postgres[(PostgreSQL)]

    Agent -->|HTTP| ERP[Mock ERP API\n:8001]
    Agent -->|read/write| Postgres
    Agent -->|cache| Redis[(Redis)]
    Agent -->|vector index| Qdrant[(Qdrant)]
    Agent -->|read/write| Incoming[(Mounted runtime volume)]

    Postgres -->|erp schema| ERP
    Incoming -->|original invoices + reports| Agent
```

## Repository layout

- [agent/](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/agent) - Agent service source, workflow, RAG pipeline, validation, API
- [mock_erp/](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/mock_erp) - Mock ERP FastAPI service
- [streamlit-ui/](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/streamlit-ui) - Streamlit dashboard
- [database/init/](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/database/init) - Automatic PostgreSQL initialization scripts
- [config/](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/config) - Rules and RAG prompt templates
- [compose.yaml](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/compose.yaml) - Full six-service stack
- [runtime/incoming/](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/runtime/incoming) - Mounted invoice drop folder used by the running stack
- [runtime/outputs/](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/runtime/outputs) - Mounted report output folder used by the running stack
- [data/incoming/](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/data/incoming) - Sample invoices for manual testing

## Required runtime configuration

Create a local `.env` file at the repository root. Do **not** commit it.

### Required variables

```env
# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=invoice_auditor
DB_USER=postgres
DB_PASSWORD=your-password

# Optional convenience override for local non-containerized runs
# DATABASE_URL=postgresql+psycopg://postgres:encoded-password@localhost:5432/invoice_auditor

# AWS Bedrock
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
# AWS_SESSION_TOKEN=...   # required only for temporary credentials

# Models
BEDROCK_LANGUAGE_MODEL_ID=amazon.nova-lite-v1:0
BEDROCK_TRANSLATION_MODEL_ID=amazon.nova-lite-v1:0
BEDROCK_RAG_MODEL_ID=amazon.nova-lite-v1:0
BEDROCK_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v1

# Cache / vector store defaults
QDRANT_COLLECTION=invoice_knowledge
```

### Important notes

- In Docker Compose, the application containers **do not use `localhost`** for dependencies. The checked-in [compose.yaml](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/compose.yaml) overrides internal addresses to use the required Compose service names (`postgres`, `redis`, `qdrant`, `mock-erp`, `agent`).
- The app now supports either:
  - a fully specified `DATABASE_URL`, or
  - individual `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` variables.
- Bedrock credentials must be supplied at runtime through `.env`. They are **not** baked into images.

## Startup

From a clean checkout:

```bash
docker compose up --build -d
```

Then verify:

```bash
docker compose ps
```

Expected services:

- `postgres`
- `qdrant`
- `redis`
- `mock-erp`
- `agent`
- `streamlit-ui`

## Access points

- Agent API: `http://localhost:8000`
- Mock ERP API: `http://localhost:8001`
- Streamlit dashboard: `http://localhost:8501`
- Qdrant API: `http://localhost:6333`

## How to process an invoice

The running stack monitors [runtime/incoming/](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/runtime/incoming).

1. Copy one of the sample invoices from [data/incoming/](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/data/incoming) into [runtime/incoming/](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/runtime/incoming).
2. Wait for the monitor poll cycle **or** trigger an immediate run:

```bash
curl -X POST http://localhost:8000/api/v1/invoices/process \
  -H 'Content-Type: application/json' \
  -d '{}'
```

3. Review results in the Streamlit dashboard at `http://localhost:8501`.
4. Generated reports are written under [runtime/outputs/](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/runtime/outputs).

## Human-in-the-loop dashboard

The Streamlit dashboard provides two auditor-facing workflows:

### 1. Invoice Dashboard

- View processed invoices and summary metrics
- Inspect report JSON
- Review line items and discrepancies
- Read raw extracted text and translated English text
- Submit corrections without overwriting original extracted values
- Trigger revalidation after corrections
- Review persistent feedback history

### 2. Ask a Question

- Ask structured questions (counts, filters, simple lookups)
- Ask open-ended questions over processed invoice/report text
- Optionally scope a question to a single invoice
- See query type, answer source, RAG score, and retry count

## Service boundaries

This implementation enforces the intended ownership rules:

- The **Agent** is the only service that writes audit data.
- **Mock ERP** reads the `erp` schema and exposes ERP records only through HTTP.
- **Streamlit UI** reads audit data directly from PostgreSQL but sends all changes through the Agent API.
- The **Agent** uses the Mock ERP HTTP API instead of directly querying `erp.*` tables.
- **Qdrant** stores a derived index built only from data already persisted in PostgreSQL.

## Database initialization

On first startup, PostgreSQL automatically executes the scripts in [database/init/](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/database/init):

1. Create `langgraph`, `erp`, and `audit` schemas
2. Create audit tables
3. Create ERP tables
4. Seed ERP master data
5. Apply follow-up schema adjustments

No manual database setup step is required.

## Prompt templates and persona/config files

Prompt and persona/config artifacts are stored in:

- [config/rag_prompts.yaml](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/config/rag_prompts.yaml)
- [config/rules.yaml](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/config/rules.yaml)

## Docker artifacts

### Dockerfiles

- [agent/Dockerfile](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/agent/Dockerfile)
- [mock_erp/Dockerfile](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/mock_erp/Dockerfile)
- [streamlit-ui/Dockerfile](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/streamlit-ui/Dockerfile)

### Docker ignore files

- [agent/.dockerignore](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/agent/.dockerignore)
- [mock_erp/.dockerignore](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/mock_erp/.dockerignore)
- [streamlit-ui/.dockerignore](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/streamlit-ui/.dockerignore)

## Verification checklist

### Check 1 - Single-command startup

```bash
docker compose down -v
docker compose up --build -d
docker compose ps
```

Verify that all six services are healthy.

### Check 2 - End-to-end processing

1. Copy a test invoice into [runtime/incoming/](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/runtime/incoming).
2. Confirm processing via Agent logs or `POST /api/v1/invoices/process`.
3. Validate that PostgreSQL stores:
   - invoice audit row
   - line items
   - discrepancies (if any)
   - recommendation and validation status
4. Confirm that report files appear in [runtime/outputs/](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/runtime/outputs).

### Check 3 - Persistence across restart

After processing and indexing at least one invoice:

```bash
docker compose down
docker compose up -d
```

Verify that:

- audit history remains in PostgreSQL
- the Qdrant index still exists
- the invoice remains queryable without reprocessing

### Check 4 - Deliberate data loss

```bash
docker compose down -v
docker compose up -d
```

Verify that PostgreSQL and Qdrant start empty again because the named volumes were deleted.

> **Important:** the monitored input folder is a drop folder for *new arrivals*. If an invoice file is still sitting in [runtime/incoming/](/home/labuser/aug26-sp1-l1-fa3-proj-group-35/runtime/incoming) when the fresh stack starts, the Agent will correctly detect it as a newly arrived invoice and process it again. For a clean deliberate-data-loss demonstration, keep the drop folder empty before recreating the stack and then add invoices afterward.

### Check 5 - No secrets in images

Inspect image history:

```bash
docker history ai-invoice-auditor-agent:1.0 --no-trunc
docker history ai-invoice-auditor-mock-erp:1.0 --no-trunc
docker history ai-invoice-auditor-streamlit-ui:1.0 --no-trunc
```

The `.env` file is excluded from the build context and credentials are only supplied at runtime.

### Check 6 - Service-name resolution

```bash
docker compose exec agent getent hosts postgres qdrant redis mock-erp
```

The Agent must resolve the dependency services by Compose service name, not by hardcoded IP address or `localhost`.

## Useful commands

```bash
docker compose logs -f agent
docker compose logs -f mock-erp
docker compose logs -f streamlit-ui
docker compose exec agent env
docker compose exec agent getent hosts postgres qdrant redis mock-erp
docker compose exec postgres psql -U "$DB_USER" -d "$DB_NAME"
docker history ai-invoice-auditor-agent:1.0 --no-trunc
```

## Notes on model availability

The repository is configured to use AWS Bedrock models. In this environment, the implementation was verified with:

- `amazon.nova-lite-v1:0` for reasoning/generation
- `amazon.titan-embed-text-v1` for embeddings

If your Bedrock account also has access to Cohere Command R+ or other approved models, you can switch model IDs through environment variables without changing code.
