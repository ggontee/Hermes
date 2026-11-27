"use client";

import { type RefObject } from "react";
import { motion, useMotionValue, useTransform, type PanInfo } from "framer-motion";
import type { Card } from "@/lib/types";
import CardBody from "./CardBody";

// Mnemo SwipeCard를 옮겼다. 오른쪽 = 보관, 왼쪽 = 버림.
const SWIPE_THRESHOLD = 120;

interface Props {
  card: Card;
  isTop: boolean;
  disabled?: boolean;
  exitDirectionRef: RefObject<"left" | "right" | null>;
  onSwipe: (direction: "left" | "right") => void;
  onOpen: () => void;
}

export default function SwipeCard({ card, isTop, disabled, exitDirectionRef, onSwipe, onOpen }: Props) {
  const x = useMotionValue(0);
  const rotate = useTransform(x, [-300, 0, 300], [-15, 0, 15]);
  const opacity = useTransform(x, [-300, -100, 0, 100, 300], [0.5, 1, 1, 1, 0.5]);
  const keepOpacity = useTransform(x, [0, 100, 200], [0, 0.5, 1]);
  const discardOpacity = useTransform(x, [-200, -100, 0], [1, 0.5, 0]);

  function handleDragEnd(_: unknown, info: PanInfo) {
    if (info.offset.x > SWIPE_THRESHOLD) onSwipe("right");
    else if (info.offset.x < -SWIPE_THRESHOLD) onSwipe("left");
  }

  return (
    <motion.div
      className="absolute inset-0"
      style={{ x, rotate, opacity, zIndex: isTop ? 10 : 0, cursor: isTop ? "grab" : "default" }}
      drag={isTop && !disabled ? "x" : false}
      dragConstraints={{ left: 0, right: 0 }}
      dragElastic={0.9}
      onDragEnd={handleDragEnd}
      onTap={isTop && !disabled ? onOpen : undefined}
      initial={{ scale: isTop ? 1 : 0.95, y: isTop ? 0 : 10 }}
      animate={{ scale: isTop ? 1 : 0.95, y: isTop ? 0 : 10 }}
      exit={{
        x: exitDirectionRef.current === "right" ? 400 : exitDirectionRef.current === "left" ? -400 : x.get() > 0 ? 400 : -400,
        opacity: 0,
        transition: { duration: 0.3 },
      }}
      whileDrag={{ cursor: "grabbing" }}
    >
      <div className="relative h-full w-full overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-lg dark:border-white/10 dark:bg-[#1b1c1f]">
        <motion.div
          className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-2xl bg-emerald-500/20"
          style={{ opacity: keepOpacity }}
        >
          <span className="-rotate-12 rounded-xl border-4 border-emerald-600 px-6 py-2 text-3xl font-bold text-emerald-600">KEEP</span>
        </motion.div>
        <motion.div
          className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-2xl bg-red-500/20"
          style={{ opacity: discardOpacity }}
        >
          <span className="rotate-12 rounded-xl border-4 border-red-600 px-6 py-2 text-3xl font-bold text-red-600">PASS</span>
        </motion.div>
        {/* 세로 스크롤은 자유, 가로만 스와이프 */}
        <div className="h-full overflow-y-auto overscroll-contain" style={{ touchAction: "pan-y" }}>
          <CardBody card={card} />
        </div>
      </div>
    </motion.div>
  );
}
