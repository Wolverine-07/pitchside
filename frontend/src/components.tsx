import { useEffect, useRef, useState } from "react";
import type { Meta, Overlay, Snapshot, Trace } from "./types";
import { pitchPos, type BallPoint } from "./useMatch";

export const clubColor = (meta: Meta | null, code?: string | null) =>
  meta && code ? (code === meta.home.code ? meta.home.colors[0] : meta.away.colors[0]) : "#7d8aa6";

const MOMENT_LABEL: Record<string, string> = {
  goal: "Goal",
  big_chance: "Big chance",
  pressing_spell: "Pressing spell",
  momentum_swing: "Momentum swing",
  chaos_spike: "Control lost",
  card: "Booking",
  milestone: "Milestone",
  player_speed: "Top speed",
};
export const momentLabel = (t: string) => MOMENT_LABEL[t] ?? t.replace("_", " ");

/* ---------- scoreboard ---------- */

function Crest({ code, color }: { code: string; color: string }) {
  return (
    <span
      className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-[11px] font-extrabold tracking-wide text-white ring-2 ring-white/10"
      style={{ background: color }}
    >
      {code}
    </span>
  );
}

export function Scoreboard({ meta, snapshot, clock }: { meta: Meta | null; snapshot: Snapshot | null; clock: { minute: number; added?: number; period: number } }) {
  if (!meta) return <div className="h-16 rounded-xl border border-line bg-panel" />;
  const s = snapshot?.score ?? { [meta.home.code]: 0, [meta.away.code]: 0 };
  const half = clock.minute === 0 ? "Pre-match" : clock.period === 1 ? "First half" : "Second half";
  return (
    <div className="grid h-16 shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-4 rounded-xl border border-line bg-panel px-5">
      <div className="flex min-w-0 items-center gap-3">
        <Crest code={meta.home.code} color={meta.home.colors[0]} />
        <span className="truncate text-[15px] font-semibold">{meta.home.name}</span>
      </div>
      <div className="flex flex-col items-center">
        <div className="flex items-center gap-3 font-mono text-3xl font-medium leading-none">
          <span>{s[meta.home.code]}</span>
          <span className="text-muted">:</span>
          <span>{s[meta.away.code]}</span>
        </div>
        <div className="mt-1 text-[11px] font-medium uppercase tracking-[0.14em] text-muted">
          {half} ·{" "}
          <span className="text-soft">
            {clock.minute}
            {clock.added ? `+${clock.added}` : ""}'
          </span>
        </div>
      </div>
      <div className="flex min-w-0 items-center justify-end gap-3">
        <span className="truncate text-right text-[15px] font-semibold">{meta.away.name}</span>
        <Crest code={meta.away.code} color={meta.away.colors[0]} />
      </div>
    </div>
  );
}

/* ---------- pitch ---------- */

// Same 4-3-3 shape as the simulator: x from own goal line, y from right touchline.
const SHAPE: Record<number, [number, number]> = {
  1: [5, 34], 2: [30, 60], 4: [22, 44], 5: [22, 24], 3: [30, 8], 6: [42, 34], 8: [52, 46], 10: [52, 22],
  7: [76, 58], 9: [84, 34], 11: [76, 10], 13: [5, 34], 15: [22, 34], 14: [52, 34], 17: [76, 58], 19: [84, 34],
};

