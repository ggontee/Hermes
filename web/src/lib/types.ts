export type Kind = "short" | "long" | "video";
export type Field = "AI" | "Tech" | "Bio";
export type CardStatus = "pending" | "kept" | "discarded";

export interface Section {
  t: number;
  title: string;
  summary: string;
}

export interface TranslationPair {
  id: string;
  orig: string;
  ko: string;
}

export interface TranscriptLine {
  t: number | null;
  orig: string;
  ko: string;
}

/** 묶음에 딸린 항목: 작성자 한마디(note) 또는 다른 형식(alt) */
export interface Attachment {
  role: "note" | "alt";
  platform: string;
  url: string;
  text: string;
}

export interface Card {
  id: number;
  kind: Kind;
  status: CardStatus;
  person: string;
  affiliation: string | null;
  field: Field;
  sourceType: string;
  url: string;
  publishedAt: string;
  titleOrig: string;
  paragraphs: string[];
  media: string[];
  // short
  translationKo: string | null;
  quoteTranslationKo: string | null;
  // long
  titleKo: string | null;
  summaryKo: string[];
  soWhat: string | null;
  tags: string[];
  userTags: string[];
  isPreview: boolean;
  translationPairs: TranslationPair[];
  // video
  videoId: string | null;
  oneliner: string | null;
  sections: Section[];
  top3: number[];
  transcript: TranscriptLine[];
  fromDescription: boolean;
  // 사용자
  userComment: string | null;
  decidedAt: string | null;
  attachments: Attachment[];
  analysis: AnalysisSummary | null;
}

export interface AnalysisSummary {
  id: number;
  status: "queued" | "running" | "done" | "failed";
  title: string | null;
  tanaNodeId: string | null;
  createdAt: string;
}

export interface Analysis extends AnalysisSummary {
  cardId: number;
  question: string | null;
  contentMd: string | null;
  error: string | null;
  costUsd: number;
  finishedAt: string | null;
}

export interface StatusInfo {
  lastRun: {
    startedAt: string;
    finishedAt: string | null;
    newItems: number;
    processed: number;
    deferred: number;
    errors: number;
  } | null;
  usage: { aiItems: number; videos: number; analyses: number; costUsd: number };
  limits: { aiItems: number; videos: number; analyses: number };
  sourceErrors: { person: string; type: string; error: string; lastSuccessAt: string | null }[];
  nextRun: string;
  pendingCount: number;
}
