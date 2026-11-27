import Database from "better-sqlite3";
import path from "node:path";
import type { Analysis, AnalysisSummary, Attachment, Card, CardStatus, StatusInfo } from "./types";

// 저장소는 hermes.db 하나. 파이프라인(pipeline/db.py)이 스키마를 만든다.
// 웹앱은 카드 상태·코멘트·태그와 심화 분석 요청만 쓴다.
const DB_PATH = process.env.HERMES_DB_PATH ?? path.resolve(process.cwd(), "..", "data", "hermes.db");

let db: Database.Database | null = null;

export function getDb(): Database.Database {
  if (!db) {
    db = new Database(DB_PATH, { fileMustExist: true });
    db.pragma("journal_mode = WAL");
    db.pragma("busy_timeout = 30000");
    db.pragma("foreign_keys = ON");
  }
  return db;
}

const j = <T>(s: string | null | undefined, fallback: T): T => {
  if (!s) return fallback;
  try {
    return JSON.parse(s) as T;
  } catch {
    return fallback;
  }
};

const CARD_SELECT = `
SELECT c.*, i.url, i.published_at, i.title_orig, i.paragraphs_json, i.media_json, i.external_id,
       i.group_id, p.name AS person, p.affiliation, p.field, s.type AS source_type,
       (SELECT a.id FROM analyses a WHERE a.card_id = c.id ORDER BY a.id DESC LIMIT 1) AS analysis_id
FROM cards c
JOIN items i ON i.id = c.item_id
JOIN people p ON p.id = i.person_id
JOIN sources s ON s.id = i.source_id
`;

type Row = Record<string, unknown>;

function youtubeId(url: string, externalId: string, sourceType: string): string | null {
  if (sourceType === "youtube" && /^[\w-]{11}$/.test(externalId)) return externalId;
  const m = url.match(/[?&]v=([\w-]{11})/) ?? url.match(/youtu\.be\/([\w-]{11})/);
  return m ? m[1] : null;
}

function attachments(groupId: number, itemId: number): Attachment[] {
  const rows = getDb()
    .prepare(
      `SELECT role, platform, url, paragraphs_json FROM items
       WHERE group_id = ? AND id != ? AND role IN ('note', 'alt') ORDER BY published_at`,
    )
    .all(groupId, itemId) as Row[];
  return rows.map((r) => ({
    role: r.role as "note" | "alt",
    platform: r.platform as string,
    url: r.url as string,
    text: j<string[]>(r.paragraphs_json as string, []).join("\n\n"),
  }));
}

function analysisSummary(id: number | null): AnalysisSummary | null {
  if (!id) return null;
  const r = getDb().prepare("SELECT id, status, title, tana_node_id, created_at FROM analyses WHERE id = ?").get(id) as
    | Row
    | undefined;
  if (!r) return null;
  return {
    id: r.id as number,
    status: r.status as AnalysisSummary["status"],
    title: (r.title as string) ?? null,
    tanaNodeId: (r.tana_node_id as string) ?? null,
    createdAt: r.created_at as string,
  };
}

function toCard(r: Row): Card {
  const sourceType = r.source_type as string;
  return {
    id: r.id as number,
    kind: r.kind as Card["kind"],
    status: r.status as CardStatus,
    person: r.person as string,
    affiliation: (r.affiliation as string) ?? null,
    field: r.field as Card["field"],
    sourceType,
    url: r.url as string,
    publishedAt: r.published_at as string,
    titleOrig: (r.title_orig as string) ?? "",
    paragraphs: j<string[]>(r.paragraphs_json as string, []),
    media: j<string[]>(r.media_json as string, []),
    translationKo: (r.translation_ko as string) ?? null,
    quoteTranslationKo: (r.quote_translation_ko as string) ?? null,
    titleKo: (r.title_ko as string) ?? null,
    summaryKo: j<string[]>(r.summary_ko_json as string, []),
    soWhat: (r.so_what as string) ?? null,
    tags: j<string[]>(r.tags_json as string, []),
    userTags: j<string[]>(r.user_tags_json as string, []),
    isPreview: Boolean(r.is_preview),
    translationPairs: j(r.translation_pairs_json as string, []),
    videoId: r.kind === "video" ? youtubeId(r.url as string, r.external_id as string, sourceType) : null,
    oneliner: (r.video_oneliner as string) ?? null,
    sections: j(r.video_sections_json as string, []),
    top3: j<number[]>(r.video_top3_json as string, []),
    transcript: j(r.transcript_ko as string, []),
    fromDescription: Boolean(r.from_description),
    userComment: (r.user_comment as string) ?? null,
    decidedAt: (r.decided_at as string) ?? null,
    attachments: attachments(r.group_id as number, r.item_id as number),
    analysis: analysisSummary((r.analysis_id as number) ?? null),
  };
}

