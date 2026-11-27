import { statusInfo } from "@/lib/db";
import { dateTime } from "@/lib/format";

export const dynamic = "force-dynamic";

function Meter({ label, used, limit }: { label: string; used: number; limit: number }) {
  const pct = limit ? Math.min(100, (used / limit) * 100) : 0;
  return (
    <div>
      <div className="flex justify-between text-sm">
        <span>{label}</span>
        <span className="tabular-nums text-gray-500">
          {used} / {limit}
        </span>
      </div>
      <div className="mt-1 h-1.5 rounded-full bg-gray-200 dark:bg-white/10">
        <div className={`h-1.5 rounded-full ${pct >= 100 ? "bg-red-500" : "bg-indigo-500"}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function StatusPage() {
  const s = statusInfo();
  const r = s.lastRun;
  return (
    <>
      <h1 className="mb-4 text-2xl font-bold tracking-tight">상태</h1>

      <section className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-white/10 dark:bg-[#1b1c1f]">
        <h2 className="text-sm font-semibold text-gray-500">마지막 수집</h2>
        {r ? (
          <>
            <p className="mt-1 text-lg font-semibold">
              {dateTime(r.startedAt)} {r.finishedAt ? "" : <span className="text-sm text-amber-600">진행 중</span>}
            </p>
            <dl className="mt-3 grid grid-cols-4 gap-2 text-center">
              {[
                ["새 글", r.newItems],
                ["AI 처리", r.processed],
                ["상한 미룸", r.deferred],
                ["오류", r.errors],
              ].map(([k, v]) => (
                <div key={k as string} className="rounded-xl bg-gray-50 py-2 dark:bg-white/5">
                  <dt className="text-xs text-gray-400">{k}</dt>
                  <dd className="text-lg font-semibold tabular-nums">{v}</dd>
                </div>
              ))}
            </dl>
          </>
        ) : (
          <p className="mt-1 text-gray-400">아직 수집한 적이 없습니다.</p>
        )}
        <p className="mt-3 text-sm text-gray-500">
          다음 수집 {s.nextRun} · 대기 카드 {s.pendingCount}장
        </p>
      </section>

      <section className="mt-4 space-y-3 rounded-2xl border border-gray-200 bg-white p-4 dark:border-white/10 dark:bg-[#1b1c1f]">
        <h2 className="text-sm font-semibold text-gray-500">오늘 사용량</h2>
        <Meter label="AI 처리" used={s.usage.aiItems} limit={s.limits.aiItems} />
        <Meter label="영상 받아쓰기" used={s.usage.videos} limit={s.limits.videos} />
        <Meter label="심화 분석" used={s.usage.analyses} limit={s.limits.analyses} />
        <p className="text-sm text-gray-500">추정 비용 ${s.usage.costUsd.toFixed(2)}</p>
      </section>

      <section className="mt-4 rounded-2xl border border-gray-200 bg-white p-4 dark:border-white/10 dark:bg-[#1b1c1f]">
        <h2 className="text-sm font-semibold text-gray-500">소스 오류 {s.sourceErrors.length ? s.sourceErrors.length : ""}</h2>
        {s.sourceErrors.length === 0 ? (
          <p className="mt-1 text-sm text-gray-400">모든 소스가 정상입니다.</p>
        ) : (
          <ul className="mt-2 divide-y divide-gray-100 dark:divide-white/5">
            {s.sourceErrors.map((e, i) => (
              <li key={i} className="py-2 text-sm">
                <p className="font-medium">
                  {e.person} <span className="text-gray-400">· {e.type}</span>
                </p>
                <p className="text-red-500 break-all">{e.error}</p>
                <p className="text-xs text-gray-400">마지막 성공 {dateTime(e.lastSuccessAt)}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
