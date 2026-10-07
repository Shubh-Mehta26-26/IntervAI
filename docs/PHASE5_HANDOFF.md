# Phase 5 handoff: RAG-grounded evaluation

## Delivered behavior

Answer evaluation now embeds a query built from the question, topic, skill, and candidate claims; retrieves compatible ready chunks from PostgreSQL with pgvector cosine distance; supplies only those chunks to the evaluator; and validates every returned `knowledge_chunk_id` against the retrieved set. A response can be `grounded` only when it cites at least one retrieved chunk. Empty or inadequate context is persisted as `insufficient`, never presented as grounded.

Practice interviews expose source title, stable source identifier, relationship, and supported claim immediately. Simulation interviews retain the Phase 4 reveal policy and expose evaluation details only after completion.

## Persistence and traceability

- `knowledge_documents` stores provenance, domain/topic metadata, checksum, state, and embedding contract.
- `knowledge_chunks` stores deterministic chunks and `vector(1536)` embeddings with an HNSW cosine index.
- `retrieval_logs` records the exact query, filters, ordered chunk IDs/scores, embedding provider/model, version, interview, answer, and evaluation.
- `evaluation_sources` links validated citations to the evaluation and immutable chunk, including rank, similarity, relationship, and supported claim.
- `answer_evaluations` records `grounding_status` and reviewer-facing `evaluation_notes`.

Migration `7b31d944be52` upgrades from the Phase 4 head and has been verified through upgrade, full downgrade to base, and upgrade to head in the disposable PostgreSQL test database.

## Provider configuration

Both provider adapters use `OPENAI_API_KEY`. The required local variables are:

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=<model available to the local OpenAI project>
OPENAI_API_KEY=<local secret>
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
```

The OpenAI embedding adapter calls `/v1/embeddings` with float encoding and an explicit 1536-dimensional contract. Provider responses are checked for item count and vector dimensions. The application reports exact missing variable names and never logs the key.

## Ingestion

The initial project-authored corpus is under `knowledge_base/sources` and covers DBMS indexes/query planning, transactions/normalization, operating-system concurrency/deadlocks, Python generators/decorators, binary search, and hash tables.

After configuring the local providers, ingest it with:

```powershell
.\.venv\Scripts\python.exe scripts\ingest_knowledge.py knowledge_base\sources
```

The command accepts one `.md`/`.txt` file or a directory. It enforces UTF-8, regular-file and 2 MiB limits, rejects unsafe source paths, batches embeddings, and avoids re-embedding an unchanged source checksum. A changed source atomically replaces its chunks.

## Security boundaries

Candidate answers and retrieved text remain inside explicit data boundaries. The evaluation system prompt labels chunks as untrusted reference data and forbids following embedded instructions, role changes, or secret requests. Structured output validation rejects unknown, duplicate, or fabricated citations before persistence. Retrieval filters out failed documents and vectors created by a different provider, model, or dimension.

## Verification

- The PostgreSQL suite covers complete migration down/up, deterministic chunking, idempotent ingestion, real pgvector retrieval, empty retrieval, provider failure, dimension mismatch, unsafe inputs, prompt injection boundaries, citation rejection, grounded API source output, and retrieval-log persistence.
- Ruff, Python compilation, ESLint, TypeScript, Next production build, Docker health, and desktop/mobile UI are verification gates.

## Live verification gate

At implementation time the repository `.env` did not contain `LLM_PROVIDER`, `LLM_MODEL`, `OPENAI_API_KEY`, `EMBEDDING_PROVIDER`, or `EMBEDDING_MODEL`. No live OpenAI call or corpus ingestion was claimed. Once those variables are configured locally, run ingestion first, then the interview smoke test and inspect `retrieval_logs` plus returned citation IDs before declaring the live gate complete.
