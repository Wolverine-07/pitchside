import { useEffect, useMemo, useState } from "react";
import { Crest, GoalBanner, momentLabel } from "./components";
import { dirOf } from "./i18n";
import type { Meta, Overlay } from "./types";
import { useMatch } from "./useMatch";

// /overlay: the same verified captions as a clean graphics feed on a transparent background, to drop into
// OBS or a vision mixer as a browser source over match video. 1920x1080, nothing interactive.
//   /overlay?speed=3&lang=hi&mode=analyst&fixture=KSC-RVA&key=green (key=green for a chroma-key background)

const SHOW_MS = 12000;

export default function OverlayFeed() {
  const q = new URLSearchParams(location.search);
  const lang = q.get("lang") ?? "en";
  const profile = q.get("mode") ?? "casual";
  const { view, start } = useMatch();
  const [meta, setMeta] = useState<Meta | null>(null);

  useEffect(() => {
    const bg = q.get("key") === "green" ? "#00b140" : "transparent";
    document.documentElement.style.background = bg;
    document.body.style.background = bg;
    const fixture = q.get("fixture") ?? "KSC-RVA";
    fetch(`/api/meta?seed=16&storyline=comeback&fixture=${fixture}`)
      .then((r) => r.json())
      .then((m: Meta) => {
        setMeta(m);
        start({
          seed: 16,
          storyline: "comeback",
          fixture,
          speed: Number(q.get("speed") ?? 3),
          club: m.away.code,
          player: [...m.away.players].find((p) => p.role === "ST")?.id ?? m.away.players[0].id,
          metric: "possession",
          langs: lang === "en" ? ["en"] : ["en", lang],
        });
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const m = view.meta ?? meta;
  const key = `${profile}:${lang}`;
  const latest = useMemo(() => {
    const mine = view.cards.filter((c) => c.profile_key === key || c.profile_key === `flash:${lang}`);
    return mine.filter((c) => !String(c.content.moment_type).endsWith("_recap")).at(-1);
  }, [view.cards, key, lang]);

  return (
    <div className="relative h-[1080px] w-[1920px] overflow-hidden text-white">
      {m && view.snapshot && <ScoreBug meta={m} score={view.snapshot.score} minute={view.clock.minute} />}
      <LowerThird card={latest} meta={m} />
      <div className="absolute inset-x-0 top-[300px] h-[400px]">
        <GoalBanner goal={view.lastGoal} meta={m} />
      </div>
    </div>
  );
}

function ScoreBug({ meta, score, minute }: { meta: Meta; score: Record<string, number>; minute: number }) {
  const side = (code: string, colors: string[]) => (
    <div className="flex items-center gap-2 px-3">
      <Crest code={code} colors={colors} size={26} />
      <span className="text-[20px] font-bold tracking-wide">{code}</span>
    </div>
  );
  return (
    <div className="absolute left-[64px] top-[48px] flex h-[52px] items-stretch overflow-hidden rounded-lg bg-[#0b1220]/90 shadow-2xl">
      {side(meta.home.code, meta.home.colors)}
      <div className="flex items-center bg-white px-4 font-mono text-[24px] font-bold text-[#0b1220]">
        {score[meta.home.code]}–{score[meta.away.code]}
      </div>
      {side(meta.away.code, meta.away.colors)}
      <div className="flex items-center bg-[#16233a] px-4 font-mono text-[18px] text-white/80">{minute}'</div>
    </div>
  );
}

function LowerThird({ card, meta }: { card: Overlay | undefined; meta: Meta | null }) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    if (!card) return;
    setShown(true);
    const t = window.setTimeout(() => setShown(false), SHOW_MS);
    return () => window.clearTimeout(t);
  }, [card?.overlay_id]);
  if (!card) return null;
  const c = card.content;
  const team = c.team === meta?.home.code ? meta?.home : c.team === meta?.away.code ? meta?.away : null;
  return (
    <div
      className={`absolute bottom-[72px] left-[64px] w-[1100px] transition-all duration-500 ${shown ? "translate-y-0 opacity-100" : "translate-y-6 opacity-0"}`}
    >
      <div className="flex overflow-hidden rounded-lg bg-[#0b1220]/92 shadow-2xl">
        <div className="w-2 shrink-0" style={{ background: team?.colors[0] ?? "#4f9cff" }} />
        <div className="min-w-0 flex-1 px-6 py-4">
          <div className="text-[14px] font-semibold uppercase tracking-[0.16em] text-[#7fd3a0]">
            {momentLabel(c.moment_type)} · {Math.floor(card.anchor_t_ms / 60000) + 1}'
          </div>
          <div dir={dirOf(c.lang)} className="mt-1 text-[30px] font-bold leading-tight">
            {c.headline}
          </div>
          <div dir={dirOf(c.lang)} className="mt-1 line-clamp-2 text-[22px] leading-snug text-white/85">
            {c.body}
          </div>
        </div>
      </div>
    </div>
  );
}
