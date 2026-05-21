import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const SEVERITY_STYLES = {
  info: "bg-blue-50 border-blue-200 text-blue-900",
  warn: "bg-amber-50 border-amber-200 text-amber-900",
  error: "bg-red-50 border-red-200 text-red-900",
  critical: "bg-red-100 border-red-300 text-red-950",
} as const;

export function CriticalBanner() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["banner"],
    queryFn: api.banner.get,
    refetchInterval: 10_000,
  });
  const clear = useMutation({
    mutationFn: api.banner.clear,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["banner"] }),
  });
  if (!data?.active) return null;
  const severity = data.severity ?? "warn";
  return (
    <div className={cn("border-b px-6 py-2 flex items-center gap-3", SEVERITY_STYLES[severity])}>
      <span className="text-xs font-semibold uppercase tracking-wide">
        {severity}
      </span>
      <span className="text-sm flex-1">
        <strong>{data.title}</strong>
        {data.description ? ` — ${data.description}` : ""}
      </span>
      <Button size="sm" variant="ghost" onClick={() => clear.mutate()}>
        Dismiss
      </Button>
    </div>
  );
}
