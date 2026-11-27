"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Card } from "@/lib/types";
import { cardTitle } from "@/lib/format";

interface Props {
  card: Card | null;
  left: number;
  estimateUsd: number;
  onClose: () => void;
  onQueued: (cardId: number, analysisId: number) => void;
}

export default function AnalysisSheet({ card, left, estimateUsd, onClose, onQueued }: Props) {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!card) return;
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`/api/cards/${card.id}/analysis`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: question.trim() || null }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.reason ?? "요청 실패");
      onQueued(card.id, j.id);
      setQuestion("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AnimatePresence>
      {card ? (
        <>
          <motion.div className="fixed inset-0 z-[60] bg-black/40" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          <motion.div
            className="fixed inset-x-0 bottom-0 z-[70] mx-auto max-w-md rounded-t-2xl bg-white p-5 pb-[max(env(safe-area-inset-bottom),20px)] shadow-2xl dark:bg-[#1f2023]"
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 320 }}
          >
            <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-gray-200 dark:bg-white/20" />
            <h2 className="text-lg font-bold">심화 분석</h2>
            <p className="mt-1 truncate text-sm text-gray-500">{cardTitle(card)}</p>
            <p className="mt-4 text-sm leading-relaxed text-gray-600 dark:text-gray-300">
              Claude로 분석해 Tana <b>#Research</b>에 저장합니다. 예상 비용 약 ${estimateUsd.toFixed(2)}. 오늘 남은 횟수 {left}회.
            </p>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={2}
              maxLength={500}
              placeholder="특히 궁금한 점 (선택). 예: 우리 서비스에 적용한다면?"
              className="mt-3 w-full resize-none rounded-xl border border-gray-200 bg-transparent px-3 py-2 text-sm dark:border-white/10"
            />
            {error ? <p className="mt-2 text-sm text-red-500">{error}</p> : null}
            <div className="mt-3 flex gap-3">
              <button onClick={onClose} className="flex-1 rounded-xl bg-gray-100 py-3 text-gray-500 dark:bg-white/10">
                취소
              </button>
              <button
                onClick={submit}
                disabled={busy || left <= 0}
                className="flex-1 rounded-xl bg-indigo-600 py-3 font-medium text-white disabled:opacity-40"
              >
                {left <= 0 ? "오늘 상한 도달" : busy ? "요청 중…" : "분석 요청"}
              </button>
            </div>
          </motion.div>
        </>
      ) : null}
    </AnimatePresence>
  );
}
