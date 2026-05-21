import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export function WhyPage() {
  const params = useParams();
  const [emailId, setEmailId] = useState(params.emailId ?? "");
  const [query, setQuery] = useState(params.emailId ?? "");
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["why", query],
    queryFn: () => api.why(query),
    enabled: Boolean(query),
  });
  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">/why</h2>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(emailId);
        }}
      >
        <Input
          placeholder="email_id (Gmail message id)…"
          value={emailId}
          onChange={(e) => setEmailId(e.target.value)}
        />
        <Button type="submit">Look up</Button>
      </form>
      {isLoading && <p className="text-sm text-zinc-500">Loading…</p>}
      {isError && (
        <p className="text-sm text-red-600">
          {(error as Error).message}
        </p>
      )}
      {data && data.entries.length === 0 && (
        <p className="text-sm text-zinc-500">No decisions on file for this email_id.</p>
      )}
      {data?.entries.map((entry, idx) => (
        <Card key={idx}>
          <CardHeader>
            <CardTitle className="font-mono text-xs">{entry.kind}</CardTitle>
            <div className="text-xs text-zinc-500">
              {new Date(entry.timestamp).toLocaleString()}
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-sm mb-2">{entry.description}</p>
            <pre className="text-xs bg-zinc-50 p-2 rounded-md border overflow-x-auto">
              {JSON.stringify(entry.payload, null, 2)}
            </pre>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
