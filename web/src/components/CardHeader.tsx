import type { Card } from "@/lib/types";
import { KIND_BADGE, KIND_LABEL, relativeTime } from "@/lib/format";

export default function CardHeader({ card }: { card: Card }) {
  const channels = card.attachments.filter((a) => a.role === "alt").length;
  return (
    <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
      <span className={`shrink-0 rounded-md px-1.5 py-0.5 font-semibold ${KIND_BADGE[card.kind]}`}>
        {KIND_LABEL[card.kind]}
      </span>
      <span className="min-w-0 truncate">
        <span className="text-gray-400">{card.field}</span> ·{" "}
        <span className="font-medium text-gray-700 dark:text-gray-200">{card.person}</span>
        {card.affiliation ? <span> · {card.affiliation}</span> : null}
      </span>
      <span className="ml-auto shrink-0 text-gray-400">
        {channels > 0 ? <span className="mr-1.5 rounded bg-gray-100 px-1 dark:bg-white/10">+{channels} 채널</span> : null}
        {relativeTime(card.publishedAt)}
      </span>
    </div>
  );
}
