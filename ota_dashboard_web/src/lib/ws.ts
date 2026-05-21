// WebSocket subscription helpers for live approval-queue updates.
//
// `useApprovalStream` opens a WebSocket against `/api/v1/approvals/stream`
// and invalidates the TanStack Query cache when a new approval arrives.

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";

export function useApprovalStream() {
  const queryClient = useQueryClient();
  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.host}/api/v1/approvals/stream`;
    let socket: WebSocket | null = null;
    let cancelled = false;

    function connect() {
      if (cancelled) return;
      socket = new WebSocket(url);
      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg?.event === "approval.new") {
            queryClient.invalidateQueries({ queryKey: ["approvals"] });
          }
        } catch {
          // ignore malformed payloads
        }
      };
      socket.onclose = () => {
        if (!cancelled) setTimeout(connect, 2000);
      };
    }
    connect();

    return () => {
      cancelled = true;
      socket?.close();
    };
  }, [queryClient]);
}
