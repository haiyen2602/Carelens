import { AlertCircle } from "lucide-react";

export function ChatError({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div className="flex items-center gap-3 rounded-lg bg-destructive/10 p-4">
      <AlertCircle className="h-5 w-5 shrink-0 text-destructive" />
      <p className="flex-1 text-sm text-destructive">{error}</p>
      <button onClick={onRetry} className="text-sm text-destructive underline hover:no-underline">
        Thử lại
      </button>
    </div>
  );
}
