import { Suspense } from "react";
import CardStack from "@/components/CardStack";
import FilterBar from "@/components/FilterBar";
import { nextRunLabel, pendingCards, people } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function FeedPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const cards = pendingCards({ field: sp.field, kind: sp.kind, person: sp.person });
  const key = `${sp.field ?? ""}|${sp.kind ?? ""}|${sp.person ?? ""}`;
  return (
    <>
      <header className="mb-3 flex items-baseline justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Hermes</h1>
      </header>
      <Suspense>
        <FilterBar people={people()} />
      </Suspense>
      <CardStack key={key} initialCards={cards} total={cards.length} nextRun={nextRunLabel()} />
    </>
  );
}
