"use client";

import { useEffect, useState, Fragment } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ApiError, getChunk, submitFeedback } from "@/lib/api";
import { relevanceBand } from "@/lib/relevance";
import styles from "./page.module.css";
import {
  ArrowLeftIcon,
  FolderIcon,
  ExternalLinkIcon,
  ThumbsUpIcon,
  ThumbsDownIcon,
} from "./icons";

const NOTE_STORAGE_PREFIX = "ghostkube:note:";

interface StoredNote {
  chunk_id: string;
  text: string;
  relevance_score: number;
  metadata: Record<string, unknown>;
  query: string;
}

type Status = "loading" | "success" | "error";

const STRUCTURED_KEYS = new Set([
  "path",
  "extension",
  "is_code",
  "schema",
  "source_url",
  "source_type",
]);

export default function NoteDetailPage() {
  const { chunkId } = useParams<{ chunkId: string }>();

  const [status, setStatus] = useState<Status>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [metadata, setMetadata] = useState<Record<string, unknown>>({});
  const [relevanceScore, setRelevanceScore] = useState<number | null>(null);
  const [query, setQuery] = useState<string | null>(null);
  const [feedbackGiven, setFeedbackGiven] = useState<"up" | "down" | null>(null);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);

  useEffect(() => {
    if (!chunkId) return;

    const raw = window.sessionStorage.getItem(
      `${NOTE_STORAGE_PREFIX}${chunkId}`
    );
    if (raw) {
      try {
        const stored: StoredNote = JSON.parse(raw);
        setText(stored.text);
        setMetadata(stored.metadata);
        setRelevanceScore(stored.relevance_score);
        setQuery(stored.query || null);
        setStatus("success");
        return;
      } catch {
        // corrupted sessionStorage entry - fall through to the API fetch
      }
    }

    let cancelled = false;
    setStatus("loading");
    getChunk(chunkId)
      .then((chunk) => {
        if (cancelled) return;
        setText(chunk.text);
        setMetadata(chunk.metadata);
        setRelevanceScore(null);
        setQuery(null);
        setStatus("success");
      })
      .catch((err) => {
        if (cancelled) return;
        setErrorMessage(
          err instanceof ApiError ? err.message : "Something went wrong."
        );
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [chunkId]);

  async function handleFeedback(rating: "up" | "down") {
    if (!query || !chunkId) return;
    setFeedbackError(null);
    try {
      await submitFeedback({ chunk_id: chunkId, query, rating });
      setFeedbackGiven(rating);
    } catch (err) {
      setFeedbackError(
        err instanceof ApiError ? err.message : "Couldn't record feedback."
      );
    }
  }

  const path = (metadata.path as string | undefined) ?? "unknown path";
  const sourceUrl = metadata.source_url as string | undefined;
  const sourceType = metadata.source_type as string | undefined;
  const extension = metadata.extension as string | undefined;
  const scorePercent =
    relevanceScore !== null ? Math.round(relevanceScore * 100) : null;
  const band = scorePercent !== null ? relevanceBand(scorePercent) : null;
  const extraMetadata = Object.entries(metadata).filter(
    ([key]) => !STRUCTURED_KEYS.has(key)
  );

  // Prefer a PR-specific link over the generic repo root when pr_ingest.py
  // (Phase 8.5) has attached one - a note from a PR thread should deep-link
  // to that PR, not just the repo.
  const prUrl = metadata.pr_url as string | undefined;
  const primaryLinkUrl = prUrl ?? sourceUrl;
  const primaryLinkLabel = prUrl ? "View pull request" : "View source repository";

  return (
    <div>
      <Link href="/explorer" className={styles.backLink}>
        <ArrowLeftIcon className={styles.backIcon} />
        Back to Explorer
      </Link>

      {status === "loading" && (
        <p className={styles.hintState}>Loading note…</p>
      )}

      {status === "error" && (
        <div className={styles.errorState}>
          <p className={styles.errorTitle}>Note not found</p>
          <p className={styles.errorText}>{errorMessage}</p>
          <Link href="/explorer" className={styles.errorLink}>
            Search again
          </Link>
        </div>
      )}

      {status === "success" && (
        <div className={styles.layout}>
          <div className={styles.main}>
            <div className={styles.pathRow}>
              <FolderIcon className={styles.pathIcon} />
              <span className={styles.mono}>{path}</span>
            </div>

            <pre className={styles.textBlock}>{text}</pre>

            <div className={styles.summaryBlock}>
              <span className={styles.summaryLabel}>Summary</span>
              <span className={styles.summaryPlaceholder}>(Phase 13)</span>
            </div>

            <div className={styles.feedbackSection}>
              <p className={styles.feedbackPrompt}>Was this note helpful?</p>
              {query ? (
                <div className={styles.feedbackRow}>
                  <button
                    type="button"
                    className={`${styles.feedbackBtn} ${
                      feedbackGiven === "up" ? styles.feedbackActiveUp : ""
                    }`}
                    onClick={() => handleFeedback("up")}
                    disabled={!!feedbackGiven}
                  >
                    <ThumbsUpIcon className={styles.feedbackIcon} />
                    Helpful
                  </button>
                  <button
                    type="button"
                    className={`${styles.feedbackBtn} ${
                      feedbackGiven === "down" ? styles.feedbackActiveDown : ""
                    }`}
                    onClick={() => handleFeedback("down")}
                    disabled={!!feedbackGiven}
                  >
                    <ThumbsDownIcon className={styles.feedbackIcon} />
                    Not helpful
                  </button>
                </div>
              ) : (
                <p className={styles.feedbackUnavailable}>
                  Feedback is available when you reach a note from an
                  Explorer search.
                </p>
              )}
              {feedbackError && (
                <p className={styles.feedbackError}>{feedbackError}</p>
              )}
            </div>
          </div>

          <aside className={styles.sidebar}>
            <h2 className={styles.sidebarTitle}>Metadata</h2>
            <dl className={styles.metaList}>
              <dt>Path</dt>
              <dd className={styles.mono}>{path}</dd>

              {extension && (
                <Fragment>
                  <dt>Extension</dt>
                  <dd className={styles.mono}>{extension}</dd>
                </Fragment>
              )}

              {sourceType && (
                <Fragment>
                  <dt>Source type</dt>
                  <dd>{sourceType}</dd>
                </Fragment>
              )}

              <dt>Chunk ID</dt>
              <dd className={styles.mono} title={chunkId}>
                {chunkId?.slice(0, 16)}…
              </dd>

              {extraMetadata.map(([key, value]) => {
                const stringValue = String(value);
                const isUrl =
                  typeof value === "string" && stringValue.startsWith("http");
                return (
                  <Fragment key={key}>
                    <dt>{key}</dt>
                    <dd className={styles.mono}>
                      {isUrl ? (
                        <a
                          href={stringValue}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={styles.metaLink}
                        >
                          {stringValue}
                        </a>
                      ) : (
                        stringValue
                      )}
                    </dd>
                  </Fragment>
                );
              })}
            </dl>

            {primaryLinkUrl && (
              <a
                href={primaryLinkUrl}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.sourceLink}
              >
                <ExternalLinkIcon className={styles.sourceLinkIcon} />
                {primaryLinkLabel}
              </a>
            )}

            {band && scorePercent !== null && (
              <div className={styles.relevanceBlock}>
                <h2 className={styles.sidebarTitle}>Relevance</h2>
                <div className={styles.relevanceRow}>
                  <span
                    className={`${styles.pill} ${styles[band.pillClass]}`}
                  >
                    {scorePercent}
                  </span>
                  <span className={styles.bandLabel}>{band.label}</span>
                </div>
                {query && (
                  <p className={styles.relevanceQuery}>for &ldquo;{query}&rdquo;</p>
                )}
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
