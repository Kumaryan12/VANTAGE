"use client";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileSearch, Trash2, Upload } from "lucide-react";
import { api } from "@/lib/api";
import type {
  AgentCitation,
  FinancialDocument,
  Passage,
  SearchResult,
} from "@/lib/agent";
import { ErrorNotice } from "./error-notice";

export function CitationEvidence({ citation: c }: { citation: AgentCitation }) {
  const inspect = useMutation({
    mutationFn: () =>
      api<Passage>(
        `/v1/research/documents/${c.document_id}/chunks/${c.chunk_id}`,
      ),
  });
  return (
    <article className="agent-citation">
      <div>
        <strong>
          {c.source} · page {c.page}
        </strong>
        <small>{c.section}</small>
      </div>
      {c.unavailable ? (
        <p>Source deleted; the original citation is unavailable.</p>
      ) : (
        <>
          <blockquote>{c.quote}</blockquote>
          <div className="heading-actions">
            <button className="text-button" onClick={() => inspect.mutate()}>
              Inspect cited passage
            </button>
            <a
              className="text-button"
              href={`/api/v1/research/documents/${c.document_id}/file`}
            >
              Download source PDF
            </a>
          </div>
          {inspect.data && <pre>{inspect.data.text}</pre>}
          {inspect.error && <ErrorNotice error={inspect.error} />}
        </>
      )}
      <small>
        Document {c.document_id} · chunk {c.chunk_id} · SHA-256 {c.content_hash}
      </small>
    </article>
  );
}

