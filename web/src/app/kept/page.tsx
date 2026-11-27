import { Suspense } from "react";
import KeptList from "@/components/KeptList";
import { analysesLeft, keptCards } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function KeptPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const all = keptCards();
  const counts = new Map<string, number>();
  for (const c of all) for (const t of new Set([...c.userTags, ...c.tags])) counts.set(t, (counts.get(t) ?? 0) + 1);
  const allTags = [...counts.entries()].sort((a, b) => b[1] - a[1]);

  let cards = all;
  if (sp.tag) cards = cards.filter((c) => c.tags.includes(sp.tag!) || c.userTags.includes(sp.tag!));
  if (sp.kind && sp.kind !== "all") cards = cards.filter((c) => c.kind === sp.kind);
  if (sp.analyzed === "1") cards = cards.filter((c) => c.analysis?.status === "done");
  const key = `${sp.tag ?? ""}|${sp.kind ?? ""}|${sp.analyzed ?? ""}`;

  return (
    <>
      <h1 className="mb-4 text-2xl font-bold tracking-tight">
        보관함 <span className="text-base font-normal text-gray-400">{all.length}</span>
      </h1>
      <Suspense>
        <KeptList
          key={key}
          cards={cards}
          allTags={allTags}
          analysesLeft={analysesLeft()}
          tanaBase={process.env.HERMES_TANA_NODE_URL ?? "https://app.tana.inc/?nodeid="}
        />
      </Suspense>
    </>
  );
}
