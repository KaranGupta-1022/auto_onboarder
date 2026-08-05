"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, listPods, Pod } from "@/lib/api";
import styles from "./page.module.css";
import { RefreshIcon, BoxIcon, CheckIcon, GhostIcon } from "./icons";

type Status = "loading" | "success" | "error";

export default function ClusterPage() {
  const [status, setStatus] = useState<Status>("loading");
  const [pods, setPods] = useState<Pod[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (isRefresh: boolean) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setStatus("loading");
    }
    setErrorMessage(null);

    try {
      const result = await listPods();
      setPods(result.pods);
      setStatus("success");
    } catch (err) {
      setErrorMessage(
        err instanceof ApiError ? err.message : "Something went wrong."
      );
      setStatus("error");
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load(false);
  }, [load]);

  const injectedCount = pods.filter((pod) => pod.injected).length;
  const injectedPercent =
    pods.length > 0 ? Math.round((injectedCount / pods.length) * 100) : null;

  return (
    <div>
      <div className={styles.headerRow}>
        <div>
          <h1 className={styles.title}>Cluster</h1>
          <p className={styles.subtitle}>
            Pods labeled <span className={styles.mono}>ghostkube.io/service</span> and
            their webhook-injection status.
          </p>
        </div>
        <button
          type="button"
          className={styles.refreshBtn}
          onClick={() => load(true)}
          disabled={status === "loading" || refreshing}
        >
          <RefreshIcon
            className={`${styles.refreshIcon} ${refreshing ? styles.spin : ""}`}
          />
          Refresh
        </button>
      </div>

      {status === "loading" && <p className={styles.hintState}>Loading pods…</p>}

      {status === "error" && (
        <div className={styles.errorBanner}>{errorMessage}</div>
      )}

      {status === "success" && (
        <>
          <div className={styles.statsRow}>
            <div className={styles.statCard}>
              <BoxIcon className={styles.statIcon} />
              <div>
                <div className={styles.statValue}>{pods.length}</div>
                <div className={styles.statLabel}>Total pods</div>
              </div>
            </div>
            <div className={styles.statCard}>
              <GhostIcon className={`${styles.statIcon} ${styles.statIconAccent}`} />
              <div>
                <div className={styles.statValue}>
                  {injectedCount}
                  {injectedPercent !== null && (
                    <span className={styles.statPercent}>
                      {" "}
                      ({injectedPercent}%)
                    </span>
                  )}
                </div>
                <div className={styles.statLabel}>Injected</div>
              </div>
            </div>
          </div>

          {pods.length === 0 ? (
            <div className={styles.emptyState}>
              <p className={styles.emptyTitle}>No pods found</p>
              <p className={styles.emptyText}>
                Make sure a pod is labeled{" "}
                <span className={styles.mono}>ghostkube.io/service</span>, the
                mutating webhook is deployed, and the cluster is reachable
                from the Brain API (in-cluster config or a local kubeconfig).
              </p>
            </div>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Namespace</th>
                    <th>Service</th>
                    <th>Injected</th>
                  </tr>
                </thead>
                <tbody>
                  {pods.map((pod) => (
                    <tr key={`${pod.namespace}/${pod.name}`}>
                      <td className={styles.mono}>{pod.name}</td>
                      <td>{pod.namespace}</td>
                      <td className={styles.mono}>{pod.service_label}</td>
                      <td>
                        {pod.injected ? (
                          <span
                            className={`${styles.pill} ${styles.pillInjected}`}
                            title={pod.ghost_note_id ?? undefined}
                          >
                            <CheckIcon className={styles.pillIcon} />
                            Injected
                          </span>
                        ) : (
                          <span
                            className={`${styles.pill} ${styles.pillNotInjected}`}
                          >
                            Not injected
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
