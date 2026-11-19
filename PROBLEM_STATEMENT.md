# AI Invoice Auditor --- Complete Problem Statement

> **Document type:** Project requirements and implementation
> specification
> **Project:** AI Invoice Auditor
> **Purpose:** Keep this document in the repository as the source of
> truth for the capstone requirements.
> **Source:** Transcribed and formatted from the 20-page
> problem-statement photographs supplied in this conversation.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Original Project Requirements](#2-original-project-requirements)
3. [Functional Requirements --- Containerized
   Extension](#3-functional-requirements--containerized-extension)
4. [Non-Functional Requirements](#4-non-functional-requirements)
5. [Solution Architecture](#5-solution-architecture)
6. [Data Architecture](#6-data-architecture)
7. [Implementation Details](#7-implementation-details)
8. [Containerization Requirements](#8-containerization-requirements)
9. [Verification Checklist](#9-verification-checklist)
10. [Deliverables](#10-deliverables)
11. [Evaluation Criteria](#11-evaluation-criteria)

---

# 1. Project Overview

## Project

**Name:** AI Invoice Auditor

## Project Description

An end-to-end Agentic AI-powered system for automated multilingual
invoice processing and validation. The solution uses AI agents to
extract, translate, validate, and audit invoices received via email in
various formats and languages. It integrates Retrieval-Augmented
Generation (RAG) and human-in-the-loop feedback for enhanced accuracy
and reliability.

## Business Context

A logistics client receives invoices from global vendors to raise
invoice discrepancies in various languages (English, Spanish, German,
etc.) and formats (PDF, Word, scanned images) via email as attachments.
Manual processing is time-consuming, error-prone, and a skill-intensive
process as it requires language expertise.

# 2. Original Project Requirements

Design and implement an end-to-end Agentic AI-powered solution that:

1. Monitors an email inbox for incoming invoices. **For this step, only
   the design/application is expected, not the actual implementation.**
2. Extracts invoice data (text, tables, key fields) from attachments
   that can be in any language and format. The solution should
   therefore be format- and language-agnostic.
3. Translates extracted data to English.
4. Validates invoice data against records in an enterprise system
   (e.g., ERP, database, or mock data). The call to the enterprise
   system can be mocked for the capstone implementation. The mock API
   call should return data from the ERP system to be validated against
   the data received at line-item level in the customer invoice.
5. Generates a detailed validation report highlighting:
   - Discrepancies where invoice data does not match ERP data.
   - Missing fields from the invoice. Invoice validation should be
     performed against dynamically configured rules.
   - Translation confidence.
6. Provides question-answering capabilities, implemented using
   vector-based RAG, on invoices to the Support Agent (Human Agent).

## 2.1 Agentic RAG Requirements

RAG should be implemented using Agentic AI. The RAG solution should
comprise the following agent roles:

- **Indexing Agent:** Parses and indexes invoice documents in a vector
  database.
- **Retrieval Agent:** Accepts a user query, generates a query
  embedding, and performs similarity search.
- **Augmentation Agent:** Performs reranking of chunks based on
  similarity scores.
- **Generation Agent:** Uses an LLM to generate contextual responses.
- **Reflection Agent:** Evaluates the response using RAG Triad
  parameters, including Answer Relevance, Context Relevance, and
  Groundedness.

## 2.2 RAG Tools

The following tools need to be leveraged as part of the RAG
implementation:

- **Vector-Indexer Tool:** Converts documents into embeddings and
  stores them in a vector database for efficient retrieval.
- **Semantic-Retriever Tool:** Performs semantic search using vector
  similarity to find contextually relevant data.
- **Chunk-Ranker Tool:** Re-ranks retrieved chunks based on relevance
  scores to improve context quality.
- **Response-Synthesizer Tool:** Generates natural-language answers
  using retrieved context and the user query.
- **RAG Evaluator Tool:** Assesses generated responses using RAG
  metrics such as context relevance and groundedness.

# 2.3 Agentic Workflow and Agent Roles

Implement an agentic workflow using the open-source LangGraph framework,
with RAG, prompt engineering, and human-in-the-loop feedback.

The overall Invoice Auditor solution should be implemented using Agentic
AI and should include the following agent roles:

- **Invoice-Monitor Agent:** Continuously monitors the mailbox for
  emails with invoice attachments. This agent can read documents from
  the file system rather than from a live mailbox.
- **Extractor Agent:** Extracts data from various document formats.
- **Translation Agent:** Translates extracted invoice data from
  different languages into English.
- **Invoice Data Validation Agent:** Validates missing information
  based on defined rules.
- **Business Validation Agent:** Validates extracted invoice data with
  enterprise-system data to identify discrepancies.
- **Reporting Agent:** Generates detailed reports highlighting
  discrepancies, missing fields, translation confidence, and the final
  recommendation.

The above-mentioned agents should have appropriate tools to accomplish
their assigned tasks:

- **Invoice-Watcher Tool:** Monitors a designated mailbox or file
  system to detect and retrieve emails containing invoice attachments.
  The agent can read documents from the file system rather than from a
  live mailbox.
- **Data Harvester Tool:** Extracts data from a wide range of document
  formats, enabling downstream processing.
- **Lang-Bridge Tool:** Converts extracted invoice content from
  various languages into English for standardized interpretation.
- **DataCompleteness Checker Tool:** Validates invoice data for
  completeness and accuracy based on predefined business rules.
- **Business Validation Tool:** Cross-verifies extracted invoice data
  against enterprise systems to identify mismatches or
  inconsistencies.
- **Insight Reporter Tool:** Generates comprehensive reports
  highlighting data gaps, validation results, translation confidence,
  and final recommendations.

## 2.4 Multi-Framework Agent Communication

Out of the agents defined above, some should be developed using
**LangGraph**, while others should be implemented using **Google ADK**.

The solution should enable seamless communication between agents
implemented using different frameworks by adhering to the
**Agent-to-Agent (A2A) Protocol**, ensuring standardized and secure
interactions across components.

## 2.5 MCP, Responsible AI, and Observability

- The solution should utilize the **Model Context Protocol (MCP)** to
  dynamically discover, access, and invoke the appropriate tools
  required for task execution.
- Implement **Responsible AI (RAI) guardrails** across agents and
  tools wherever applicable, ensuring ethical, secure, and compliant
  use of AI components throughout the solution.
- Integrate observability tools such as **LangFuse** to enable
  real-time tracing, monitoring, and debugging of agentic AI
  workflows, ensuring transparency and operational reliability.
- The solution should leverage prompt templates while defining prompts
  for indexing, retrieval, augmentation, generation, and reflection.
- The system should include human-in-the-loop feedback and audit
  trails for reliability and transparency.

## 2.6 Solution Architecture --- Original Description

The Agentic AI Invoice Auditor is built on a modular agentic
architecture using the open-source LangGraph Agentic framework. It
orchestrates specialized agents for tasks such as monitoring,
extraction, translation, validation, and reporting through a centralized
LLM Gateway (LiteLLM). A RAG-based question-answering system enables
contextual queries with agents for indexing, retrieval, augmentation,
generation, and reflection. The system includes human-in-the-loop
feedback and audit trails for reliability and transparency.

## 2.7 Original Technology Stack

### Backend

- Python and required libraries
- LangGraph Agentic framework
- Google ADK framework
- Vector database (FAISS, Qdrant, Weaviate)
- OCR tools (e.g., Tesseract)

### Models (Open Source)

- Text-generation models
- Embedding model
- Multi-modal model

### Communication Protocols

- **Model Context Protocol (MCP):** Facilitates interaction between an
  agent and the specific tools it needs to use.
- **Agent-to-Agent Protocol (A2A):** Defines standards and mechanisms
  for seamless discovery, invocation, and communication between
  agents, enabling coordinated task execution and interoperability
  within an agentic ecosystem.

### Other Technology

- **LLM Gateway:** LiteLLM
- **Frontend:** Streamlit / React for the UI
- **Deployment:** NuvePro Lab
- **Observability Tool:** LangFuse

## 2.8 Original Non-Functional Requirements

- **Performance:** Efficient processing of large invoice batches.
- **Scalability:** Modular agent design allows horizontal scaling and
  document handling.
- **Security:** Secure access.
- **Reliability:** Robust error handling and fallback mechanisms.
- **Usability:** Intuitive UI for support agents.
- **Maintainability:** Modular codebase with documentation.

## 2.9 Input Dataset

- Masked invoice PDF.

## 2.10 Original Final Deliverables

- Solution design diagram.
- Source code (Python, modularized).
- Functional application (demo UI + backend agents).
- Sample data (multilingual invoices, mock enterprise records).
- Validation reports (PDF/HTML/CSV).
- Documentation (setup, usage, agent design, prompt templates).

---

# 3. Functional Requirements --- Containerized Extension

This extension adds production-shaped deployment, persistence, service
boundaries, verification, and evaluation requirements to the existing AI
Invoice Auditor capstone without replacing its original agentic AI, RAG,
MCP, A2A, RAI, LangFuse, and multilingual invoice-processing
requirements.

## 3.1 Extension Scope

- Run the solution as a reproducible Docker Compose multi-service
  stack that starts from a clean machine with one command.
- Use PostgreSQL as the durable system of record, Qdrant as a
  rebuildable vector index, and Redis only for disposable caches.
- Enforce ERP access through the `mock-erp` HTTP service rather than
  direct reads from ERP database tables.
- Preserve audit history, human corrections, agent checkpoints, and
  RAG data according to the defined durability model.
- Validate the implementation through startup, end-to-end processing,
  persistence, deliberate data-loss, image-safety, and
  service-discovery checks.

## 3.2 Invoice Monitoring

- Watch the incoming directory, which is mounted into the agent
  container as a volume.
- Detect new files and route them by type to the correct extraction
  path.
- Compute a checksum for each file and skip any invoice already
  present in the audit trail.
- Record every detected file, including files that fail to process.

**Why a checksum rather than a filename?**

Vendors rename files freely, and the same invoice can arrive twice under
different names. A content checksum is the reliable way to determine
whether an invoice has already been audited.

## 3.3 Invoice Extraction

- Handle PDF, DOCX, and PNG (scanned) input.
- For PDFs, attempt direct text extraction first; fall back to OCR
  when no embedded text layer exists.
- Use Tesseract with the language packs required by the dataset for
  scanned documents.
- Extract invoice number, date, vendor name, currency, and total.
- Extract line items: item code, description, quantity, unit price,
  and line total.
- Store the complete raw extracted text, not only the parsed fields.

**Why store the raw text?**

OCR is expensive and cannot be cheaply repeated. Keeping the full
extracted text means the vector index can be rebuilt without re-reading
a single PDF, and a disputed audit can be defended by showing exactly
what the system read.

## 3.4 Translation

- Detect the source language automatically.
- Translate non-English content to English using an AWS Bedrock model.
- Record a translation confidence score alongside the translated text.
- Cache translation results so repeated content is not re-translated.

## 3.5 Validation

### Invoice Data Validation Agent

- Check field completeness against configured rules.
- Verify that totals sum to the invoice total and that tax
  calculations are correct.
- Highlight missing or internally inconsistent fields.

### Business Validation Agent

- Call the mock ERP service over HTTP by service name. The ERP service
  reads data from PostgreSQL.
- Compare quantity, unit price, and currency against the matching
  purchase order.
- Apply the tolerance thresholds defined in `rules.yaml`.
- Record one discrepancy row per mismatched field, with both values
  and the deviation.

The source photographs show the following endpoint examples, although
two paths/ports are not fully legible in the photograph:

```text
GET http://mock-erp:8092/po/{po_number}
GET http://mock-erp:.../vendor/{vendor_id}
GET http://mock-erp:8000/sku/{sku_code}
```

The containerized architecture later specifies `mock-erp:8000` as the
internal service address and host port `8001` as its published port. Use
the service address and port defined in the final Compose architecture.

**Service boundary --- this is assessed directly.**

Both services share the same database instance, so the agent container
can technically reach PostgreSQL. It must not query ERP tables directly.
All ERP data is obtained through the `mock-erp` HTTP API. Bypassing the
API collapses the service boundary and makes the ERP service
meaningless.

## 3.6 Reporting

- Generate a JSON report for machine consumption and an HTML report
  for human reading.
- Include a discrepancy summary, missing-field list, and translation
  confidence.
- Produce recommendations: approval, manual review, or reject.
- Write the outcome to PostgreSQL. Report files may also be written,
  but the database is the system of record.

## 3.7 RAG-Based Querying

Implement a LangGraph-based RAG pipeline over the processed invoices and
their reports:

- **Indexing Agent:** Chunks invoice text and report text, embeds
  them, and writes vectors to Qdrant.
- **Retrieval Agent:** Retrieves relevant chunks, with the ability to
  filter to a specific invoice.
- **Augmentation Agent:** Reranks and assembles context.
- **Generation Agent:** Retrieves the chunks needed to generate a
  response for the user query and generates an answer through LiteLLM.
- **Reflection Agent:** Evaluates the answer using the RAG Triad:
  relevance, groundedness, and context relevance.

The photographed requirement states that if the overall average score is
greater than **0.7**, the generated answer should be displayed to the
user; otherwise, the answer should not be displayed. It also specifies
retrieving the top **3** chunks for response generation.

## 3.8 Human-in-the-Loop Dashboard

A Streamlit interface, running in its own container, that allows an
auditor to:

- Review invoice reports and their discrepancies.
- Correct extracted values.
- Ask natural-language questions about processed invoices.

Record feedback permanently rather than overwriting the original
extraction.

---

# 4. Non-Functional Requirements

---

  Requirement                         Description

---

  Performance                         Efficient processing of invoice
                                      batches; expensive operations are
                                      performed once and reused.

  Scalability                         Modular agent design supports
                                      scaling and document handling.

  Durability                          Audit trail and RAG index survive
                                      container destruction and
                                      recreation when named volumes are
                                      retained.

  Security                            No credential appears in
                                      application source, in any
                                      Dockerfile, or in any built image
                                      layer.

  Reliability                         A service that cannot reach its
                                      dependencies fails clearly and
                                      immediately rather than starting in
                                      a broken state.

  Usability                           The dashboard is usable by a
                                      non-technical auditor.

Maintainability                     Modular agent design, documented
                                      configuration, and reproducible
                                      build.
--------------------------------------------

---

# 5. Solution Architecture

The system is deployed as six containers on a single user-defined bridge
network created by Docker Compose. Services address each other by
service name; no IP address is ever hard-coded.

## 5.1 Deployed Services

---

  Service          Image / Build                     Ports Responsibility
                                          (host:container)

---

  `agent`          Build from                  `8000:8000` Runs the LangGraph
                   Dockerfile                              workflow: monitor,
                                                           extractor,
                                                           translation,
                                                           validation,
                                                           reporting, and RAG
                                                           agents. Exposes a
                                                           health endpoint.

  `mock-erp`       Build from                  `8001:8000` FastAPI service
                   Dockerfile                              serving vendor,
                                                           purchase-order, and
                                                           SKU lookups from
                                                           PostgreSQL.

  `streamlit-ui`   Build from                  `8501:8501` Human-in-the-loop
                   Dockerfile                              dashboard. Reads
                                                           reports from
                                                           PostgreSQL and
                                                           calls the agent for
                                                           re-validation.

  `postgres`       `postgres:16`               `5432:5432` Durable system of
                                                           record. Holds agent
                                                           checkpoints, ERP
                                                           master data, and
                                                           the audit trail.

  `qdrant`         `qdrant/qdrant`             `6333:6333` Vector database
                                                           holding the RAG
                                                           index. A derived
                                                           store, rebuildable
                                                           from PostgreSQL.

`redis`          `redis:7`                   `6379:6379` Ephemeral cache for
                                                           translation results
                                                           and LLM responses.
-----------------------------------------------------------------------------

## 5.2 Processing Flow

A single invoice moves through the system as follows:

1. The file arrives in the mounted incoming directory. The file itself
   never enters any database.
2. The monitor agent detects it, checksums it, and routes it by type.
3. The extractor produces raw text --- directly for digital PDFs, via
   OCR for scans --- and writes that text to PostgreSQL.
4. If the same query is asked again instead of hitting the LLM, the
   cached result for the query is taken from Redis.
5. Structured fields are parsed into typed columns; line items become
   their own rows.
6. The validation agent calls `mock-erp` over HTTP and writes
   discrepancies to PostgreSQL.
7. The reporting agent writes the recommendation to PostgreSQL and
   generates report files.
8. The indexing agent chunks the stored text, embeds it, and writes
   vectors to Qdrant.

Queries take a much shorter path. Structured questions are answered
directly from PostgreSQL with SQL. Only open-ended questions go through
Qdrant retrieval and generation. Nothing is re-extracted at query time.

**Note on LiteLLM:** LiteLLM runs as an in-process library in this build
rather than a separate container. In production it would run as its own
gateway service so that rate limiting, cost tracking, and credential
handling are centralised. Be prepared to explain this trade-off.

## 5.3 Architecture Diagram --- Interpretation

The architecture diagram is the target being built. It fixes service
names, ports, and which store each service is allowed to touch.

- The dashed outer boundary is the network Compose creates. Everything
  inside it resolves each other by service name. The auditor's browser
  and AWS Bedrock are outside the stack and are reached differently.
- Solid arrows are requests expecting responses. The agent calls
  `mock-erp` over HTTP and waits for the purchase order back.
- Dashed arrows are data reads/writes or calls to an external API.
  These connections need a hostname and credentials supplied at
  runtime.
- Colour marks durability rather than importance. The stores drawn
  with named volumes survive a teardown; Redis has no volume and is
  designed not to need one.

### Three assessed architecture decisions

1. **The agent is the only service that writes application data.**
   `mock-erp` reads the `erp` schema and serves it over HTTP;
   `streamlit-ui` reads the `audit` schema and calls the agent when
   something must change. Keeping writes in one place is what makes the
   audit trail trustworthy.
2. **`mock-erp` is the only route to ERP data.** Both the agent and UI
   can technically reach PostgreSQL directly because all three schemas
   live in one instance. Querying the `erp` schema from outside
   `mock-erp` collapses the service boundary and makes the ERP service
   meaningless.
3. **Qdrant points back to PostgreSQL, not the other way round.** The
   vector index is derived from text already stored in PostgreSQL, so
   losing the Qdrant volume is a rebuild rather than data loss.
   Verification Checks 3 and 4 test exactly this distinction.

The port pairs in the diagram are important. The value on the left of
the arrow is the host port, reachable from your browser; the value on
the right is the container port, which other containers must use.
`mock-erp` is published on host port `8001` but is addressed internally
as `mock-erp:8000`. Confusing the two is a common cause of connection
failure.

---

# 6. Data Architecture

Four stores are involved. Deciding what belongs in each --- and which
service owns it --- is the central design decision of this project. A
stack that runs but places data incorrectly is not architecturally sound
and will not receive full marks.

## 6.1 Storage Responsibilities and Durability

---

  Store                   Holds                   Survives teardown?

---

  Filesystem (volume)     Original invoice files  Yes, while the volume
                          and generated report    exists.
                          files.

  PostgreSQL              Agent checkpoints, ERP  Yes --- named volume
                          master data, and the    required.
                          complete audit trail.

  Qdrant                  Vector embeddings and   Yes --- named volume
                          their chunk payloads.   required.

Redis                   LLM response caches.    No, and it must not
                                                  need to.
----------------------------------------------------------

## 6.2 Where the Invoice File Itself Goes

The PDF, DOCX, or PNG binary is never stored in PostgreSQL. Binary blobs
in a relational database are an antipattern; production systems place
them in object storage and keep a reference in the database. Here the
file stays on the mounted volume and the database stores its path and
checksum.

Everything read out of the file goes into PostgreSQL in three different
forms:

---

  Form                    Column type             Example

---

  Unstructured text       `TEXT`                  The complete extracted text of
                                                  the invoice as a single value,
                                                  newlines and all. No schema
                                                  describes its contents.

  Structured fields       Typed columns           `invoice_number VARCHAR`,
                                                  `invoice_date DATE`,
                                                  `total_amount NUMERIC(14,2)`.
                                                  These exist because you will
                                                  filter, sort, and sum on them.

Variable extras         `JSONB`                 Format-specific fields that do
                                                  not justify a column of their
                                                  own, such as a vendor's custom
                                                  reference or a country-specific
                                                  tax breakdown.
----------------------------------------------------------------

A fixed schema does not mean every invoice must have every field. A
column that has no value is simply `NULL`. Declaring a schema means
deciding in advance which fields are possible, not requiring that all of
them are present.

## 6.3 PostgreSQL: Three Schemas, One Database

Create three schemas inside a single database rather than three separate
databases. One connection string, clear ownership boundaries, and it
mirrors how a real team separates concerns without provisioning separate
servers.

---

  Schema            Owner             Contents                Who designs it

---

  `langgraph`       agent             Checkpoints,            Created
                                      `checkpoint_blobs`,     automatically by
                                      `checkpoint_writes`,    the LangGraph
                                      thread. Serialized      PostgreSQL
                                      graph state used to     checkpointer.
                                      resume a paused
                                      workflow.

  `erp`             `mock-erp`        Vendors, purchase       Provided in
                                      orders, PO line items,  `erp_schema.sql`.
                                      SKU master.

`audit`           Agent writes;     `invoice_audit`,        You design these
                    `streamlit-ui`    `invoice_line_items`,   tables.
                    reads             discrepancies, human
                                      feedback.
---------------------------------------------------------------------------------------------------------

### Why an audit schema when LangGraph already checkpoints everything?

LangGraph checkpoints are msgpack binary blobs. They exist so that a
paused workflow can resume --- they are working memory, not a business
record. You cannot answer "show me every invoice from vendor V001
rejected last month" against a serialized blob; that needs typed columns
and indexes. The two stores have different purposes and different
lifetimes: checkpoints may be pruned once a workflow completes, the
audit trail never is.

### Suggested audit schema

The following is a starting point, not a specification. You are expected
to adapt it, but the marked capabilities below must be present.

```sql
CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE audit.invoice_audit (
    invoice_id UUID PRIMARY KEY,
    file_path VARCHAR(512),           -- reference, not the file
    file_checksum VARCHAR(64) UNIQUE, -- detects reprocessing
    extraction_method VARCHAR(32),    -- pdfplumber | docx | tesseract
    raw_extracted_text TEXT,          -- full text, pre-translation
    translated_text TEXT,
    source_language VARCHAR(8),
    translation_confidence NUMERIC(4,3),
    invoice_number VARCHAR(64),
    vendor_name VARCHAR(255),
    po_number VARCHAR(64),
    invoice_date DATE,
    currency CHAR(3),
    total_amount NUMERIC(14,2),
    validation_status VARCHAR(32),    -- passed | failed | partial
    recommendation VARCHAR(32),      -- approve | review | reject
    extracted_raw JSONB,              -- variable leftovers
    thread_id VARCHAR(128),           -- links to LangGraph state
    processed_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE audit.invoice_line_items (
    id BIGSERIAL PRIMARY KEY,
    invoice_id UUID REFERENCES audit.invoice_audit(invoice_id),
    line_number INTEGER,
    item_code VARCHAR(64),
    description TEXT,
    quantity NUMERIC(12,3),
    unit_price NUMERIC(14,4),
    line_total NUMERIC(14,2)
);

CREATE TABLE audit.discrepancies (
    id BIGSERIAL PRIMARY KEY,
    invoice_id UUID REFERENCES audit.invoice_audit(invoice_id),
    field_name VARCHAR(64),
    invoice_value TEXT,
    erp_value TEXT,
    deviation_pct NUMERIC(8,4),
    severity VARCHAR(16),
    detected_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE audit.human_feedback (
    id BIGSERIAL PRIMARY KEY,
    invoice_id UUID REFERENCES audit.invoice_audit(invoice_id),
    field_name VARCHAR(64),
    original_value TEXT,
    corrected_value TEXT,
    corrected_by VARCHAR(128),
    corrected_at TIMESTAMPTZ DEFAULT now(),
    revalidated BOOLEAN DEFAULT FALSE
);
```

### Required capabilities, regardless of how you name things

- Line items are separate rows in their own table, not an array or
  JSON blob inside the invoice row.
- A human correction is an `INSERT` into `human_feedback`, never an
  `UPDATE` that overwrites the original extracted value.
- Monetary values use `NUMERIC`, not floating point. Floats lose
  cents.
- Dates use `DATE` or `TIMESTAMPTZ` so that range queries work without
  casting.
- The raw extracted text is retained.

**Coming from a document database:** In a document store you would nest
line items inside the invoice document. PostgreSQL does not nest ---
line items become rows in a second table linked by `invoice_id`, and you
join to bring them back together. This is not a limitation here: invoice
validation is fundamentally the comparison of two relational structures,
invoice lines against purchase-order lines, which is exactly what a join
does.

## 6.4 Qdrant: A Derived Index

Create a single collection. Alongside each vector, store a payload
containing at minimum:

---

  Payload field                       Purpose

---

  `invoice_id`                        Allows retrieval to be filtered to
                                      one invoice. Without it, a question
                                      about a specific invoice searches
                                      the entire corpus.

  `chunk_text`                        The text the vector was produced
                                      from, returned to the generation
                                      step as context.

  `source_type`                       Distinguishes invoice text from
                                      report text. A question about why
                                      an invoice was flagged is answered
                                      by the report, not the invoice.

  `vendor`                            Supports vendor-scoped questions
                                      such as recurring discrepancy
                                      patterns.

`language`                          Supports filtering and diagnosis of
                                      extraction quality.
---------------------------------------------------------

Qdrant is built from PostgreSQL and never the other way round. Because
the source text is already persisted, losing the Qdrant volume is a
rebuild --- re-chunk, re-embed, repopulate --- not data loss. No OCR is
repeated and no invoice is re-read.

## 6.5 Redis: Disposable by Design

Cache only values that can be recomputed, each with an expiry:

```text
llm:{sha256(prompt)} -> cached model response
```

The test for whether something belongs in Redis: if the cache is
flushed, does anything break, or does the system merely become slower?
Only the second case belongs in Redis.

Agent state, audit records, and the vector index all fail this test and
must have a durable home elsewhere.

## 6.6 Service Addresses Inside the Network

Every value below is a hostname created by Compose from the service
name. These use the container port, not the host port --- the host
mapping is irrelevant to traffic between containers.

---

  From              To                Address            Common mistake

---

  `agent`           `postgres`        `postgres:5432`    Using `localhost`,
                                                         which refers to the
                                                         agent container
                                                         itself.

  `agent`           `qdrant`          `qdrant:6333`      Using an IP from
                                                         `docker inspect`,
                                                         which changes on
                                                         restart.

  `agent`           `redis`           `redis:6379`       Assuming the host
                                                         port mapping
                                                         applies between
                                                         containers.

  `agent`           `mock-erp`        `mock-erp:8000`    Using `8001`, which
                                                         is the host
                                                         mapping, not the
                                                         container port.

  `streamlit-ui`    `agent`           `agent:8000`       Calling
                                                         `localhost:8000`
                                                         from inside the UI
                                                         container.

your browser      `streamlit-ui`    `localhost:8501`   Expecting a service
                                                         name to resolve
                                                         from the host.
-----------------------------------------------------------------------

---

# 7. Implementation Details

## 7.1 Technology Stack

  Layer              Tool

---

  Agent framework    LangGraph, LangChain
  LLM gateway        LiteLLM (in-process)
  Models             AWS Bedrock --- Nova Lite, Cohere Command R+
  API services       FastAPI, Uvicorn, Pydantic
  OCR and parsing    Tesseract, Poppler, pdfplumber, python-docx
  Vector DB          Qdrant
  Relational DB      PostgreSQL 16
  Cache              Redis 7
  UI                 Streamlit
  Containerization   Docker, Docker Compose v2
  Base image         `python:3.11-slim` (pinned)
  Config             YAML persona and rules files

## 7.2 Model Selection

---

  Task                    Model                   Reason

---

  Reasoning and           Nova Lite               Efficient for
  summarization                                   structured reasoning
                                                  and report generation.

  RAG generation          Cohere Command R+       Optimised for
                                                  retrieval-augmented
                                                  generation.

Translation             Cohere Command R+       Handles multilingual
                                                  translation natively.
-----------------------------------------------------------------------

## 7.3 Agent Specification

---

  Agent                   Function                Uses LLM

---

  Invoice Monitor         Detects and routes new  No
                          files; checksums
                          against the audit
                          trail.

  Extractor               Parses PDF, DOCX, and   No
                          images; falls back to
                          OCR when needed.

  Translation             Detects language,       Yes
                          translates to English,
                          caches results.

  Invoice Data Validation Checks completeness,    Yes
                          totals, and tax
                          arithmetic against
                          `rules.yaml`.

  Business Validation     Compares invoice data   Yes
                          to ERP records via the
                          `mock-erp` API.

  Reporting               Produces discrepancy    Yes
                          report and
                          recommendation;
                          persists the outcome.

RAG agents              Indexing, retrieval,    Yes
                          augmentation,
                          generation, and
                          reflection.
---------------------------------------------------------------------------------------------------------------------

---

# 8. Containerization Requirements

You author three Dockerfiles and the complete `compose.yaml`. The
infrastructure services use official images and require no Dockerfile.
The requirements below define what your files must achieve; the
implementation is yours to determine.

## 8.1 Common Dockerfile Requirements

- Base image pinned to an explicit version. The latest tag is not
  acceptable.
- Layers ordered so that editing application source does not trigger a
  reinstall of Python dependencies.
- A `.dockerignore` present, excluding at minimum `.env`,
  `__pycache__/`, `*.pyc`, `.git/`, and any local virtual environment.
- No credentials, API keys, or `.env` contents in any image layer.
  Verified with `docker history`.
- The default command runs a long-lived foreground process, not a
  script that exits.
- The container runs as an unprivileged user, not root.
- Logs are written to stdout and stderr, never to files inside the
  container.
- Images are tagged explicitly, for example `my-agent:1.0`.

## 8.2 Agent Dockerfile

---

  Requirement                         Detail

---

  System packages                     OCR and PDF handling require
                                      binaries installed through the OS
                                      package manager: Tesseract plus the
                                      language packs the dataset actually
                                      needs, and Poppler utilities for
                                      PDF rendering.

  Language packs                      The dataset includes non-English
                                      invoices. English-only OCR will
                                      fail on them. Determine which packs
                                      are required and install those.

  Python dependencies                 LangGraph, LangChain, LiteLLM,
                                      FastAPI, Pydantic, pdfplumber,
                                      python-docx, pytesseract, the
                                      Qdrant client, and a PostgreSQL
                                      driver.

  Image size                          Keep the final image under
                                      approximately 1.5 GB. Clean
                                      package-manager caches within the
                                      same layer that creates them.

Entry point                         A long-running server exposing the
                                      agent workflow and a health
                                      endpoint on container port `8000`.
------------------------------------------------------------------

**Ordering hint:** Installing system packages, installing Python
dependencies, and copying application code are three concerns that
change at very different rates. Order them accordingly.

## 8.3 mock-erp and streamlit-ui Dockerfiles

### mock-erp

- Slim Python base; no OCR or document-parsing dependencies.
- FastAPI, Uvicorn, Pydantic, and a PostgreSQL driver only.
- Serves on container port `8000`, published on host port `8001`.
- Database credentials arrive from the environment at runtime.

### streamlit-ui

- Slim Python base; Streamlit, an HTTP client, and a PostgreSQL
  driver.
- Must bind to `0.0.0.0`, not `localhost`, or it will be unreachable
  from the host.
- Serves on container port `8501`.
- Reads reports from PostgreSQL and calls the agent by service name.

## 8.4 Compose Requirements

---

  Requirement             Applies to              Detail

---

  Single-command startup  All                     `docker compose up --build -d`
                                                  must bring the entire stack to a
                                                  working state with no manual
                                                  follow-up.

  Named volumes           postgres, qdrant        Declared at top level and
                                                  mounted at each service's data
                                                  directory. Data survives
                                                  `docker compose down`.

  Health checks           postgres, qdrant, redis Each must verify the service is
                                                  genuinely ready to accept
                                                  connections, not merely started.

  Dependency conditions   agent, mock-erp,        Application services wait for
                          streamlit-ui            dependencies to report healthy.
                                                  `depends_on` alone is not
                                                  sufficient and will cause
                                                  connection failures.

  Runtime secrets         agent, mock-erp,        AWS credentials and database
                          streamlit-ui            passwords supplied via an env
                                                  file. No secrets in
                                                  `compose.yaml` or in any image.

  Service-name networking All                     Services address each other by
                                                  service name. Hard-coded IPs or
                                                  localhost references between
                                                  containers are not acceptable.

  Schema initialisation   postgres                `erp_schema.sql` must load
                                                  automatically on first start. A
                                                  stack requiring a manual load
                                                  step has not met the
                                                  single-command requirement.

  Restart policy          All                     Set a policy appropriate to each
                                                  service. Be prepared to explain
                                                  why a restart policy does not
                                                  fix a mis-ordered startup.

Invoice input           agent                   The incoming directory must be
                                                  reachable inside the container.
                                                  This is a development
                                                  convenience; be prepared to
                                                  explain why object storage would
                                                  be used in production.
------------------------------------------------------------------------

**Common failure:** A service that starts before its database is ready
will exit, and a restart policy will hide this by looping indefinitely.
The container appears in `docker ps` while doing no useful work. Use
`docker compose logs` to confirm each service actually reached a running
state.

## 8.5 Recommended Build Sequence

Do not write all four files and then run everything at once. When six
services fail together, the cause is almost impossible to isolate. Build
up one piece at a time.

1. Build `mock-erp` first --- smallest dependency set, no system
   packages. Then `streamlit-ui`. Then `agent`.
2. For each image: write `.dockerignore`, build with an explicit tag,
   check the size, inspect layers with `docker history`, run it
   standalone, and confirm it serves before moving on.
3. Determine the agent's system packages in a throwaway interactive
   container rather than by rebuilding the image repeatedly.
4. Start infrastructure only:

   ```bash
   docker compose up -d postgres qdrant redis
   ```

   Confirm all three report healthy.
5. Confirm the ERP schema loaded and is populated.
6. Add `mock-erp`, then `agent`, then `streamlit-ui`, verifying each
   before the next.
7. Finally, prove a clean start:

   ```bash
   docker compose down -v
   docker compose up --build -d
   ```

## 8.6 Diagnostic Commands

---

  Command                                             Tells you

---

  `docker compose ps`                                 Which services are up and which are
                                                      actually healthy. Running is not
                                                      the same as working.

  `docker compose logs -f <service>`                  Why a service exited or is looping.
                                                      The first command to reach for.

  `docker compose exec <service> env`                 Which environment variables
                                                      actually reached the container.

  `docker compose exec agent getent hosts postgres`   Whether a service name resolves
                                                      from inside the container.

  `docker compose config`                             The fully resolved Compose file
                                                      with variables substituted. Reveals
                                                      typos before you run anything.

  `docker history <image> --no-trunc`                 Every layer and the command that
                                                      created it. Used to prove no secret
                                                      was baked in.

`docker system df`                                  Disk consumed by images,
                                                      containers, volumes, and build
                                                      cache.
------------------------------------------------------------

---

# 9. Verification Checklist

Complete every check below before your demonstration. Checks 3 and 4 are
the primary evidence that the stack is genuinely production-shaped
rather than merely running.

## Check 1 --- Single-command startup

From a clean state, the full stack starts and all six services report
healthy.

```bash
docker compose down -v
docker compose up --build -d
docker compose ps
```

## Check 2 --- End-to-end processing

Place an invoice in the incoming directory. Confirm it is extracted,
translated, validated against the ERP service, and that a report is
produced and stored in PostgreSQL.

## Check 3 --- Persistence across restart

Process at least one invoice and index it for RAG, then destroy and
recreate the stack without removing volumes.

```bash
docker compose down
docker compose up -d
```

After restart, and without reprocessing anything, demonstrate that the
audit trail is intact and the RAG interface still answers questions
about the previously indexed invoice.

## Check 4 --- Deliberate data loss

Show the inverse, to prove the persistence in Check 3 was real and not
incidental.

```bash
docker compose down -v
docker compose up -d
```

Confirm the audit trail and RAG index are now empty, and explain which
flag caused the difference.

## Check 5 --- No secrets in images

```bash
docker history <your-image>:<tag> --no-trunc
```

## Check 6 --- Service-name resolution

From inside the agent container, confirm PostgreSQL, Qdrant, and the ERP
service all resolve by service name rather than by IP address.

```bash
docker compose exec agent bash
```

---

# 10. Deliverables

- Source code, including three Dockerfiles, three `.dockerignore`
  files, and `compose.yaml`.
- Your audit schema definition.
- A README documenting how to configure `.env` and start the stack
  from a clean checkout.
- Working demonstration covering all six verification checks.
- Presentation slides, not exceeding five, including one architecture
  diagram of the deployed stack.
- Prompt templates and persona files (`.yaml` / `.json`).

> **Do not submit:** Your `.env` file, or any file containing real
> credentials. Submitting live keys is treated as a security failure
> regardless of the quality of the rest of the work.

---

# 11. Evaluation Criteria (50 Marks)

  Component                           Weightage

---

  Functional completeness                   25%
  RAG and agentic integration               25%
  Containerization and deployment           25%
  Code quality and modularity               15%
  UI and human-in-the-loop                  10%

## 11.1 Containerization Breakdown

---

  Criterion                                    Marks Evidence

---

  Full stack runs from                           10% Check 1. All six
  a single command                                   services healthy, no
                                                     manual steps.

  Dockerfile quality                             10% Correct layer
                                                     ordering, pinned base
                                                     image,
                                                     `.dockerignore`
                                                     present, non-root
                                                     user, no secrets in
                                                     any layer (Check 5).

Persistence correctly                           5% Checks 3 and 4. Data
  configured                                         survives `down`, is
                                                     lost on `down -v`,
                                                     and the team can
                                                     explain why.
-----------------------------------------------------------------

A stack that runs but loses its audit trail on restart will not receive
persistence marks. A stack with credentials baked into an image will not
receive Dockerfile marks, irrespective of layer quality.

---

## Source Transcription Notes

- This Markdown document is formatted for repository use; wording and
  headings have been cleaned up for readability.
- The original photographs contain a few small or blurred lines. In
  particular, the vendor/PO endpoint examples in the photographed
  functional requirements are not all legible. Those uncertain
  endpoint strings are explicitly marked above rather than silently
  guessed.
- The original problem statement describes the initial capstone
  technology options (including FAISS/Weaviate and Streamlit/React),
  while the containerized extension specifies the concrete
  implementation stack (PostgreSQL 16, Qdrant, Redis 7, Streamlit,
  Docker Compose, and the listed AWS Bedrock models). Both are
  retained in their respective sections.
- The original photographs include an architecture diagram that is
  described textually above; the diagram itself is not recreated in
  this text file.
