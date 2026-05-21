import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export function AuditLogPage() {
  const [q, setQ] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["audit", q],
    queryFn: () => api.audit.scan(q || undefined),
  });
  const events = data?.events ?? [];
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Audit Log</h2>
        <a
          href={`/api/v1/audit.csv${q ? `?q=${encodeURIComponent(q)}` : ""}`}
          className="inline-block"
        >
          <Button variant="outline" size="sm">
            Export CSV
          </Button>
        </a>
      </div>
      <Input
        placeholder="Search payload, event_type, routine_run_id..."
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {isLoading && <p className="text-sm text-zinc-500">Loading…</p>}
      <Card>
        <CardHeader>
          <CardTitle>{events.length} events</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="text-xs text-zinc-500 bg-zinc-50">
              <tr>
                <th className="text-left p-2">Time</th>
                <th className="text-left p-2">Event</th>
                <th className="text-left p-2">Severity</th>
                <th className="text-left p-2">Trace</th>
                <th className="text-left p-2">Run</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.event_id} className="border-t hover:bg-zinc-50">
                  <td className="p-2 text-zinc-500">
                    {new Date(event.timestamp).toLocaleTimeString()}
                  </td>
                  <td className="p-2 font-mono">{event.event_type}</td>
                  <td className="p-2">
                    <span
                      className={
                        event.severity === "error" || event.severity === "critical"
                          ? "text-red-600"
                          : event.severity === "warn"
                            ? "text-amber-600"
                            : "text-zinc-600"
                      }
                    >
                      {event.severity}
                    </span>
                  </td>
                  <td className="p-2 font-mono text-xs">
                    {event.trace_id ? (
                      <Link
                        to={`/audit?trace=${event.trace_id}`}
                        className="text-blue-600 hover:underline"
                      >
                        {event.trace_id.slice(0, 8)}…
                      </Link>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="p-2 font-mono text-xs">
                    {event.routine_run_id ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
