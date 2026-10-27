# Financial PDF evidence and retrieval

User-uploaded permitted PDFs are the only ingestion source. No unrestricted scraping or arbitrary URL fetching is implemented. Annual reports, disclosures, statements and presentations are accepted as PDF text; company/reporting period/publication metadata are uploader assertions, not independently certified filings or current market data.

## Ingestion and storage

`POST /api/v1/research/documents` accepts a PDF plus source, permission acknowledgment and optional company/reporting period/publication date. It returns 202 and processing status. Limits: file 5 MB, complete multipart stream 6 MB, 100 pages, 50,000 characters per page, 500,000 total text characters, 600 chunks per document, 20 active documents and 2,500 chunks per session. One parser job per process is admitted. Header, extension and MIME are checked; encrypted, active-action/embedded-file, malformed or image-only documents fail explicitly. OCR is not implemented.

A fixed parser module runs in a child process, with no shell expansion, application tokens or provider credentials in its environment. CPU limit is ten seconds, wall limit fifteen, decompressed page streams eight MB; Linux additionally limits address space to 512 MB. This is resource/process isolation, not a comprehensive OS sandbox against parser vulnerabilities. Extraction never follows links or executes PDF instructions. PDF content hashes are checked before processing/download.

Private originals live in `DOCUMENT_STORAGE_DIR` (repository `artifacts/documents` default); Compose mounts a separate persistent volume. Database rows store owner, clean original filename, content hash, source/company/reporting period/date, upload time, extraction status/errors, version, page/chunk counts and metadata. Chunk rows retain owner, exact one-based source page, source section label, text hash, token counts and optional embedding/model. Page-aware character chunks default to 1,800 chars/180 overlap (bounded configurable 400–3,000 chars). Sections are extracted first-line labels and may be imperfect; chunks never span pages. No reliable table structure or missing cells/units/arithmetic are invented.

## Retrieval

BM25 keyword retrieval works without credentials. The bounded session index is scanned only **after** SQL owner/document/company/status filtering. Query terms and persisted token counts determine deterministic scores; stable ID tie breaks and source-overlap deduplication retain provenance. Filters do not silently broaden if explicit documents are missing or foreign. Insufficient matches return an explicit evidence warning.

Opt-in semantic indexing sends redacted extracted chunks to the configured OpenAI embedding provider, at most 64 bounded passages per call, requesting 256-dimensional vectors. A flat exact-cosine NumPy vector index is appropriate for the 2,500-chunk local bound. Embedding model and dimensional compatibility are checked. Semantic query consent is separate; compatible authorized vectors are scored with a documented .2 cosine candidate threshold, then combined with positive BM25 ranks by reciprocal rank fusion (constant 60). Scores are retrieval diagnostics, not probabilities or financial risk measures. Provider/index failures retain keyword retrieval with warnings. Normal Demo Mode never requires vector credentials or network access.

Embeddings and query semantics have mocked contract tests; no claim of measured live embedding quality follows. There is no learned reranker. Relative publication timing, visual reading order, tables, OCR and statement authenticity remain limitations.

## Citations and deletion

The graph may cite only retrieved chunk IDs and exact quote substrings. The deterministic resolver reauthorizes the document/chunk and checks page, quote and text hash. The model cannot invent page/source identifiers. Original PDFs are attachment downloads with sandbox/CSP/nosniff headers; the UI inspects extracted passages as escaped text, not executable HTML.

Deletion removes original file, keyword tokens and embeddings, tombstones metadata and purges copied passages/quotes from stored investigation evidence/answers. Old citations become unavailable and warnings remain; audit identifiers survive. This is application-level cleanup, not forensic erasure of database pages/backups or every prior query string. Back up database plus document/model volumes together. Identity/session expiry still prevents private recovery; a retention and backup policy remains Phase 6 work.
