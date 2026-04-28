import { useState, useCallback } from "react";
import { getAuthHeader } from "../lib/auth";
import { getApiBaseUrl } from "./utils";

export type FileDiffEntry = {
  status: string; // "A" | "M" | "D"
  path: string;
};

export type PreviewRestoreResponse = {
  checkpointId: number;
  files: FileDiffEntry[];
};

/**
 * Fetch a preview of file changes for a checkpoint restore at a given turn.
 * Returns { preview, isLoading, error, fetchPreview }.
 */
export function useCheckpointPreview() {
  const [preview, setPreview] = useState<PreviewRestoreResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPreview = useCallback(
    async (sessionId: string, turnIndex: number) => {
      setIsLoading(true);
      setError(null);
      try {
        const basePath = getApiBaseUrl();
        const response = await fetch(
          `${basePath}/api/sessions/${encodeURIComponent(
            sessionId,
          )}/turns/${encodeURIComponent(turnIndex)}/checkpoint-preview`,
          { headers: getAuthHeader() },
        );

        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.detail || "Failed to fetch checkpoint preview");
        }

        const data = await response.json();
        const result: PreviewRestoreResponse = {
          checkpointId: data.checkpoint_id,
          files: (data.files ?? []).map(
            (f: Record<string, unknown>) => ({
              status: f.status as string,
              path: f.path as string,
            }),
          ),
        };
        setPreview(result);
        return result;
      } catch (err) {
        const message =
          err instanceof Error
            ? err.message
            : "Failed to fetch checkpoint preview";
        setError(message);
        setPreview(null);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  return { preview, isLoading, error, fetchPreview };
}

/**
 * Rewind a session to a specific turn.
 * Returns { rewind, isLoading, error }.
 */
export function useRewindCheckpoint() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const rewind = useCallback(
    async (
      sessionId: string,
      turnIndex: number,
      restoreFiles: boolean,
    ) => {
      setIsLoading(true);
      setError(null);
      try {
        const basePath = getApiBaseUrl();
        const response = await fetch(
          `${basePath}/api/sessions/${encodeURIComponent(sessionId)}/rewind`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...getAuthHeader(),
            },
            body: JSON.stringify({
              turn_index: turnIndex,
              restore_files: restoreFiles,
            }),
          },
        );

        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.detail || "Failed to rewind session");
        }

        return await response.json();
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to rewind session";
        setError(message);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  return { rewind, isLoading, error };
}
