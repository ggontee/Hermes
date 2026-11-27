// SQLite datetime('now')는 'YYYY-MM-DD HH:MM:SS'(UTC, Z 없음)로 남는다.
export function parseDate(s: string | null | undefined): Date | null {
  if (!s) return null;
  const iso = /[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : `${s.replace(" ", "T")}Z`;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

const TZ = "Asia/Seoul";

export function relativeTime(s: string | null | undefined, now = new Date()): string {
  const d = parseDate(s);
  if (!d) return "";
  const min = Math.floor((now.getTime() - d.getTime()) / 60000);
  if (min < 1) return "방금";
  if (min < 60) return `${min}분 전`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}시간 전`;
  return new Intl.DateTimeFormat("ko-KR", { timeZone: TZ, month: "short", day: "numeric" }).format(d);
}

export function dateTime(s: string | null | undefined): string {
  const d = parseDate(s);
  if (!d) return "-";
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: TZ,
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
}

export function clock(sec: number | null | undefined): string {
  if (sec == null || sec < 0) return "";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  const mm = String(m).padStart(h ? 2 : 1, "0");
  return h ? `${h}:${mm}:${String(s).padStart(2, "0")}` : `${mm}:${String(s).padStart(2, "0")}`;
}

export const KIND_LABEL = { short: "SNS", long: "글", video: "영상" } as const;

export const KIND_BADGE = {
  short: "bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-300",
  long: "bg-violet-100 text-violet-700 dark:bg-violet-900/50 dark:text-violet-300",
  video: "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300",
} as const;

/** 보관함 목록 등에 쓰는 한 줄 제목 */
export function cardTitle(c: { kind: string; titleKo: string | null; titleOrig: string; translationKo: string | null; oneliner: string | null; paragraphs: string[] }): string {
  if (c.kind === "short") return (c.translationKo ?? c.paragraphs[0] ?? "").split("\n")[0].slice(0, 120);
  return c.titleKo || c.titleOrig || c.oneliner || "(제목 없음)";
}
