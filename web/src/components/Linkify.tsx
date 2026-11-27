import { Fragment } from "react";

const URL_RE = /(https?:\/\/[^\s<>"')\]]+)/g;

/** 줄바꿈과 링크를 살려서 평문을 그린다. 링크를 눌러도 카드가 넘어가지 않게 전파를 막는다. */
export default function Linkify({ text }: { text: string }) {
  const parts = text.split(URL_RE);
  return (
    <>
      {parts.map((p, i) =>
        i % 2 === 1 ? (
          <a
            key={i}
            href={p}
            target="_blank"
            rel="noreferrer"
            className="text-indigo-600 underline break-all dark:text-indigo-400"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => e.stopPropagation()}
          >
            {p.replace(/^https?:\/\//, "").slice(0, 48)}
            {p.replace(/^https?:\/\//, "").length > 48 ? "…" : ""}
          </a>
        ) : (
          <Fragment key={i}>{p}</Fragment>
        ),
      )}
    </>
  );
}