function Players({ meta, onPitch, ball, focus }: { meta: Meta; onPitch: string[]; ball?: BallPoint; focus?: string }) {
  const bx = ball?.x ?? 52.5;
  const by = ball?.y ?? 34;
  const players = [...meta.home.players, ...meta.away.players].filter((p) => onPitch.includes(p.id));
  return (
    <g>
      {players.map((p) => {
        const home = p.id.startsWith(meta.home.code);
        const [sx, sy] = SHAPE[p.number] ?? [50, 34];
        const own = home ? { x: bx, y: by } : { x: 105 - bx, y: 68 - by };
        const shift = p.role === "GK" ? 0.1 : 0.55;
        let x = Math.min(91, Math.max(2, sx + (own.x - 52.5) * shift));
        let y = Math.min(66, Math.max(2, sy + (own.y - 34) * 0.25));
        if (!home) [x, y] = [105 - x, 68 - y];
        const color = home ? meta.home.colors[0] : meta.away.colors[0];
        return (
          <g key={p.id} style={{ transition: "transform 800ms cubic-bezier(.2,.7,.3,1)" }} transform={`translate(${x} ${68 - y})`}>
            {p.id === focus && <circle r="2.8" fill="none" stroke="#fbbf24" strokeWidth="0.4" />}
            <circle r="1.45" fill={color} stroke="rgba(255,255,255,.85)" strokeWidth="0.22" />
            <text y="0.55" textAnchor="middle" fontSize="1.45" fontWeight="700" fill="white">
              {p.number}
            </text>
          </g>
        );
      })}
    </g>
  );
}

export function Pitch({ meta, trail, tags, clockMs, onPitch, focus, children }: { meta: Meta | null; trail: BallPoint[]; tags: Overlay[]; clockMs: number; onPitch: string[]; focus?: string; children?: React.ReactNode }) {
  const ball = trail.at(-1);
  const recent = trail.slice(-5);
  const recentTags = tags.filter((t) => clockMs - t.anchor_t_ms < 20_000).slice(-2);
  return (
    <div className="pitch-box relative overflow-hidden rounded-xl border border-line shadow-[0_20px_60px_-20px_rgba(0,0,0,.6)]">
      <svg viewBox="-3 -3 111 74" className="absolute inset-0 h-full w-full">
        <defs>
          <radialGradient id="vignette" cx="50%" cy="50%" r="75%">
            <stop offset="60%" stopColor="black" stopOpacity="0" />
            <stop offset="100%" stopColor="black" stopOpacity="0.45" />
          </radialGradient>
        </defs>
        <rect x="-3" y="-3" width="111" height="74" fill="var(--color-grass)" />
        {Array.from({ length: 10 }, (_, i) => (
          <rect key={i} x={i * 10.5} y="0" width="10.5" height="68" fill={i % 2 ? "var(--color-grass-2)" : "var(--color-grass)"} />
        ))}
        <g fill="none" stroke="rgba(255,255,255,.55)" strokeWidth="0.3">
          <rect x="0" y="0" width="105" height="68" />
          <line x1="52.5" y1="0" x2="52.5" y2="68" />
          <circle cx="52.5" cy="34" r="9.15" />
          <circle cx="52.5" cy="34" r="0.4" fill="rgba(255,255,255,.55)" />
          <rect x="0" y="13.84" width="16.5" height="40.32" />
          <rect x="88.5" y="13.84" width="16.5" height="40.32" />
          <rect x="0" y="24.84" width="5.5" height="18.32" />
          <rect x="99.5" y="24.84" width="5.5" height="18.32" />
          <path d="M16.5 26.7 A9.15 9.15 0 0 1 16.5 41.3" />
          <path d="M88.5 26.7 A9.15 9.15 0 0 0 88.5 41.3" />
          <rect x="-1.6" y="30.34" width="1.6" height="7.32" />
          <rect x="105" y="30.34" width="1.6" height="7.32" />
        </g>
        {meta && <Players meta={meta} onPitch={onPitch} ball={ball} focus={focus} />}
        {recent.slice(1).map((p, i) => (
          <line key={i} x1={recent[i].x} y1={68 - recent[i].y} x2={p.x} y2={68 - p.y} stroke="white" strokeOpacity={0.12 + i * 0.12} strokeWidth="0.35" strokeLinecap="round" />
        ))}
        {ball && (
          <g style={{ transition: "transform 300ms linear" }} transform={`translate(${ball.x} ${68 - ball.y})`}>
            <circle r="2.4" fill="white" opacity="0.12" />
            <circle r="0.95" fill="white" />
          </g>
        )}
        {recentTags.map((t) => {
          const team = t.content.player.split("-")[0];
          const p = pitchPos(meta, team, t.content.x ?? 52, t.content.y ?? 34);
          const label = `${t.content.name.split(" ").at(-1)} · ${Math.round(t.content.speed_kmh)} km/h`;
          return (
            <g key={t.overlay_id} transform={`translate(${Math.min(p.x, 84)} ${Math.max(68 - p.y, 6)})`}>
              <rect x="1.8" y="-5.6" width={label.length * 1.05 + 3} height="3.6" rx="1.8" fill="rgba(7,11,20,.85)" stroke={clubColor(meta, team)} strokeWidth="0.25" />
              <text x="3.3" y="-3.15" fontSize="1.9" fontWeight="600" fill="white">
                {label}
              </text>
            </g>
          );
        })}
        <rect x="-3" y="-3" width="111" height="74" fill="url(#vignette)" pointerEvents="none" />
      </svg>
      {children}
    </div>
  );
}