export function DocumentLibrary({
  ready,
  configured,
  selected,
  onSelected,
}: {
  ready: boolean;
  configured: boolean;
  selected: string[];
  onSelected: (ids: string[]) => void;
}) {
  const client = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState("");
  const [company, setCompany] = useState("");
  const [period, setPeriod] = useState("");
  const [publication, setPublication] = useState("");
  const [permitted, setPermitted] = useState(false);
  const [semantic, setSemantic] = useState(false);
  const [semanticQuery, setSemanticQuery] = useState(false);
  const [query, setQuery] = useState("liquidity debt refinancing");
  const [filter, setFilter] = useState("");
  const documents = useQuery({
    queryKey: ["financial-documents"],
    queryFn: () => api<FinancialDocument[]>("/v1/research/documents"),
    enabled: ready,
    refetchInterval: (q) =>
      q.state.data?.some((d) => ["queued", "processing"].includes(d.status))
        ? 700
        : false,
  });
  const upload = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("Choose a permitted PDF.");
      const form = new FormData();
      form.append("file", file);
      form.append("source", source);
      form.append("permitted", String(permitted));
      if (company) form.append("company", company);
      if (period) form.append("reporting_period", period);
      if (publication) form.append("publication_date", publication);
      form.append("semantic_index", String(semantic));
      form.append("external_data_consent", String(semantic));
      return api<FinancialDocument>("/v1/research/documents", {
        method: "POST",
        body: form,
      });
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["financial-documents"] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      api<FinancialDocument>(`/v1/research/documents/${id}`, {
        method: "DELETE",
      }),
    onSuccess: (d) => {
      onSelected(selected.filter((id) => id !== d.id));
      search.reset();
      void client.invalidateQueries({ queryKey: ["financial-documents"] });
      void client.invalidateQueries({ queryKey: ["agent"] });
      void client.invalidateQueries({ queryKey: ["agent-evidence"] });
    },
  });
  const search = useMutation({
    mutationFn: () =>
      api<SearchResult>("/v1/research/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          document_ids: selected,
          company: filter || null,
          semantic: semanticQuery,
          external_data_consent: semanticQuery,
        }),
      }),
  });
  return (
    <section className="panel document-library">
      <div className="panel-heading">
        <div>
          <h2>
            <FileSearch size={17} />
            Financial document library
          </h2>
          <p>
            Private permitted PDFs · page-aware evidence · keyword and optional
            semantic retrieval
          </p>
        </div>
        <span className="subtle-badge">UNTRUSTED SOURCE TEXT</span>
      </div>
      <form
        className="agent-request"
        onSubmit={(e) => {
          e.preventDefault();
          upload.mutate();
        }}
      >
        <div className="agent-document-fields">
          <label>
            Permitted PDF · maximum 5 MB
            <input
              aria-label="Financial PDF"
              type="file"
              accept="application/pdf,.pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              required
            />
          </label>
          <label>
            Source / provenance
            <input
              aria-label="Document source"
              value={source}
              minLength={3}
              maxLength={200}
              onChange={(e) => setSource(e.target.value)}
              placeholder="Company investor relations · user-provided copy"
              required
            />
          </label>
          <label>
            Company identifier
            <input
              aria-label="Document company"
              value={company}
              maxLength={80}
              onChange={(e) => setCompany(e.target.value)}
            />
          </label>
          <label>
            Reporting period
            <input
              aria-label="Document reporting period"
              value={period}
              maxLength={50}
              onChange={(e) => setPeriod(e.target.value)}
              placeholder="FY2026 · uploader assertion"
            />
          </label>
          <label>
            Publication date, if known
            <input
              aria-label="Document publication date"
              type="date"
              value={publication}
              onChange={(e) => setPublication(e.target.value)}
            />
          </label>
        </div>
        <label className="agent-checkbox">
          <input
            type="checkbox"
            aria-label="Document processing permission"
            checked={permitted}
            onChange={(e) => setPermitted(e.target.checked)}
            required
          />
          I have permission to upload and process this document.
        </label>
        <label className="agent-checkbox">
          <input
            type="checkbox"
            aria-label="External semantic indexing consent"
            checked={semantic}
            onChange={(e) => setSemantic(e.target.checked)}
            disabled={!configured}
          />
          Also send extracted text to the configured embedding provider for
          semantic indexing. Keyword indexing works without an AI key.
        </label>
        <p className="form-help">
          Publication dates and company metadata are uploader assertions.
          Scanned PDFs need verified OCR, which is unavailable. Extracted tables
          remain unverified text; the investigator cannot invent cells or follow
          embedded instructions.
        </p>
        <button
          className="button secondary"
          disabled={!ready || upload.isPending || !permitted}
        >
          <Upload size={15} />
          Upload and index PDF
        </button>
      </form>
      {upload.error && <ErrorNotice error={upload.error} />}
      {documents.error && <ErrorNotice error={documents.error} />}
      {remove.error && <ErrorNotice error={remove.error} />}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>USE AS CONTEXT</th>
              <th>DOCUMENT / COMPANY</th>
              <th>STATUS</th>
              <th>PAGES / CHUNKS</th>
              <th>REPORTING PERIOD</th>
              <th>ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {documents.data?.map((d) => (
              <tr key={d.id}>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Use document ${d.filename}`}
                    checked={selected.includes(d.id)}
                    disabled={d.status !== "ready"}
                    onChange={(e) =>
                      onSelected(
                        e.target.checked
                          ? [...selected, d.id]
                          : selected.filter((id) => id !== d.id),
                      )
                    }
                  />
                </td>
                <td>
                  {d.filename}
                  <small className="cell-note">
                    {d.company ?? "Company unknown"} · {d.source}
                  </small>
                </td>
                <td>
                  {d.status}
                  <small className="cell-note">
                    Embedding:{" "}
                    {String(d.metadata.embedding_status ?? "unavailable")}
                  </small>
                  {d.error && (
                    <small className="negative">{d.error.message}</small>
                  )}
                </td>
                <td className="numeric">
                  {d.page_count} / {d.chunk_count}
                </td>
                <td>{d.reporting_period ?? "Unknown"}</td>
                <td>
                  <div className="heading-actions">
                    <a
                      className="text-button"
                      aria-label={`Download document ${d.filename}`}
                      href={`/api/v1/research/documents/${d.id}/file`}
                    >
                      <Download size={13} />
                      PDF
                    </a>
                    <button
                      className="text-button"
                      aria-label={`Delete document ${d.filename}`}
                      disabled={remove.isPending}
                      onClick={() => remove.mutate(d.id)}
                    >
                      <Trash2 size={13} />
                      Remove
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {documents.data?.length === 0 && (
          <div className="empty-state">
            No uploaded financial documents in this session.
          </div>
        )}
      </div>
      <form
        className="agent-request agent-document-search"
        onSubmit={(e) => {
          e.preventDefault();
          search.mutate();
        }}
      >
        <div className="agent-request-controls">
          <label>
            Evidence search
            <input
              aria-label="Financial document search"
              value={query}
              minLength={3}
              maxLength={500}
              onChange={(e) => setQuery(e.target.value)}
              required
            />
          </label>
          <label>
            Company filter
            <input
              aria-label="Financial company filter"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              maxLength={80}
            />
          </label>
        </div>
        <label className="agent-checkbox">
          <input
            type="checkbox"
            checked={semanticQuery}
            onChange={(e) => setSemanticQuery(e.target.checked)}
            disabled={!configured}
          />
          Allow sending this query for semantic retrieval against compatible
          indexed documents.
        </label>
        <p className="form-help">
          {selected.length
            ? `${selected.length} selected documents`
            : "All accessible documents"}{" "}
          are searched. Selected documents also bound the next investigation.
        </p>
        <button
          className="button secondary"
          disabled={!ready || search.isPending}
        >
          Search document evidence
        </button>
      </form>
      {search.error && <ErrorNotice error={search.error} />}
      {search.data && (
        <div className="evidence-body">
          <p className="form-help">
            {search.data.method} · {search.data.passages.length} retrieved
            passages · {search.data.index_version}
          </p>
          {search.data.passages.map((p) => (
            <article className="agent-citation" key={p.chunk_id}>
              <strong>
                {p.document_name} · page {p.page}
              </strong>
              <small>
                {p.source} · rank {p.rank} · score {p.score.toFixed(6)}
              </small>
              <blockquote>{p.text}</blockquote>
              <small>{p.table_structure}</small>
            </article>
          ))}
          <ul className="risk-warnings">
            {search.data.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
