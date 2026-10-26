"use client";

import { TriangleAlert } from "lucide-react";
import { ApiError } from "@/lib/api";

export function ErrorNotice({
  error,
  compact = false,
}: {
  error: Error;
  compact?: boolean;
}) {
  return (
    <div className={`error-notice ${compact ? "compact" : ""}`} role="alert">
      <TriangleAlert size={18} />
      <div>
        <strong>
          {error instanceof ApiError
            ? error.code.replaceAll("_", " ")
            : "Request failed"}
        </strong>
        <p>{error.message}</p>
        {error instanceof ApiError && error.requestId && (
          <small>Request {error.requestId}</small>
        )}
      </div>
    </div>
  );
}
