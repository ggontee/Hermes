"use client";

import type { CardStatus } from "./types";

// 스와이프 결과는 바로 보내고, 실패하면(오프라인 등) 기기에 쌓아 두었다가 온라인이 되면 다시 보낸다.
const OUTBOX = "hermes.outbox";

interface Pending {
  id: number;
  body: Record<string, unknown>;
}

function read(): Pending[] {
  try {
    return JSON.parse(localStorage.getItem(OUTBOX) ?? "[]");
  } catch {
    return [];
  }
}

function write(list: Pending[]) {
  try {
    localStorage.setItem(OUTBOX, JSON.stringify(list));
  } catch {}
}

async function send(id: number, body: Record<string, unknown>): Promise<boolean> {
  try {
    const r = await fetch(`/api/cards/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    return r.ok || (r.status >= 400 && r.status < 500); // 4xx는 다시 보내도 같다
  } catch {
    return false;
  }
}

export async function patchCard(id: number, body: { status?: CardStatus; comment?: string | null; userTags?: string[] }) {
  if (await send(id, body)) return true;
  write([...read().filter((p) => !(p.id === id && "status" in p.body && "status" in body)), { id, body }]);
  return false;
}

let flushing = false;
export async function flushOutbox() {
  if (flushing) return;
  flushing = true;
  try {
    const left: Pending[] = [];
    for (const p of read()) if (!(await send(p.id, p.body))) left.push(p);
    write(left);
  } finally {
    flushing = false;
  }
}

export function loadPref<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(`hermes.${key}`);
    return v ? (JSON.parse(v) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function savePref(key: string, value: unknown) {
  try {
    localStorage.setItem(`hermes.${key}`, JSON.stringify(value));
  } catch {}
}
