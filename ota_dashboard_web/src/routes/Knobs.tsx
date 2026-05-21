import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const ROUTINE_ID = "ota.email-triage";

export function KnobsPage() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["knobs", ROUTINE_ID],
    queryFn: () => api.knobs.get(ROUTINE_ID),
  });
  const [edits, setEdits] = useState<Record<string, string>>({});
  const update = useMutation({
    mutationFn: (knobs: Record<string, unknown>) =>
      api.knobs.update(ROUTINE_ID, knobs),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["knobs", ROUTINE_ID] });
      setEdits({});
    },
  });
  if (isLoading) return <p className="text-sm text-zinc-500">Loading…</p>;
  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">Knobs — {ROUTINE_ID}</h2>
      <Card>
        <CardHeader>
          <CardTitle>Routine config</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {(data?.knobs ?? []).map((knob) => (
            <div key={knob.name} className="grid grid-cols-3 gap-3 items-center">
              <label className="text-sm font-medium">{knob.name}</label>
              <Input
                className="col-span-2"
                value={edits[knob.name] ?? String(knob.value ?? "")}
                onChange={(e) =>
                  setEdits((current) => ({ ...current, [knob.name]: e.target.value }))
                }
              />
            </div>
          ))}
          <Button
            disabled={Object.keys(edits).length === 0 || update.isPending}
            onClick={() => update.mutate(edits)}
          >
            {update.isPending ? "Saving…" : "Save changes"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
