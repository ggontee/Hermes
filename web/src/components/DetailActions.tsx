"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Card } from "@/lib/types";
import { patchCard } from "@/lib/client";
import CommentModal from "./CommentModal";

/** 상세 화면 아래 고정 버튼. 대기 카드는 버림/보관, 보관한 카드는 보관함으로. */
export default function DetailActions({ card }: { card: Card }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const decide = async (status: "kept" | "discarded", comment?: string) => {
    setBusy(true);
    await patchCard(card.id, { status, comment: comment || null });
    router.push(status === "kept" ? "/" : "/");
    router.refresh();
  };

  if (card.status !== "pending") {
    return (
      <p className="mt-8 text-center text-sm text-gray-400">
        {card.status === "kept" ? "보관한 카드입니다" : "버린 카드입니다"}
      </p>
    );
  }

  return (
    <>
      <div className="fixed inset-x-0 bottom-16 z-40 px-4 pb-safe">
        <div className="mx-auto flex max-w-md gap-3">
          <button disabled={busy} onClick={() => decide("discarded")} className="flex-1 rounded-xl border-2 border-red-300 bg-[var(--bg)] py-3 font-medium text-red-500">
            ✕ 버림
          </button>
          <button disabled={busy} onClick={() => setOpen(true)} className="flex-1 rounded-xl bg-emerald-500 py-3 font-medium text-white">
            ♥ 보관
          </button>
        </div>
      </div>
      <CommentModal card={card} isOpen={open} onConfirm={(c) => decide("kept", c)} onCancel={() => setOpen(false)} />
    </>
  );
}
