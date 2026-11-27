"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useRouter } from "next/navigation";
import type { Card } from "@/lib/types";
import { patchCard } from "@/lib/client";
import SwipeCard from "./SwipeCard";
import CommentModal from "./CommentModal";

interface Props {
  initialCards: Card[];
  total: number;
  nextRun: string;
}

interface Undo {
  card: Card;
  action: "kept" | "discarded";
}

const UNDO_MS = 5000;

export default function CardStack({ initialCards, total, nextRun }: Props) {
  const router = useRouter();
  const [cards, setCards] = useState(initialCards);
  const [commentTarget, setCommentTarget] = useState<Card | null>(null);
  const [undo, setUndo] = useState<Undo | null>(null);
  const [done, setDone] = useState(0);
  const exitDirectionRef = useRef<"left" | "right" | null>(null);
  const undoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => setCards(initialCards), [initialCards]);

  const decide = useCallback((card: Card, status: "kept" | "discarded", comment?: string) => {
    setCards((cs) => cs.filter((c) => c.id !== card.id));
    setDone((n) => n + 1);
    setUndo({ card, action: status });
    if (undoTimer.current) clearTimeout(undoTimer.current);
    undoTimer.current = setTimeout(() => setUndo(null), UNDO_MS);
    patchCard(card.id, { status, comment: comment || null });
  }, []);

  const handleSwipe = useCallback(
    (direction: "left" | "right") => {
      const current = cards[0];
      if (!current || commentTarget) return;
      exitDirectionRef.current = direction;
      if (direction === "left") decide(current, "discarded");
      else setCommentTarget(current);
    },
    [cards, commentTarget, decide],
  );

  const handleUndo = useCallback(() => {
    if (!undo) return;
    if (undoTimer.current) clearTimeout(undoTimer.current);
    exitDirectionRef.current = null;
    setCards((cs) => [{ ...undo.card, status: "pending" }, ...cs]);
    setDone((n) => Math.max(0, n - 1));
    patchCard(undo.card.id, { status: "pending" });
    setUndo(null);
  }, [undo]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (commentTarget || (e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "ArrowLeft") handleSwipe("left");
      if (e.key === "ArrowRight") handleSwipe("right");
      if (e.key === "z" && (e.metaKey || e.ctrlKey)) handleUndo();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleSwipe, handleUndo, commentTarget]);

  const remaining = Math.max(0, total - done);

  return (
    <>
      {cards.length === 0 ? (
        <div className="flex h-[60dvh] flex-col items-center justify-center gap-3 text-center">
          <div className="text-5xl">✨</div>
          <h2 className="text-xl font-bold">새 카드가 없습니다</h2>
          <p className="text-gray-500">
            {done > 0 ? `${done}장을 정리했어요. ` : ""}다음 수집: {nextRun}
          </p>
        </div>
      ) : (
        <div className="flex w-full flex-col items-center gap-4">
          <div className="flex w-full items-center gap-3">
            <div className="h-1.5 flex-1 rounded-full bg-gray-200 dark:bg-white/10">
              <div
                className="h-1.5 rounded-full bg-indigo-500 transition-all duration-300"
                style={{ width: `${total ? (done / total) * 100 : 0}%` }}
              />
            </div>
            <span className="whitespace-nowrap text-sm text-gray-500">{remaining}장 남음</span>
          </div>

          <div className="relative h-[calc(100dvh-330px)] max-h-[600px] min-h-[340px] w-full">
            <AnimatePresence>
              {cards.slice(0, 2).map((card, i) => (
                <SwipeCard
                  key={card.id}
                  card={card}
                  isTop={i === 0}
                  disabled={!!commentTarget}
                  exitDirectionRef={exitDirectionRef}
                  onSwipe={handleSwipe}
                  onOpen={() => router.push(`/card/${card.id}`)}
                />
              ))}
            </AnimatePresence>
          </div>

          <div className="flex items-center gap-8">
            <button
              onClick={() => handleSwipe("left")}
              disabled={!!commentTarget}
              className="flex h-14 w-14 items-center justify-center rounded-full border-2 border-red-400 bg-white text-xl text-red-500 shadow-md transition-all active:scale-95 disabled:opacity-40 dark:bg-transparent"
              aria-label="버리기"
            >
              ✕
            </button>
            <button
              onClick={() => handleSwipe("right")}
              disabled={!!commentTarget}
              className="flex h-14 w-14 items-center justify-center rounded-full border-2 border-emerald-400 bg-white text-xl text-emerald-500 shadow-md transition-all active:scale-95 disabled:opacity-40 dark:bg-transparent"
              aria-label="보관"
            >
              ♥
            </button>
          </div>
        </div>
      )}

      <AnimatePresence>
        {undo ? (
          <motion.div
            className="fixed inset-x-0 bottom-20 z-40 flex justify-center px-4"
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 20, opacity: 0 }}
          >
            <div className="flex items-center gap-4 rounded-full bg-gray-900 px-4 py-2.5 text-sm text-white shadow-lg dark:bg-gray-100 dark:text-gray-900">
              <span>{undo.action === "kept" ? "보관했어요" : "버렸어요"}</span>
              <button onClick={handleUndo} className="font-semibold text-indigo-300 dark:text-indigo-600">
                되돌리기
              </button>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <CommentModal
        card={commentTarget}
        isOpen={!!commentTarget}
        onConfirm={(comment) => {
          if (!commentTarget) return;
          exitDirectionRef.current = "right";
          decide(commentTarget, "kept", comment);
          setCommentTarget(null);
        }}
        onCancel={() => setCommentTarget(null)}
      />
    </>
  );
}
