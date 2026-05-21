import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function FleetPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["fleet"],
    queryFn: api.fleet,
  });
  if (isLoading) return <p className="text-sm text-zinc-500">Loading…</p>;
  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">Fleet</h2>
      {(data?.entries ?? []).map((entry) => (
        <Card key={entry.deployment_id}>
          <CardHeader>
            <CardTitle>{entry.deployment_id}</CardTitle>
            <div className="text-xs text-zinc-500">
              {entry.edition} · {entry.framework_version}
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-sm font-medium mb-1">Routines</div>
            <ul className="text-sm space-y-1">
              {entry.routines.map((routine) => (
                <li key={routine} className="font-mono text-xs">
                  {routine}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
