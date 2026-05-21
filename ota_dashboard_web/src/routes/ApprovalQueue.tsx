import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type ApprovalQueueItem } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useApprovalStream } from "@/lib/ws";

export function ApprovalQueuePage() {
  useApprovalStream();
  const { data, isLoading } = useQuery({
    queryKey: ["approvals"],
    queryFn: () => api.approvals.list(),
    refetchInterval: 5_000,
  });
  const items = data?.items ?? [];
  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">Approval Queue</h2>
      {isLoading && <p className="text-sm text-zinc-500">Loading…</p>}
      {!isLoading && items.length === 0 && (
        <p className="text-sm text-zinc-500">No pending approvals.</p>
      )}
      {items.map((item) => (
        <ApprovalCard key={item.id} item={item} />
      ))}
    </div>
  );
}

function ApprovalCard({ item }: { item: ApprovalQueueItem }) {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const decide = useMutation({
    mutationFn: ({
      action,
      edits,
    }: {
      action: "approve" | "reject" | "edit_and_approve" | "remember_and_approve";
      edits?: Record<string, unknown>;
    }) => api.approvals.decide(item.id, action, edits),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["approvals"] }),
  });
  const subject = (item.payload as { subject?: string }).subject ?? "";
  const body = (item.payload as { body?: string }).body ?? "";
  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <div className="space-y-1">
          <CardTitle>{item.summary || item.gate_id}</CardTitle>
          <div className="text-xs text-zinc-500">
            {item.routine_id} · {new Date(item.created_at).toLocaleString()}
          </div>
        </div>
        <Button size="sm" variant="ghost" onClick={() => setExpanded((e) => !e)}>
          {expanded ? "Hide" : "Show"}
        </Button>
      </CardHeader>
      {expanded && (
        <CardContent className="space-y-3">
          {subject && (
            <div>
              <div className="text-xs font-medium text-zinc-500">Subject</div>
              <div className="text-sm">{subject}</div>
            </div>
          )}
          {body && (
            <div>
              <div className="text-xs font-medium text-zinc-500">Body</div>
              <pre className="text-sm whitespace-pre-wrap bg-zinc-50 p-3 rounded-md border">
                {body}
              </pre>
            </div>
          )}
          <div className="flex gap-2 pt-2">
            <Button onClick={() => decide.mutate({ action: "approve" })}>
              Approve
            </Button>
            <Button
              variant="secondary"
              onClick={() => decide.mutate({ action: "remember_and_approve" })}
            >
              Approve &amp; remember
            </Button>
            <Button
              variant="outline"
              onClick={() =>
                decide.mutate({
                  action: "edit_and_approve",
                  edits: item.payload,
                })
              }
            >
              Edit &amp; approve
            </Button>
            <Button
              variant="destructive"
              onClick={() => decide.mutate({ action: "reject" })}
            >
              Reject
            </Button>
          </div>
        </CardContent>
      )}
    </Card>
  );
}
