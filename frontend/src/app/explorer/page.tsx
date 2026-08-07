"use client";

import { useState } from "react";
import Link from "next/link";
import { ApiError, ghostNote, submitFeedback, GhostNoteResult } from "@/lib/api";
import { relevanceBand } from "@/lib/relevance";
import styles from "./page.module.css";
import {
  SearchIcon,
  XIcon,
  FolderIcon,
  ThumbsUpIcon,
  ThumbsDownIcon,
} from "./icons";

type Status = "idle" | "loading" | "success" | "error";

const NOTE_STORAGE_PREFIX = "ghostkube:note:";

export default function ExplorerPage() {
  const [query, setQuery] = useState("");
  const [lastQuery, setLastQuery] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [results, setResults] = useState<GhostNoteResult[]>([]);
  const [topSummary, setTopSummary] = useState<{
    summary: string;
    summary_path: string | null;
    synthesized: boolean;
  } | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  const [feedbackGiven, setFeedbackGiven] = useState<
    Record<string, "up" | "down">
  >({});

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;

    setStatus("loading");
    setErrorMessage(null);
    setFeedbackError(null);

    try {
      const result = await ghostNote({ query: trimmed, top_results: 8 });
      setResults(result.results);
      setTopSummary(
        result.results.length > 0
          ? {
              summary: result.summary,
              summary_path: result.summary_path,
              synthesized: result.synthesized,
            }
          : null
      );
      setLastQuery(trimmed);
      setStatus("success");
    } catch (err) {
      setErrorMessage(
        err instanceof ApiError ? err.message : "Something went wrong."
      );
      setStatus("error");
    }
  }

  function handleClear() {
    setQuery("");
    setResults([]);
    setTopSummary(null);
    setLastQuery("");
    setStatus("idle");
    setErrorMessage(null);
  }

  async function handleFeedback(result: GhostNoteResult, rating: "up" | "down") {
    setFeedbackError(null);
    try {
      await submitFeedback({
        chunk_id: result.chunk_id,
        query: lastQuery,
        rating,
      });
      setFeedbackGiven((prev) => ({ ...prev, [result.chunk_id]: rating }));
    } catch (err) {
      setFeedbackError(
        err instanceof ApiError ? err.message : "Couldn't record feedback."
      );
    }
  }

  function openNote(result: GhostNoteResult) {
    // The Brain API only synthesizes a summary for the top hit (one Groq
    // call per search, not per-result), so only attach it when this is that
    // result - everything else genuinely has no summary to show.
    const isTopResult = results[0]?.chunk_id === result.chunk_id;
    window.sessionStorage.setItem(
      `${NOTE_STORAGE_PREFIX}${result.chunk_id}`,
      JSON.stringify({
        ...result,
        query: lastQuery,
        ...(isTopResult && topSummary ? topSummary : {}),
      })
    );
  }

  return (
    <div>
      <h1 className={styles.title}>Explorer</h1>
      <p className={styles.subtitle}>Search ingested ghost notes.</p>

      <form className={styles.searchForm} onSubmit={handleSearch}>
        <div className={styles.searchWrap}>
          <SearchIcon className={styles.searchIcon} />
          <input
            className={styles.searchInput}
            type="text"
            placeholder="Search ghost notes (e.g. authentication flow kubernetes)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && (
            <button
              type="button"
              className={styles.clearIconBtn}
              onClick={handleClear}
              aria-label="Clear search"
            >
              <XIcon className={styles.clearIcon} />
            </button>
          )}
        </div>
        <button
          type="submit"
          className={styles.searchBtn}
          disabled={status === "loading" || !query.trim()}
        >
          {status === "loading" ? "Searching..." : "Search"}
        </button>
      </form>

      {feedbackError && <div className={styles.errorBanner}>{feedbackError}</div>}

      {status === "idle" && (
        <p className={styles.hintState}>
          Search your ingested notes to get started.
        </p>
      )}

      {status === "loading" && <p className={styles.hintState}>Searching…</p>}

      {status === "error" && (
        <div className={styles.errorBanner}>{errorMessage}</div>
      )}

      {status === "success" && (
        <>
          <p className={styles.resultsCount}>
            {results.length} result{results.length === 1 ? "" : "s"} found for
            &ldquo;{lastQuery}&rdquo;
          </p>

          {results.length === 0 ? (
            <div className={styles.emptyState}>
              <p className={styles.emptyTitle}>No results found</p>
              <p className={styles.emptyText}>
                We couldn&apos;t find any notes matching your search. Try
                different keywords, or make sure a source has been ingested
                first.
              </p>
              <button className={styles.clearSearchBtn} onClick={handleClear}>
                Clear search
              </button>
            </div>
          ) : (
            <div className={styles.results}>
              {results.map((result) => {
                const scorePercent = Math.round(result.relevance_score * 100);
                const band = relevanceBand(scorePercent);
                const path =
                  (result.metadata.path as string | undefined) ??
                  "unknown path";
                const given = feedbackGiven[result.chunk_id];

                return (
                  <div key={result.chunk_id} className={styles.card}>
                    <div className={styles.cardMain}>
                      <Link
                        href={`/notes/${result.chunk_id}`}
                        className={styles.cardLink}
                        onClick={() => openNote(result)}
                      >
                        <p className={styles.cardText}>{result.text}</p>
                      </Link>
                      <div className={styles.cardPath}>
                        <FolderIcon className={styles.pathIcon} />
                        <span className={styles.mono}>{path}</span>
                      </div>
                    </div>

                    <div className={styles.cardSide}>
                      <div className={styles.scoreBlock}>
                        <span
                          className={`${styles.pill} ${styles[band.pillClass]}`}
                        >
                          {scorePercent}
                        </span>
                        <span className={styles.bandLabel}>{band.label}</span>
                      </div>
                      <div className={styles.feedbackRow}>
                        <button
                          type="button"
                          className={`${styles.feedbackBtn} ${
                            given === "up" ? styles.feedbackActiveUp : ""
                          }`}
                          onClick={() => handleFeedback(result, "up")}
                          disabled={!!given}
                          aria-label="Mark as helpful"
                        >
                          <ThumbsUpIcon className={styles.feedbackIcon} />
                        </button>
                        <button
                          type="button"
                          className={`${styles.feedbackBtn} ${
                            given === "down" ? styles.feedbackActiveDown : ""
                          }`}
                          onClick={() => handleFeedback(result, "down")}
                          disabled={!!given}
                          aria-label="Mark as not helpful"
                        >
                          <ThumbsDownIcon className={styles.feedbackIcon} />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
