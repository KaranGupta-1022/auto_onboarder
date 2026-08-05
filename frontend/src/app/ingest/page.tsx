"use client";

import { useEffect, useState } from "react";
import { ApiError, ingest, IngestRequest } from "@/lib/api";
import styles from "./page.module.css";
import { LinkIcon, DocumentIcon, UploadIcon } from "./icons";

const RECENT_JOBS_KEY = "ghostkube:recent-ingests";
const MAX_RECENT_JOBS = 10;

interface RecentJob {
  url: string;
  source_type: string;
  status: "success" | "error";
  chunks_ingested?: number;
  total_characters?: number;
  message: string;
  timestamp: string;
}

function loadRecentJobs(): RecentJob[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.sessionStorage.getItem(RECENT_JOBS_KEY);
    return raw ? (JSON.parse(raw) as RecentJob[]) : [];
  } catch {
    return [];
  }
}

function saveRecentJob(job: RecentJob) {
  const existing = loadRecentJobs();
  const next = [job, ...existing].slice(0, MAX_RECENT_JOBS);
  window.sessionStorage.setItem(RECENT_JOBS_KEY, JSON.stringify(next));
  return next;
}

function formatDate(timestamp: string) {
  return new Date(timestamp).toLocaleDateString(undefined, {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

function formatTime(timestamp: string) {
  return new Date(timestamp).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function formatSource(url: string): string {
  try {
    const parsed = new URL(url);
    const parts = parsed.pathname.split("/").filter(Boolean);
    if (parsed.hostname.includes("github.com") && parts.length >= 2) {
      return `${parts[0]}/${parts[1]}`;
    }
  } catch {
    // not a parseable URL, fall back to showing it as-is
  }
  return url;
}

type FormStatus = "idle" | "loading" | "success" | "error";

export default function IngestPage() {
  const [url, setUrl] = useState("");
  const [sourceType, setSourceType] = useState<"repo" | "pr">("repo");
  const [metadataText, setMetadataText] = useState("");
  const [status, setStatus] = useState<FormStatus>("idle");
  const [loadingStep, setLoadingStep] = useState<1 | 2>(1);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<RecentJob | null>(null);
  const [recentJobs, setRecentJobs] = useState<RecentJob[]>([]);

  useEffect(() => {
    setRecentJobs(loadRecentJobs());
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("loading");
    setLoadingStep(1);
    setErrorMessage(null);
    setLastResult(null);

    let metadata: Record<string, unknown> | undefined;
    if (metadataText.trim()) {
      try {
        metadata = JSON.parse(metadataText);
      } catch {
        setStatus("error");
        setErrorMessage("Metadata must be valid JSON.");
        return;
      }
    }

    const stepTimer = setTimeout(() => setLoadingStep(2), 1200);

    const payload: IngestRequest = { url, source_type: sourceType, metadata };

    try {
      const result = await ingest(payload);
      clearTimeout(stepTimer);
      const job: RecentJob = {
        url,
        source_type: sourceType,
        status: "success",
        chunks_ingested: result.chunks_ingested,
        total_characters: result.total_characters,
        message: result.message,
        timestamp: new Date().toISOString(),
      };
      setRecentJobs(saveRecentJob(job));
      setLastResult(job);
      setStatus("success");
      setUrl("");
      setMetadataText("");
    } catch (err) {
      clearTimeout(stepTimer);
      const message =
        err instanceof ApiError ? err.message : "Something went wrong.";
      const job: RecentJob = {
        url,
        source_type: sourceType,
        status: "error",
        message,
        timestamp: new Date().toISOString(),
      };
      setRecentJobs(saveRecentJob(job));
      setStatus("error");
      setErrorMessage(message);
    }
  }

  const isLoading = status === "loading";

  return (
    <div>
      <h1 className={styles.title}>Ingest new source</h1>
      <p className={styles.subtitle}>
        Add a new data source to scrape, embed, and index.
      </p>

      <form className={styles.form} onSubmit={handleSubmit}>
        <div className={styles.formGrid}>
          <label className={`${styles.label} ${styles.labelUrl}`} htmlFor="url">
            Source URL
          </label>
          <label
            className={`${styles.label} ${styles.labelType}`}
            htmlFor="source_type"
          >
            Source type
          </label>

          <div className={`${styles.inputWrap} ${styles.inputUrl}`}>
            <LinkIcon className={styles.inputIcon} />
            <input
              id="url"
              className={styles.input}
              type="url"
              required
              placeholder="https://github.com/owner/repo"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={isLoading}
            />
          </div>

          <div className={`${styles.inputWrap} ${styles.inputType}`}>
            <DocumentIcon className={styles.inputIcon} />
            <select
              id="source_type"
              className={styles.select}
              value={sourceType}
              onChange={(e) =>
                setSourceType(e.target.value as "repo" | "pr")
              }
              disabled={isLoading}
            >
              <option value="repo">Git Repository</option>
              <option value="pr">Pull Request</option>
            </select>
          </div>

          <button
            type="submit"
            className={`${styles.submitBtn} ${styles.submit}`}
            disabled={isLoading}
          >
            <UploadIcon className={styles.submitIcon} />
            {isLoading ? "Submitting..." : "Submit"}
          </button>

          <p className={`${styles.hint} ${styles.hintUrl}`}>
            Enter the URL of the repo or pull request to ingest.
          </p>
          <p className={`${styles.hint} ${styles.hintType}`}>
            Select the type of source.
          </p>
        </div>

        <details className={styles.metadataDetails}>
          <summary>Metadata (optional JSON)</summary>
          <textarea
            className={styles.textarea}
            placeholder={'{"team": "auth"}'}
            value={metadataText}
            onChange={(e) => setMetadataText(e.target.value)}
            disabled={isLoading}
            rows={3}
          />
        </details>
      </form>


      {isLoading && (
        <div className={styles.steps}>
          <StepCard
            title="Scraping repository"
            subtitle="Fetching data from the source..."
            active={loadingStep === 1}
            done={loadingStep > 1}
          />
          <StepCard
            title="Embedding and indexing"
            subtitle="Generating embeddings and updating index..."
            active={loadingStep === 2}
            done={false}
          />
        </div>
      )}

      {status === "error" && errorMessage && (
        <div className={styles.errorBanner}>{errorMessage}</div>
      )}

      {status === "success" && lastResult && (
        <div className={styles.successBanner}>
          {lastResult.message} — {lastResult.chunks_ingested} chunks,{" "}
          {lastResult.total_characters} characters.
        </div>
      )}

      <div className={styles.jobsSection}>
        <h2 className={styles.jobsTitle}>Recent jobs</h2>

        {recentJobs.length === 0 ? (
          <p className={styles.emptyState}>
            No ingest jobs yet this session. Submit a source above to see it
            here.
          </p>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <colgroup>
                <col style={{ width: "28%" }} />
                <col style={{ width: "9%" }} />
                <col style={{ width: "11%" }} />
                <col style={{ width: "9%" }} />
                <col style={{ width: "11%" }} />
                <col style={{ width: "16%" }} />
                <col style={{ width: "16%" }} />
              </colgroup>
              <thead>
                <tr>
                  <th className={styles.left}>Source</th>
                  <th className={styles.center}>Type</th>
                  <th className={styles.center}>Status</th>
                  <th className={styles.center}>Chunks</th>
                  <th className={styles.center}>Characters</th>
                  <th className={styles.center}>Date</th>
                  <th className={styles.center}>Time</th>
                </tr>
              </thead>
              <tbody>
                {recentJobs.map((job, i) => (
                  <tr key={`${job.timestamp}-${i}`}>
                    <td
                      className={`${styles.mono} ${styles.truncate} ${styles.left}`}
                      title={job.url}
                    >
                      {formatSource(job.url)}
                    </td>
                    <td className={styles.center}>{job.source_type}</td>
                    <td className={styles.center}>
                      <span
                        className={`${styles.pill} ${
                          job.status === "success"
                            ? styles.pillSuccess
                            : styles.pillDanger
                        }`}
                      >
                        {job.status === "success" ? "Completed" : "Failed"}
                      </span>
                    </td>
                    <td className={styles.center}>
                      {job.chunks_ingested ?? "—"}
                    </td>
                    <td className={styles.center}>
                      {job.total_characters ?? "—"}
                    </td>
                    <td className={styles.center}>
                      {formatDate(job.timestamp)}
                    </td>
                    <td className={styles.center}>
                      {formatTime(job.timestamp)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function StepCard({
  title,
  subtitle,
  active,
  done,
}: {
  title: string;
  subtitle: string;
  active: boolean;
  done: boolean;
}) {
  return (
    <div className={styles.stepCard}>
      <div
        className={`${styles.stepIcon} ${active ? styles.stepIconSpin : ""}`}
      />
      <div className={styles.stepBody}>
        <div className={styles.stepTitle}>{title}</div>
        <div className={styles.stepSubtitle}>{subtitle}</div>
        <div className={styles.progressTrack}>
          <div
            className={`${styles.progressFill} ${
              active ? styles.progressFillActive : ""
            } ${done ? styles.progressFillDone : ""}`}
          />
        </div>
      </div>
      <span className={styles.stepStatus}>
        {done ? "Done" : active ? "In progress" : "Queued"}
      </span>
    </div>
  );
}