export interface FeedFilter {
  field?: string;
  kind?: string;
  person?: string;
}

export function pendingCards(filter: FeedFilter = {}, limit = 50): Card[] {
  const where = ["c.status = 'pending'"];
  const args: unknown[] = [];
  if (filter.field && filter.field !== "all") {
    where.push("p.field = ?");
    args.push(filter.field);
  }
  if (filter.kind && filter.kind !== "all") {
    where.push("c.kind = ?");
    args.push(filter.kind);
  }
  if (filter.person) {
    where.push("p.name = ?");
    args.push(filter.person);
  }
  const rows = getDb()
    .prepare(`${CARD_SELECT} WHERE ${where.join(" AND ")} ORDER BY i.published_at DESC LIMIT ?`)
    .all(...args, limit) as Row[];
  return rows.map(toCard);
}

export function pendingCount(): number {
  return (getDb().prepare("SELECT COUNT(*) AS n FROM cards WHERE status = 'pending'").get() as { n: number }).n;
}

export function keptCards(filter: { tag?: string; analyzed?: boolean } = {}): Card[] {
  const rows = getDb()
    .prepare(`${CARD_SELECT} WHERE c.status = 'kept' ORDER BY c.decided_at DESC LIMIT 500`)
    .all() as Row[];
  let cards = rows.map(toCard);
  if (filter.tag) cards = cards.filter((c) => [...c.tags, ...c.userTags].includes(filter.tag!));
  if (filter.analyzed) cards = cards.filter((c) => c.analysis?.status === "done");
  return cards;
}

export function getCard(id: number): Card | null {
  const r = getDb().prepare(`${CARD_SELECT} WHERE c.id = ?`).get(id) as Row | undefined;
  return r ? toCard(r) : null;
}

export function people(): string[] {
  return (getDb().prepare("SELECT name FROM people ORDER BY name").all() as { name: string }[]).map((r) => r.name);
}

export function setStatus(id: number, status: CardStatus, comment?: string | null): boolean {
  const res = getDb()
    .prepare(
      `UPDATE cards SET status = ?, decided_at = CASE WHEN ? = 'pending' THEN NULL ELSE datetime('now') END,
       user_comment = COALESCE(?, user_comment) WHERE id = ?`,
    )
    .run(status, status, comment ?? null, id);
  return res.changes > 0;
}

export function updateKept(id: number, patch: { comment?: string | null; userTags?: string[] }): boolean {
  const d = getDb();
  let changed = 0;
  if (patch.comment !== undefined) {
    changed += d.prepare("UPDATE cards SET user_comment = ? WHERE id = ?").run(patch.comment, id).changes;
  }
  if (patch.userTags !== undefined) {
    const tags = patch.userTags.map((t) => t.trim().replace(/^#/, "")).filter(Boolean).slice(0, 10);
    changed += d.prepare("UPDATE cards SET user_tags_json = ? WHERE id = ?").run(JSON.stringify(tags), id).changes;
  }
  return changed > 0;
}

// ── 상한과 상태 ──

const TZ = "Asia/Seoul";
const LIMITS = {
  aiItems: Number(process.env.HERMES_LIMIT_AI_ITEMS ?? 60),
  videos: Number(process.env.HERMES_LIMIT_VIDEOS ?? 10),
  analyses: Number(process.env.HERMES_LIMIT_ANALYSES ?? 5),
};
const SCHEDULE_HOURS = [6, 14, 22];

export function seoulDate(d = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
}

export function nextRunLabel(now = new Date()): string {
  const hour = Number(new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "2-digit", hour12: false }).format(now));
  const next = SCHEDULE_HOURS.find((h) => h > hour) ?? SCHEDULE_HOURS[0];
  return `${String(next).padStart(2, "0")}:00`;
}