/* ---------- lower third ---------- */

let current: HTMLAudioElement | null = null;

/** Azure AI Speech neural voice from the API; the browser's own voice if that is unavailable. */
function speak(text: string, lang: string) {
  current?.pause();
  const audio = new Audio(`/api/speak?lang=${lang}&text=${encodeURIComponent(text)}`);
  current = audio;
  audio.play().catch(() => {
    if (!("speechSynthesis" in window)) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = ({ en: "en-GB", hi: "hi-IN", es: "es-ES" } as Record<string, string>)[lang] ?? "en-GB";
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
  });
}

/** A slim broadcast lower third: newest card for this viewer, on screen for a few seconds. */
export function LowerThird({ card, voice, lang, meta }: { card: Overlay | undefined; voice: boolean; lang: string; meta: Meta | null }) {
  const [shown, setShown] = useState<Overlay | undefined>();
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (!card) return;
    setShown(card);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setShown(undefined), 8000);
    if (voice) speak(card.content.body, lang);
  }, [card?.overlay_id]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!shown) return null;
  const c = shown.content;
  const color = clubColor(meta, c.team);
  return (
    <div key={shown.overlay_id} className="rise pointer-events-none absolute bottom-[4%] left-[3%] w-[min(560px,64%)] overflow-hidden rounded-lg bg-[rgba(7,11,20,.86)] shadow-2xl ring-1 ring-white/10 backdrop-blur-md">
      <div className="flex">
        <div className="w-1 shrink-0" style={{ background: color }} />
        <div className="min-w-0 px-3.5 py-2.5">
          <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.14em]">
            <span style={{ color }}>{momentLabel(c.moment_type)}</span>
            <span className="text-muted">·</span>
            <span className="flex items-center gap-1 text-good">
              <svg viewBox="0 0 12 12" className="h-2.5 w-2.5" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M2 6.5 5 9l5-6" />
              </svg>
              Verified
            </span>
          </div>
          <div className="mt-0.5 truncate text-[15px] font-semibold leading-snug">{c.headline}</div>
          <div className="line-clamp-2 text-[13px] leading-snug text-soft">{c.body}</div>
        </div>
      </div>
    </div>
  );
}

/* ---------- stats row ---------- */

export function Panel({ title, right, children, className = "" }: { title: string; right?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <div className={`flex min-h-0 flex-col rounded-xl border border-line bg-panel ${className}`}>
      <div className="flex items-center justify-between px-4 pt-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
        <span>{title}</span>
        {right}
      </div>
      <div className="min-h-0 flex-1 px-4 pb-3 pt-2">{children}</div>
    </div>
  );
}

