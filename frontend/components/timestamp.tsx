import { formatDateTime } from "@/lib/utils";

export function Timestamp({ value }: { value: string }) {
  return (
    <time dateTime={value} className="text-sm text-ink-200">
      {formatDateTime(value)}
    </time>
  );
}
