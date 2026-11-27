"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Card } from "@/lib/types";
import { cardTitle } from "@/lib/format";

interface Props {
  card: Card | null;
  isOpen: boolean;
  initial?: string;
  confirmLabel?: [string, string];
  onConfirm: (comment: string) => void;
  onCancel: () => void;
}

// Mnemo CommentModal을 옮겼다.
export default function CommentModal({ card, isOpen, initial = "", confirmLabel, onConfirm, onCancel }: Props) {
  const [comment, setComment] = useState(initial);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (isOpen) {
      setComment(initial);
      const t = setTimeout(() => ref.current?.focus(), 300);
      return () => clearTimeout(t);
    }
  }, [isOpen, initial]);

  const confirm = () => onConfirm(comment.trim());
  const [withText, without] = confirmLabel ?? ["메모와 함께 보관", "바로 보관"];

  return (
    <AnimatePresence>
      {isOpen && card ? (
        <>
          <motion.div
            className="fixed inset-0 z-[60] bg-black/40"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onCancel}
          />
          <motion.div
            className="fixed inset-0 z-[70] flex items-center justify-center px-5"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onCancel}
          >
            <motion.div
              className="w-full max-w-sm overflow-hidden rounded-2xl bg-white p-5 shadow-2xl dark:bg-[#1f2023]"
              initial={{ scale: 0.85, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.85, opacity: 0 }}
              transition={{ type: "spring", damping: 25, stiffness: 350 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="mb-4 flex items-start gap-3 rounded-xl bg-emerald-50 p-3 dark:bg-emerald-900/20">
                <span className="mt-0.5 text-xl text-emerald-500">♥</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold text-gray-900 dark:text-gray-100">{cardTitle(card)}</p>
                  <p className="mt-0.5 text-sm text-gray-500">{card.person}</p>
                </div>
              </div>
              <label className="mb-2 block text-sm font-medium text-gray-500">한 줄 코멘트 (선택)</label>
              <textarea
                ref={ref}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    confirm();
                  }
                }}
                placeholder="왜 남겨 두는지, 어디에 쓸지..."
                className="w-full resize-none rounded-xl border border-gray-200 bg-transparent px-4 py-3 text-base text-gray-900 placeholder:text-gray-400 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-indigo-300 dark:border-white/10 dark:text-gray-100"
                rows={3}
                maxLength={500}
              />
              <p className="mt-1 text-right text-xs text-gray-300">{comment.length}/500</p>
              <div className="mt-3 flex gap-3">
                <button onClick={onCancel} className="flex-1 rounded-xl bg-gray-100 py-3 font-medium text-gray-500 dark:bg-white/10">
                  취소
                </button>
                <button onClick={confirm} className="flex-1 rounded-xl bg-indigo-600 py-3 font-medium text-white">
                  {comment.trim() ? withText : without}
                </button>
              </div>
            </motion.div>
          </motion.div>
        </>
      ) : null}
    </AnimatePresence>
  );
}