export function Momentum({ data, meta }: { data: { t: number; v: number }[]; meta: Meta | null }) {
  const w = 600,
    h = 64;
  const tMax = Math.max(95 * 60_000, data.at(-1)?.t ?? 0);
  const pts = data.map((d) => [(d.t / tMax) * w, h / 2 - (d.v / 100) * (h / 2 - 3)] as const);
  const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" L");
  const area = pts.length > 1 ? `M${pts[0][0]},${h / 2} L${line} L${pts.at(-1)![0]},${h / 2} Z` : "";
  const home = clubColor(meta, meta?.home.code);
  const away = clubColor(meta, meta?.away.code);
  return (
    <Panel
      title="Momentum"
      right={
        <span className="flex gap-3 normal-case tracking-normal">
          <span className="flex items-center gap-1.5">
            <i className="h-2 w-2 rounded-full" style={{ background: home }} />
            {meta?.home.code}
          </span>
          <span className="flex items-center gap-1.5">
            <i className="h-2 w-2 rounded-full" style={{ background: away }} />
            {meta?.away.code}
          </span>
        </span>
      }
    >
      <svg viewBox={`0 0 ${w} ${h}`} className="h-full min-h-14 w-full" preserveAspectRatio="none">
        <defs>
          <clipPath id="top">
            <rect x="0" y="0" width={w} height={h / 2} />
          </clipPath>
          <clipPath id="bottom">
            <rect x="0" y={h / 2} width={w} height={h / 2} />
          </clipPath>
        </defs>
        <line x1={w * (45 / 95)} y1="0" x2={w * (45 / 95)} y2={h} stroke="var(--color-line)" strokeDasharray="3 3" />
        <line x1="0" y1={h / 2} x2={w} y2={h / 2} stroke="var(--color-line)" />
        {area && (
          <>
            <path d={area} fill={home} fillOpacity="0.55" clipPath="url(#top)" />
            <path d={area} fill={away} fillOpacity="0.55" clipPath="url(#bottom)" />
          </>
        )}
      </svg>
    </Panel>
  );
}

function Split({ label, home, away, meta, fmt = (v: number) => String(v) }: { label: string; home: number; away: number; meta: Meta | null; fmt?: (v: number) => string }) {
  const total = home + away || 1;
  return (
    <div>
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-mono font-medium">{fmt(home)}</span>
        <span className="text-[11px] uppercase tracking-[0.12em] text-muted">{label}</span>
        <span className="font-mono font-medium">{fmt(away)}</span>
      </div>
      <div className="mt-1.5 flex h-1.5 gap-0.5 overflow-hidden rounded-full">
        <div className="rounded-l-full transition-all duration-700" style={{ width: `${(home / total) * 100}%`, background: clubColor(meta, meta?.home.code) }} />
        <div className="rounded-r-full transition-all duration-700" style={{ width: `${(away / total) * 100}%`, background: clubColor(meta, meta?.away.code) }} />
      </div>
    </div>
  );
}

export function MatchStats({ snapshot, meta }: { snapshot: Snapshot | null; meta: Meta | null }) {
  return (
    <Panel title="Match stats">
      {snapshot && meta ? (
        <div className="space-y-3">
          <Split label="Possession %" home={snapshot.possession_pct[meta.home.code]} away={snapshot.possession_pct[meta.away.code]} meta={meta} />
          <Split label="Expected goals" home={snapshot.xg[meta.home.code]} away={snapshot.xg[meta.away.code]} meta={meta} fmt={(v) => v.toFixed(2)} />
        </div>
      ) : (
        <div className="text-sm text-muted">Waiting for kick-off</div>
      )}
    </Panel>
  );
}

export function ControlGauge({ value }: { value: number | undefined }) {
  const v = value ?? 0.5;
  const label = v >= 0.65 ? "Chaotic" : v <= 0.4 ? "Controlled" : "Contested";
  const tone = v >= 0.65 ? "text-bad" : v <= 0.4 ? "text-good" : "text-warn";
  return (
    <Panel title="Control vs chaos" right={<span className="normal-case tracking-normal">last 5 min</span>}>
      <div className={`text-xl font-semibold ${tone}`}>{value === undefined ? "–" : label}</div>
      <div className="relative mt-2 h-1.5 rounded-full bg-gradient-to-r from-good via-warn to-bad">
        <div className="absolute -top-1 h-3.5 w-1 rounded bg-white shadow transition-all duration-700" style={{ left: `calc(${v * 100}% - 2px)` }} />
      </div>
      <div className="mt-1.5 flex justify-between text-[10px] uppercase tracking-[0.12em] text-muted">
        <span>Control</span>
        <span>Chaos</span>
      </div>
    </Panel>
  );
}

/* ---------- sidebar: commentary and agents ---------- */