function usageCount(kind: string): { count: number; cost: number } {
  const r = getDb().prepare("SELECT count, cost_usd FROM usage WHERE date = ? AND kind = ?").get(seoulDate(), kind) as
    | { count: number; cost_usd: number }
    | undefined;
  return { count: r?.count ?? 0, cost: r?.cost_usd ?? 0 };
}

export function analysesLeft(): number {
  return Math.max(0, LIMITS.analyses - usageCount("analyses").count - queuedAnalyses());
}

function queuedAnalyses(): number {
  return (
    getDb().prepare("SELECT COUNT(*) AS n FROM analyses WHERE status IN ('queued', 'running')").get() as { n: number }
  ).n;
}

export function statusInfo(): StatusInfo {
  const d = getDb();
  const run = d.prepare("SELECT * FROM runs ORDER BY id DESC LIMIT 1").get() as Row | undefined;
  const ai = usageCount("ai_items");
  const vid = usageCount("videos");
  const an = usageCount("analyses");
  const errors = d
    .prepare(
      `SELECT p.name AS person, s.type, s.last_error, s.last_success_at FROM sources s
       JOIN people p ON p.id = s.person_id WHERE s.enabled = 1 AND s.last_error IS NOT NULL ORDER BY p.name`,
    )
    .all() as Row[];
  return {
    lastRun: run
      ? {
          startedAt: run.started_at as string,
          finishedAt: (run.finished_at as string) ?? null,
          newItems: run.new_items as number,
          processed: run.processed as number,
          deferred: run.deferred_by_cap as number,
          errors: j<unknown[]>(run.errors_json as string, []).length,
        }
      : null,
    usage: { aiItems: ai.count, videos: vid.count, analyses: an.count, costUsd: ai.cost + vid.cost + an.cost },
    limits: LIMITS,
    sourceErrors: errors.map((e) => ({
      person: e.person as string,
      type: e.type as string,
      error: e.last_error as string,
      lastSuccessAt: (e.last_success_at as string) ?? null,
    })),
    nextRun: nextRunLabel(),
    pendingCount: pendingCount(),
  };
}

// ── 심화 분석 ──

export function queueAnalysis(cardId: number, question: string | null): { ok: true; id: number } | { ok: false; reason: string } {
  const card = getDb().prepare("SELECT status FROM cards WHERE id = ?").get(cardId) as { status: string } | undefined;
  if (!card) return { ok: false, reason: "카드가 없습니다." };
  if (card.status !== "kept") return { ok: false, reason: "보관한 카드만 분석할 수 있습니다." };
  if (analysesLeft() <= 0) return { ok: false, reason: "오늘 심화 분석 상한에 닿았습니다." };
  const res = getDb()
    .prepare("INSERT INTO analyses(card_id, question, status, created_at) VALUES (?, ?, 'queued', datetime('now'))")
    .run(cardId, question?.trim() || null);
  return { ok: true, id: Number(res.lastInsertRowid) };
}

export function getAnalysis(id: number): Analysis | null {
  const r = getDb().prepare("SELECT * FROM analyses WHERE id = ?").get(id) as Row | undefined;
  if (!r) return null;
  return {
    id: r.id as number,
    cardId: r.card_id as number,
    status: r.status as Analysis["status"],
    title: (r.title as string) ?? null,
    tanaNodeId: (r.tana_node_id as string) ?? null,
    createdAt: r.created_at as string,
    question: (r.question as string) ?? null,
    contentMd: (r.content_md as string) ?? null,
    error: (r.error as string) ?? null,
    costUsd: (r.cost_usd as number) ?? 0,
    finishedAt: (r.finished_at as string) ?? null,
  };
}
