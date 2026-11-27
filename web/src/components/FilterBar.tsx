"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { loadPref, savePref } from "@/lib/client";

const FIELDS = [
  ["all", "전체"],
  ["AI", "AI"],
  ["Tech", "Tech"],
  ["Bio", "Bio"],
] as const;
const KINDS = [
  ["all", "전체"],
  ["short", "SNS"],
  ["long", "글"],
  ["video", "영상"],
] as const;

type Pref = { field: string; kind: string; person: string };

function Chips({ items, value, onPick }: { items: readonly (readonly [string, string])[]; value: string; onPick: (v: string) => void }) {
  return (
    <div className="flex gap-1">
      {items.map(([v, label]) => (
        <button
          key={v}
          onClick={() => onPick(v)}
          className={`rounded-full px-3 py-1 text-sm transition-colors ${
            value === v ? "bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900" : "bg-gray-100 text-gray-500 dark:bg-white/10 dark:text-gray-400"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/** 필터는 URL에 두고(서버가 그 조건으로 읽는다), 마지막 선택을 기기에 기억한다. */
export default function FilterBar({ people }: { people: string[] }) {
  const router = useRouter();
  const path = usePathname();
  const params = useSearchParams();
  const cur: Pref = { field: params.get("field") ?? "all", kind: params.get("kind") ?? "all", person: params.get("person") ?? "" };
  const [person, setPerson] = useState(cur.person);
  const [open, setOpen] = useState(!!cur.person);

  const apply = (p: Pref) => {
    savePref("filter", p);
    const q = new URLSearchParams();
    if (p.field !== "all") q.set("field", p.field);
    if (p.kind !== "all") q.set("kind", p.kind);
    if (p.person) q.set("person", p.person);
    router.replace(q.size ? `${path}?${q}` : path);
  };

  useEffect(() => {
    if (params.size) return;
    const saved = loadPref<Pref | null>("filter", null);
    if (saved && (saved.field !== "all" || saved.kind !== "all" || saved.person)) {
      setPerson(saved.person);
      setOpen(!!saved.person);
      apply(saved);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="mb-4 space-y-2">
      <div className="flex items-center justify-between gap-2 overflow-x-auto">
        <Chips items={FIELDS} value={cur.field} onPick={(field) => apply({ ...cur, field })} />
        <button
          onClick={() => setOpen((v) => !v)}
          className={`shrink-0 rounded-full px-3 py-1 text-sm ${cur.person ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300" : "bg-gray-100 text-gray-500 dark:bg-white/10"}`}
        >
          {cur.person ? cur.person : "인물"}
        </button>
      </div>
      <Chips items={KINDS} value={cur.kind} onPick={(kind) => apply({ ...cur, kind })} />
      {open ? (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            apply({ ...cur, person: people.includes(person) ? person : "" });
          }}
        >
          <input
            list="hermes-people"
            value={person}
            onChange={(e) => setPerson(e.target.value)}
            placeholder="인물 이름"
            className="min-w-0 flex-1 rounded-xl border border-gray-200 bg-transparent px-3 py-1.5 text-sm dark:border-white/10"
          />
          <datalist id="hermes-people">
            {people.map((p) => (
              <option key={p} value={p} />
            ))}
          </datalist>
          <button className="rounded-xl bg-gray-900 px-3 text-sm text-white dark:bg-gray-100 dark:text-gray-900">적용</button>
          {cur.person ? (
            <button
              type="button"
              onClick={() => {
                setPerson("");
                apply({ ...cur, person: "" });
              }}
              className="text-sm text-gray-400"
            >
              해제
            </button>
          ) : null}
        </form>
      ) : null}
    </div>
  );
}