export function CommentaryFeed({ cards, meta, liveId }: { cards: Overlay[]; meta: Meta | null; liveId?: string }) {
  if (!cards.length) return <Empty text="Captions appear here as the agents put moments on air." />;
  return (
    <ol className="space-y-2.5">
      {[...cards].reverse().map((c) => {
        const color = clubColor(meta, c.content.team);
        const minute = Math.floor(c.anchor_t_ms / 60000) + 1;
        return (
          <li key={c.overlay_id} className={`rise rounded-lg border p-3 ${c.overlay_id === liveId ? "border-accent/50 bg-accent/5" : "border-line bg-panel-2/60"}`}>
            <div className="mb-1 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.14em]">
              <span className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-soft">{minute}'</span>
              <span style={{ color }}>{momentLabel(c.content.moment_type)}</span>
              {c.provenance.fallback && <span className="text-warn">template</span>}
            </div>
            <div className="text-[14px] font-semibold leading-snug">{c.content.headline}</div>
            <div className="mt-0.5 text-[13px] leading-snug text-soft">{c.content.body}</div>
          </li>
        );
      })}
    </ol>
  );
}

const STEP_TONE: Record<string, string> = {
  ok: "text-good",
  pass: "text-good",
  rule: "text-soft",
  corrected: "text-warn",
  fallback: "text-warn",
  reject: "text-bad",
};

export function AgentSummary({ traces }: { traces: Trace[] }) {
  const steps = traces.flatMap((t) => t.steps);
  const rejected = steps.filter((s) => s.agent === "verifier" && s.status === "reject").length;
  const templates = steps.filter((s) => s.agent === "template").length;
  const corrected = steps.filter((s) => s.agent === "analyst" && s.status === "corrected").length;
  const total = traces.map((t) => t.steps.reduce((a, s) => a + s.ms, 0));
  const avg = total.length ? total.reduce((a, b) => a + b, 0) / total.length / 1000 : 0;
  const tiles = [
    { label: "Moments aired", value: traces.length },
    { label: "Drafts sent back", value: rejected },
    { label: "Citations fixed", value: corrected },
    { label: "Avg agent time", value: traces.length ? `${avg.toFixed(1)}s` : "–" },
  ];
  return (
    <div className="mb-3 grid grid-cols-2 gap-2">
      {tiles.map((t) => (
        <div key={t.label} className="rounded-lg border border-line bg-panel-2/60 px-3 py-2">
          <div className="font-mono text-lg font-medium">{t.value}</div>
          <div className="text-[10px] uppercase tracking-[0.12em] text-muted">{t.label}</div>
        </div>
      ))}
      {templates > 0 && <div className="col-span-2 text-xs text-muted">{templates} moment(s) aired a verified template line.</div>}
    </div>
  );
}

export function AgentTrace({ traces }: { traces: Trace[] }) {
  if (!traces.length) return <Empty text="Each moment's path through the six agents shows up here." />;
  return (
    <div className="space-y-2.5">
      {traces.map((t) => (
        <div key={t.moment_id} className="rise rounded-lg border border-line bg-panel-2/60 p-3">
          <div className="mb-2 flex items-center justify-between text-[11px] font-semibold uppercase tracking-[0.14em]">
            <span>{momentLabel(t.type)}</span>
            <span className="font-mono text-muted">{t.minute}'</span>
          </div>
          <ol className="space-y-1.5 border-l border-line pl-3">
            {t.steps.map((s, i) => (
              <li key={i} className="text-xs">
                <div className="flex items-center gap-2">
                  <span className="w-16 font-semibold capitalize">{s.agent}</span>
                  <span className={STEP_TONE[s.status] ?? "text-soft"}>{s.status}</span>
                  <span className="ml-auto font-mono text-muted">{s.ms >= 1000 ? `${(s.ms / 1000).toFixed(1)}s` : `${s.ms}ms`}</span>
                </div>
                {s.note && <div className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-muted">{s.note}</div>}
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="rounded-lg border border-dashed border-line p-4 text-sm text-muted">{text}</div>;
}
