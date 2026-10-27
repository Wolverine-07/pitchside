import { useEffect, useState } from "react";
import type { Evidence, Goal, League, MatchEvent, Meta, Overlay, PlayerStats, Shot, Snapshot, Trace } from "./types";
import { pitchPos, type BallPoint, type Replay } from "./useMatch";
import { dirOf } from "./i18n";
import { speak } from "./voice";

export const clubColor = (meta: Meta | null, code?: string | null) =>
  meta && code
    ? code === meta.home.code
      ? meta.home.colors[0]
      : meta.away.colors[0]
    : "#7d8aa6";

const MOMENT_LABEL: Record<string, string> = {
  goal: "Goal",
  big_chance: "Big chance",
  pressing_spell: "Pressing spell",
  momentum_swing: "Momentum swing",
  chaos_spike: "Control lost",
  card: "Booking",
  milestone: "Milestone",
  player_speed: "Top speed",
  player_spotlight: "Player spotlight",
  match_preview: "Kick-off",
  match_pulse: "State of play",
  great_save: "Great save",
  around_the_league: "Around the league",
  half_time_recap: "Half-time recap",
  full_time_recap: "Full-time recap",
};
export const isRecap = (o?: Overlay) =>
  !!o && String(o.content.moment_type).endsWith("_recap");
export const momentLabel = (type: string) =>
  MOMENT_LABEL[type] ?? type.replaceAll("_", " ");

/* ---------- scoreboard ---------- */

/** A shield crest in the club's two colours, with its code. */
export function Crest({ code, colors, size = 40 }: { code: string; colors: string[]; size?: number }) {
  const [a, b] = colors;
  return (
    <svg viewBox="0 0 40 46" width={size} height={size * 1.15} className="shrink-0 drop-shadow-md">
      <path d="M20 1 L38 6 V22 C38 33 30 40 20 45 C10 40 2 33 2 22 V6 Z" fill={a} stroke="rgba(255,255,255,.85)" strokeWidth="1.5" />
      <path d="M20 1 L38 6 V22 C38 33 30 40 20 45 Z" fill="black" opacity="0.12" />
      <path d="M6 9 H34" stroke={b} strokeWidth="2.2" opacity="0.9" />
      <text x="20" y="29" textAnchor="middle" fontSize="11" fontWeight="800" fill="white" style={{ letterSpacing: "0.5px" }}>
        {code}
      </text>
    </svg>
  );
}

const playerName = (meta: Meta, id: string) =>
  [...meta.home.players, ...meta.away.players]
    .find((p) => p.id === id)
    ?.name.split(" ")
    .at(-1) ?? id;

function Scorers({
  meta,
  goals,
  team,
  align,
}: {
  meta: Meta;
  goals: Goal[];
  team: string;
  align: "left" | "right";
}) {
  const mine = goals.filter((g) => g.team === team);
  if (!mine.length) return null;
  return (
    <div
      className={`truncate text-[11px] text-soft ${align === "right" ? "text-right" : ""}`}
    >
      {mine.map((g, i) => (
        <span key={i}>
          {i > 0 && ", "}
          {playerName(meta, g.player)} {g.minute}
          {g.added ? `+${g.added}` : ""}'
        </span>
      ))}
    </div>
  );
}

export function Scoreboard({
  meta,
  snapshot,
  clock,
  goals = [],
}: {
  meta: Meta | null;
  snapshot: Snapshot | null;
  clock: { minute: number; added?: number; period: number };
  goals?: Goal[];
}) {
  if (!meta)
    return <div className="h-16 rounded-xl border border-line bg-panel" />;
  const s = snapshot?.score ?? { [meta.home.code]: 0, [meta.away.code]: 0 };
  const half =
    clock.minute === 0
      ? "Pre-match"
      : clock.period === 1
        ? "First half"
        : "Second half";
  return (
    <div className="grid h-16 shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-4 rounded-xl border border-line bg-panel px-5">
      <div className="flex min-w-0 items-center gap-3">
        <Crest code={meta.home.code} colors={meta.home.colors} />
        <div className="min-w-0">
          <div className="truncate text-[15px] font-semibold">
            {meta.home.name}
          </div>
          <Scorers
            meta={meta}
            goals={goals}
            team={meta.home.code}
            align="left"
          />
        </div>
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
        <div className="min-w-0">
          <div className="truncate text-right text-[15px] font-semibold">
            {meta.away.name}
          </div>
          <Scorers
            meta={meta}
            goals={goals}
            team={meta.away.code}
            align="right"
          />
        </div>
        <Crest code={meta.away.code} colors={meta.away.colors} />
      </div>
    </div>
  );
}

/* ---------- pitch ---------- */

// Same 4-3-3 shape as the simulator: x from own goal line, y from right touchline.
const SHAPE: Record<number, [number, number]> = {
  1: [5, 34],
  2: [30, 60],
  4: [22, 44],
  5: [22, 24],
  3: [30, 8],
  6: [42, 34],
  8: [52, 46],
  10: [52, 22],
  7: [76, 58],
  9: [84, 34],
  11: [76, 10],
  13: [5, 34],
  15: [22, 34],
  14: [52, 34],
  17: [76, 58],
  19: [84, 34],
};

function Players({
  meta,
  onPitch,
  ball,
  focus,
  carrier,
}: {
  meta: Meta;
  onPitch: string[];
  ball?: BallPoint;
  focus?: string;
  carrier?: string | null;
}) {
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
        const [main, trim] = home ? meta.home.colors : meta.away.colors;
        const keeper = p.role === "GK";
        const onBall = p.id === carrier;
        // The ball carrier stands where the ball is, so the name sits with the action.
        if (onBall && ball) [x, y] = [ball.x, ball.y];
        return (
          <g key={p.id} style={{ transition: "transform 700ms cubic-bezier(.2,.7,.3,1)" }} transform={`translate(${x} ${68 - y})`}>
            {onBall && <circle r="3.1" fill="white" opacity="0.18" />}
            {p.id === focus && <circle r="2.9" fill="none" stroke="#fbbf24" strokeWidth="0.45" strokeDasharray="1 0.6" />}
            <circle r="1.6" fill={keeper ? "#111827" : main} stroke={keeper ? main : trim} strokeWidth="0.42" />
            <text y="0.58" textAnchor="middle" fontSize="1.55" fontWeight="800" fill="white">
              {p.number}
            </text>
            {onBall && (
              <g transform="translate(0 -3.4)">
                <rect x={-p.name.split(" ").at(-1)!.length * 0.62 - 1} y="-1.45" width={p.name.split(" ").at(-1)!.length * 1.24 + 2} height="2.5" rx="1.25" fill="rgba(7,11,20,.85)" />
                <text y="0.45" textAnchor="middle" fontSize="1.55" fontWeight="700" fill="white">
                  {p.name.split(" ").at(-1)}
                </text>
              </g>
            )}
          </g>
        );
      })}
    </g>
  );
}

export function Pitch({
  meta,
  trail,
  tags,
  clockMs,
  onPitch,
  focus,
  shots = [],
  replay,
  carrier,
  children,
}: {
  meta: Meta | null;
  trail: BallPoint[];
  tags: Overlay[];
  clockMs: number;
  onPitch: string[];
  focus?: string;
  shots?: Shot[];
  replay?: Replay | null;
  carrier?: string | null;
  children?: React.ReactNode;
}) {
  const ball = trail.at(-1);
  const recent = trail.slice(-5);
  const recentTags = tags
    .filter((t) => clockMs - t.anchor_t_ms < 20_000)
    .slice(-2);
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
          <rect
            key={i}
            x={i * 10.5}
            y="0"
            width="10.5"
            height="68"
            fill={i % 2 ? "var(--color-grass-2)" : "var(--color-grass)"}
          />
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
        {shots.map((s, i) => {
          const r = 0.7 + s.xg * 2.6; // marker size grows with chance quality
          const color = clubColor(meta, s.team);
          return s.outcome === "goal" ? (
            <g key={i} transform={`translate(${s.x} ${68 - s.y})`}>
              <circle
                r={r + 0.6}
                fill="none"
                stroke="white"
                strokeWidth="0.35"
              />
              <circle r={r} fill={color} />
            </g>
          ) : (
            <circle
              key={i}
              cx={s.x}
              cy={68 - s.y}
              r={r}
              fill="none"
              stroke={color}
              strokeWidth="0.35"
              opacity="0.9"
            />
          );
        })}
        {meta && (
          <Players meta={meta} onPitch={onPitch} ball={ball} focus={focus} carrier={carrier} />
        )}
        {recent.slice(1).map((p, i) => (
          <line
            key={i}
            x1={recent[i].x}
            y1={68 - recent[i].y}
            x2={p.x}
            y2={68 - p.y}
            stroke="white"
            strokeOpacity={0.12 + i * 0.12}
            strokeWidth="0.35"
            strokeLinecap="round"
          />
        ))}
        {ball && (
          <g
            style={{ transition: "transform 300ms linear" }}
            transform={`translate(${ball.x} ${68 - ball.y})`}
          >
            <circle r="2.4" fill="white" opacity="0.12" />
            <circle r="0.95" fill="white" />
          </g>
        )}
        {recentTags.map((t) => {
          const team = t.content.player.split("-")[0];
          const p = pitchPos(meta, team, t.content.x ?? 52, t.content.y ?? 34);
          const label = `${t.content.name.split(" ").at(-1)} · ${Math.round(t.content.speed_kmh)} km/h`;
          return (
            <g
              key={t.overlay_id}
              transform={`translate(${Math.min(p.x, 84)} ${Math.max(68 - p.y, 6)})`}
            >
              <rect
                x="1.8"
                y="-5.6"
                width={label.length * 1.05 + 3}
                height="3.6"
                rx="1.8"
                fill="rgba(7,11,20,.85)"
                stroke={clubColor(meta, team)}
                strokeWidth="0.25"
              />
              <text
                x="3.3"
                y="-3.15"
                fontSize="1.9"
                fontWeight="600"
                fill="white"
              >
                {label}
              </text>
            </g>
          );
        })}
        <rect
          x="-3"
          y="-3"
          width="111"
          height="74"
          fill="url(#vignette)"
          pointerEvents="none"
        />
        {replay && <ReplayLayer replay={replay} meta={meta} />}
      </svg>
      {replay && meta && (
        <div className="rise pointer-events-none absolute left-1/2 top-[4%] -translate-x-1/2 rounded-full bg-[rgba(7,11,20,.86)] px-4 py-1.5 text-[12px] font-semibold uppercase tracking-[0.16em] ring-1 ring-white/10">
          <span className="text-bad">● Replay</span> · {playerName(meta, replay.player)} {replay.minute}'
        </div>
      )}
      {children}
    </div>
  );
}

/* ---------- subtitle bar ---------- */

/** Commentary under the pitch, like broadcast subtitles: it never covers play. The newest caption
 * stays until the next one; after a while it dims so a fresh one stands out. */
export function CaptionBar({
  card,
  voice,
  lang,
  meta,
  pending,
}: {
  card: Overlay | undefined;
  voice: boolean;
  lang: string;
  meta: Meta | null;
  pending?: string;
}) {
  const [stale, setStale] = useState(false);
  useEffect(() => {
    if (!card) return;
    setStale(false);
    const t = window.setTimeout(() => setStale(true), 15000);
    if (voice) speak(card.content.body, lang);
    return () => window.clearTimeout(t);
  }, [card?.overlay_id]); // eslint-disable-line react-hooks/exhaustive-deps
  const c = card?.content;
  const color = clubColor(meta, c?.team);
  return (
    <div className="flex h-[100px] shrink-0 overflow-hidden rounded-xl border border-line bg-panel">
      <div className="w-1.5 shrink-0 transition-colors" style={{ background: c ? color : "var(--color-line)" }} />
      {c ? (
        <div key={card!.overlay_id} className={`rise min-w-0 flex-1 px-4 py-2.5 transition-opacity duration-700 ${stale ? "opacity-60" : ""}`}>
          <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.14em]">
            <span className="font-mono text-muted">{Math.floor(card!.anchor_t_ms / 60000) + 1}'</span>
            <span style={{ color }}>{momentLabel(c.moment_type)}</span>
            <span className="flex items-center gap-1 text-good">
              <svg viewBox="0 0 12 12" className="h-2.5 w-2.5" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M2 6.5 5 9l5-6" />
              </svg>
              Verified
            </span>
            {pending && <span className="ml-auto normal-case tracking-normal text-muted">{pending}</span>}
          </div>
          <div dir={dirOf(c.lang)} className="mt-0.5 truncate text-[16px] font-semibold leading-snug">
            {c.headline}
          </div>
          <div dir={dirOf(c.lang)} className="line-clamp-2 text-[14px] leading-snug text-soft">
            {c.body}
          </div>
        </div>
      ) : (
        <div className="flex flex-1 items-center gap-2 px-4 text-[14px] text-muted">
          <i className="live-dot h-1.5 w-1.5 rounded-full bg-accent" />
          {pending ?? "Commentary appears here from kick-off."}
        </div>
      )}
    </div>
  );
}

/* ---------- stats row ---------- */

export function Panel({
  title,
  right,
  children,
  className = "",
}: {
  title: string;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`flex min-h-0 flex-col rounded-xl border border-line bg-panel ${className}`}
    >
      <div className="flex items-center justify-between px-4 pt-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
        <span>{title}</span>
        {right}
      </div>
      <div className="min-h-0 flex-1 px-4 pb-3 pt-2">{children}</div>
    </div>
  );
}

export function Momentum({
  data,
  meta,
  goals = [],
  chaos,
}: {
  data: { t: number; v: number }[];
  meta: Meta | null;
  goals?: Goal[];
  chaos?: number;
}) {
  const w = 600,
    h = 64;
  const tMax = Math.max(95 * 60_000, data.at(-1)?.t ?? 0);
  const pts = data.map(
    (d) => [(d.t / tMax) * w, h / 2 - (d.v / 100) * (h / 2 - 3)] as const,
  );
  const line = pts
    .map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" L");
  const area =
    pts.length > 1
      ? `M${pts[0][0]},${h / 2} L${line} L${pts.at(-1)![0]},${h / 2} Z`
      : "";
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
      <div className="relative h-full min-h-14">
        <svg
          viewBox={`0 0 ${w} ${h}`}
          className="h-full w-full"
          preserveAspectRatio="none"
        >
          <defs>
            <clipPath id="top">
              <rect x="0" y="0" width={w} height={h / 2} />
            </clipPath>
            <clipPath id="bottom">
              <rect x="0" y={h / 2} width={w} height={h / 2} />
            </clipPath>
          </defs>
          <line
            x1={w * (45 / 95)}
            y1="0"
            x2={w * (45 / 95)}
            y2={h}
            stroke="var(--color-line)"
            strokeDasharray="3 3"
          />
          <line
            x1="0"
            y1={h / 2}
            x2={w}
            y2={h / 2}
            stroke="var(--color-line)"
          />
          {area && (
            <>
              <path
                d={area}
                fill={home}
                fillOpacity="0.55"
                clipPath="url(#top)"
              />
              <path
                d={area}
                fill={away}
                fillOpacity="0.55"
                clipPath="url(#bottom)"
              />
            </>
          )}
        </svg>
        {goals.map((g, i) => {
          const left = ((g.minute + (g.minute > 45 ? 2 : 0)) / 95) * 100;
          const up = meta && g.team === meta.home.code;
          return (
            <span
              key={i}
              title={`Goal ${g.minute}'`}
              className={`absolute h-2.5 w-2.5 -translate-x-1/2 rounded-full ring-2 ring-white ${up ? "top-1" : "bottom-1"}`}
              style={{ left: `${left}%`, background: clubColor(meta, g.team) }}
            />
          );
        })}
      </div>
      {chaos !== undefined && (
        <div className="mt-1 flex items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-muted">
          <span>Control</span>
          <div className="relative h-1 flex-1 rounded-full bg-gradient-to-r from-good via-warn to-bad">
            <div className="absolute -top-1 h-3 w-1 rounded bg-white shadow transition-all duration-700" style={{ left: `calc(${chaos * 100}% - 2px)` }} />
          </div>
          <span>Chaos</span>
          <span className={`w-24 text-right font-semibold ${chaos >= 0.65 ? "text-bad" : chaos <= 0.4 ? "text-good" : "text-warn"}`}>
            {chaos >= 0.65 ? "Chaotic" : chaos <= 0.4 ? "Controlled" : "Contested"}
          </span>
        </div>
      )}
    </Panel>
  );
}



export function MatchStats({ snapshot, meta }: { snapshot: Snapshot | null; meta: Meta | null }) {
  if (!snapshot || !meta)
    return (
      <Panel title="Match stats">
        <div className="text-sm text-muted">Waiting for kick-off</div>
      </Panel>
    );
  const h = snapshot.teams?.[meta.home.code];
  const a = snapshot.teams?.[meta.away.code];
  const rows: [string, number, number, ((v: number) => string)?][] = [
    ["Possession", snapshot.possession_pct[meta.home.code], snapshot.possession_pct[meta.away.code], (v) => `${v}%`],
    ["Shots (on target)", h?.shots ?? 0, a?.shots ?? 0],
    ["Expected goals", snapshot.xg[meta.home.code], snapshot.xg[meta.away.code], (v) => v.toFixed(2)],
    ["Pass accuracy", h?.pass_accuracy_pct ?? 0, a?.pass_accuracy_pct ?? 0, (v) => `${v}%`],
    ["Corners", h?.corners ?? 0, a?.corners ?? 0],
    ["Fouls", h?.fouls ?? 0, a?.fouls ?? 0],
  ];
  const onTarget = [h?.on_target ?? 0, a?.on_target ?? 0];
  return (
    <Panel title="Match stats" right={snapshot.win_probability_pct && <WinChip p={snapshot.win_probability_pct} meta={meta} />}>
      <div className="space-y-[5px]">
        {rows.map(([label, hv, av, fmt], i) => {
          const total = hv + av || 1;
          const f = fmt ?? ((v: number) => String(v));
          return (
            <div key={label} className="grid grid-cols-[52px_1fr_52px] items-center gap-2 text-[12px]">
              <span className="text-right font-mono">
                {f(hv)}
                {i === 1 && <span className="text-muted"> ({onTarget[0]})</span>}
              </span>
              <div>
                <div className="mb-0.5 text-center text-[10px] uppercase tracking-[0.12em] text-muted">{label}</div>
                <div className="flex h-1 gap-0.5 overflow-hidden rounded-full">
                  <div className="ml-auto rounded-l-full transition-all duration-700" style={{ width: `${(hv / total) * 100}%`, background: meta.home.colors[0] }} />
                  <div className="rounded-r-full transition-all duration-700" style={{ width: `${(av / total) * 100}%`, background: meta.away.colors[0] }} />
                </div>
              </div>
              <span className="font-mono">
                {f(av)}
                {i === 1 && <span className="text-muted"> ({onTarget[1]})</span>}
              </span>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function WinChip({ p, meta }: { p: Record<string, number>; meta: Meta }) {
  return (
    <span className="flex items-center gap-1.5 normal-case tracking-normal" title="Live win probability">
      <span className="font-mono text-soft">{p[meta.home.code]}%</span>
      <span className="flex h-1.5 w-20 overflow-hidden rounded-full">
        <span style={{ width: `${p[meta.home.code]}%`, background: meta.home.colors[0] }} />
        <span className="bg-white/25" style={{ width: `${p.draw}%` }} />
        <span style={{ width: `${p[meta.away.code]}%`, background: meta.away.colors[0] }} />
      </span>
      <span className="font-mono text-soft">{p[meta.away.code]}%</span>
    </span>
  );
}

export function ControlGauge({ value }: { value: number | undefined }) {
  const v = value ?? 0.5;
  const label = v >= 0.65 ? "Chaotic" : v <= 0.4 ? "Controlled" : "Contested";
  const tone = v >= 0.65 ? "text-bad" : v <= 0.4 ? "text-good" : "text-warn";
  return (
    <Panel
      title="Control vs chaos"
      right={<span className="normal-case tracking-normal">last 5 min</span>}
    >
      <div className={`text-xl font-semibold ${tone}`}>
        {value === undefined ? "–" : label}
      </div>
      <div className="relative mt-2 h-1.5 rounded-full bg-gradient-to-r from-good via-warn to-bad">
        <div
          className="absolute -top-1 h-3.5 w-1 rounded bg-white shadow transition-all duration-700"
          style={{ left: `calc(${v * 100}% - 2px)` }}
        />
      </div>
      <div className="mt-1.5 flex justify-between text-[10px] uppercase tracking-[0.12em] text-muted">
        <span>Control</span>
        <span>Chaos</span>
      </div>
    </Panel>
  );
}

/* ---------- sidebar: commentary and agents ---------- */

export function CommentaryFeed({
  cards,
  meta,
  liveId,
  traces = [],
}: {
  cards: Overlay[];
  meta: Meta | null;
  liveId?: string;
  traces?: Trace[];
}) {
  if (!cards.length)
    return (
      <Empty text="The first caption airs at kick-off. After that, the agents comment on every moment that matters, and sum up the game whenever it goes quiet." />
    );
  return (
    <ol className="space-y-2.5">
      {[...cards].reverse().map((c) => {
        const color = clubColor(meta, c.content.team);
        const minute = Math.floor(c.anchor_t_ms / 60000) + 1;
        return (
          <li
            key={c.overlay_id}
            className={`rise rounded-lg border p-3 ${isRecap(c) ? "border-warn/40 bg-warn/5" : c.overlay_id === liveId ? "border-accent/50 bg-accent/5" : "border-line bg-panel-2/60"}`}
          >
            <div className="mb-1 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.14em]">
              <span className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-soft">
                {minute}'
              </span>
              <span style={{ color }}>
                {momentLabel(c.content.moment_type)}
              </span>
              {c.provenance.fallback && (
                <span className="text-warn">{(c.provenance as any).fast ? "instant" : "template"}</span>
              )}
            </div>
            <div dir={dirOf(c.content.lang)} className="text-[14px] font-semibold leading-snug">
              {c.content.headline}
            </div>
            <div dir={dirOf(c.content.lang)} className="mt-0.5 text-[13px] leading-snug text-soft">
              {c.content.body}
            </div>
            <WhyTrust card={c} meta={meta} trace={traces.find((x) => x.moment_id === c.moment_id)} />
          </li>
        );
      })}
    </ol>
  );
}

/** "Why trust this?": the facts behind one caption and every check it passed on the way to air. */
function WhyTrust({ card, meta, trace }: { card: Overlay; meta: Meta | null; trace?: Trace }) {
  const c = card.content;
  const why = (c.why ?? {}) as { claim?: string; reason?: string; cited?: Evidence[] };
  const facts = [...(why.cited ?? []), ...((c.evidence ?? []) as Evidence[])];
  const seen = new Set<string>();
  const rows = facts.filter((f) => {
    const k = `${f.metric}|${f.team}|${f.player}|${f.value}`;
    if (seen.has(k) || typeof f.value === "object") return false;
    seen.add(k);
    return true;
  });
  const who = (f: Evidence) =>
    f.player ? f.player : f.team ? (f.team === meta?.home.code ? meta.home.name : f.team === meta?.away.code ? meta.away.name : f.team) : "";
  const fast = (card.provenance as any).fast;
  return (
    <details className="group mt-2 text-[12px]">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-muted hover:text-soft">
        <svg viewBox="0 0 12 12" className="h-3 w-3 transition-transform group-open:rotate-90" fill="currentColor">
          <path d="M4 2.5 8 6l-4 3.5z" />
        </svg>
        Why trust this?
      </summary>
      <div className="mt-2 space-y-2 rounded-md border border-line bg-ink/60 p-2.5">
        {why.claim && (
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">Analyst's read</div>
            <div className="text-soft">
              {why.claim}
              {why.reason ? ` ${why.reason}` : ""}
            </div>
          </div>
        )}
        {rows.length > 0 && (
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">
              Numbers from the stats engine
            </div>
            <ul className="mt-0.5 space-y-0.5 font-mono text-[11px]">
              {rows.slice(0, 8).map((f, i) => (
                <li key={i} className="flex justify-between gap-2">
                  <span className="truncate text-soft">
                    {f.metric.replaceAll("_", " ")}
                    {who(f) && <span className="text-muted"> · {who(f)}</span>}
                    {f.window_s ? <span className="text-muted"> · last {Math.round(f.window_s / 60)} min</span> : null}
                  </span>
                  <span className="text-white">{String(f.value)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">Path to air</div>
          {fast ? (
            <div className="text-soft">
              Instant caption: a fixed template filled from the stats engine, so it can air the second the moment happens. The
              agents' version replaces it in the feed when it is ready.
            </div>
          ) : trace ? (
            <ol className="mt-0.5 space-y-0.5">
              {trace.steps.map((s, i) => (
                <li key={i} className="flex gap-2">
                  <span className={`w-16 shrink-0 capitalize ${STEP_TONE[s.status] ?? "text-soft"}`}>{s.agent}</span>
                  <span className="truncate text-muted" title={s.note}>
                    {s.status}
                    {s.note ? ` · ${s.note}` : ""}
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <div className="text-muted">Agent steps arrive with the translations.</div>
          )}
        </div>
      </div>
    </details>
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
  const rejected = steps.filter(
    (s) => s.agent === "verifier" && s.status === "reject",
  ).length;
  const templates = steps.filter((s) => s.agent === "template").length;
  const corrected = steps.filter(
    (s) => s.agent === "analyst" && s.status === "corrected",
  ).length;
  const total = traces.map((t) => t.steps.reduce((a, s) => a + s.ms, 0));
  const avg = total.length
    ? total.reduce((a, b) => a + b, 0) / total.length / 1000
    : 0;
  const tiles = [
    { label: "Moments aired", value: traces.length },
    { label: "Drafts sent back", value: rejected },
    { label: "Citations fixed", value: corrected },
    {
      label: "Avg agent time",
      value: traces.length ? `${avg.toFixed(1)}s` : "–",
    },
  ];
  return (
    <div className="mb-3 grid grid-cols-2 gap-2">
      {tiles.map((t) => (
        <div
          key={t.label}
          className="rounded-lg border border-line bg-panel-2/60 px-3 py-2"
        >
          <div className="font-mono text-lg font-medium">{t.value}</div>
          <div className="text-[10px] uppercase tracking-[0.12em] text-muted">
            {t.label}
          </div>
        </div>
      ))}
      {templates > 0 && (
        <div className="col-span-2 text-xs text-muted">
          {templates} moment(s) aired a verified template line.
        </div>
      )}
    </div>
  );
}

export function AgentTrace({ traces }: { traces: Trace[] }) {
  if (!traces.length)
    return (
      <Empty text="Each moment's path through the agents shows up here." />
    );
  return (
    <div className="space-y-2.5">
      {traces.map((t) => (
        <div
          key={t.moment_id}
          className="rise rounded-lg border border-line bg-panel-2/60 p-3"
        >
          <div className="mb-2 flex items-center justify-between text-[11px] font-semibold uppercase tracking-[0.14em]">
            <span>{momentLabel(t.type)}</span>
            <span className="font-mono text-muted">{t.minute}'</span>
          </div>
          <ol className="space-y-1.5 border-l border-line pl-3">
            {t.steps.map((s, i) => (
              <li key={i} className="text-xs">
                <div className="flex items-center gap-2">
                  <span className="w-16 font-semibold capitalize">
                    {s.agent}
                  </span>
                  <span className={STEP_TONE[s.status] ?? "text-soft"}>
                    {s.status}
                  </span>
                  <span className="ml-auto font-mono text-muted">
                    {s.ms >= 1000
                      ? `${(s.ms / 1000).toFixed(1)}s`
                      : `${s.ms}ms`}
                  </span>
                </div>
                {s.note && (
                  <div className="mt-0.5 line-clamp-2 text-[11px] leading-snug text-muted">
                    {s.note}
                  </div>
                )}
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="rounded-lg border border-dashed border-line p-4 text-sm text-muted">
      {text}
    </div>
  );
}

/* ---------- goal banner ---------- */

export function GoalBanner({
  goal,
  meta,
}: {
  goal: (Goal & { at: number }) | null;
  meta: Meta | null;
}) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (!goal) return;
    setShow(true);
    const t = window.setTimeout(() => setShow(false), 3200);
    return () => window.clearTimeout(t);
  }, [goal?.at]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!show || !goal || !meta) return null;
  const color = clubColor(meta, goal.team);
  const club = goal.team === meta.home.code ? meta.home.name : meta.away.name;
  return (
    <div className="goal-flash pointer-events-none absolute inset-0 grid place-items-center">
      <div className="text-center">
        <div
          className="goal-word text-[min(14cqw,120px)] font-extrabold italic leading-none tracking-tight"
          style={{ color: "white", textShadow: `0 0 40px ${color}` }}
        >
          GOAL
        </div>
        <div
          className="mt-2 inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-sm font-semibold"
          style={{ background: color }}
        >
          {playerName(meta, goal.player)} · {club} · {goal.minute}'
        </div>
      </div>
    </div>
  );
}

/* ---------- league ---------- */

export function ScoresTicker({ league }: { league: League | null }) {
  if (!league?.scores.length) return null;
  return (
    <div className="flex h-9 shrink-0 items-center gap-0 overflow-hidden border-b border-line bg-panel/80 text-[12px]">
      <span className="flex h-full shrink-0 items-center bg-accent px-3 font-bold uppercase tracking-[0.12em] text-ink">
        {league.league} · MD{league.matchday}
      </span>
      <div className="flex min-w-0 flex-1 items-center gap-6 overflow-x-auto px-4">
        {league.scores.map((s) => (
          <span
            key={s.id}
            className="flex shrink-0 items-center gap-2 font-medium"
          >
            <span>{s.home}</span>
            <span className="rounded bg-white/10 px-1.5 font-mono">
              {s.home_goals}-{s.away_goals}
            </span>
            <span>{s.away}</span>
            <span
              className={`font-mono text-[11px] ${s.finished ? "text-muted" : "text-good"}`}
            >
              {s.finished ? "FT" : `${s.minute}'`}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

export function LeagueTable({
  league,
  highlight,
}: {
  league: League | null;
  highlight: string[];
}) {
  if (!league)
    return <Empty text="The live table appears when the matchday kicks off." />;
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <div className="text-[13px] font-semibold">{league.league}</div>
        <div className="text-[11px] uppercase tracking-[0.12em] text-muted">
          Live table · MD{league.matchday}
        </div>
      </div>
      <table className="w-full text-[13px]">
        <thead>
          <tr className="text-[10px] uppercase tracking-[0.12em] text-muted">
            <th className="w-7 py-1 text-left">#</th>
            <th className="py-1 text-left">Club</th>
            <th className="w-8 py-1 text-right">P</th>
            <th className="w-10 py-1 text-right">GD</th>
            <th className="w-10 py-1 text-right">Pts</th>
          </tr>
        </thead>
        <tbody>
          {league.table.map((r) => (
            <tr
              key={r.code}
              className={`border-t border-line ${highlight.includes(r.code) ? "bg-accent/10" : ""}`}
            >
              <td className="py-1.5 font-mono">
                {r.pos}
                {!!r.moved && (
                  <span
                    className={`ml-0.5 text-[10px] ${r.moved > 0 ? "text-good" : "text-bad"}`}
                  >
                    {r.moved > 0 ? "▲" : "▼"}
                  </span>
                )}
              </td>
              <td className="py-1.5">
                <span className="flex items-center gap-2">
                  <i
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ background: r.color }}
                  />
                  <span
                    className={
                      highlight.includes(r.code) ? "font-semibold" : ""
                    }
                  >
                    {r.name}
                  </span>
                </span>
              </td>
              <td className="py-1.5 text-right font-mono text-soft">
                {r.played}
              </td>
              <td className="py-1.5 text-right font-mono text-soft">
                {r.gd > 0 ? `+${r.gd}` : r.gd}
              </td>
              <td className="py-1.5 text-right font-mono font-semibold">
                {r.points}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-4 mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">
        Matchday {league.matchday}
      </div>
      <div className="space-y-1.5">
        {league.scores.map((s) => (
          <div
            key={s.id}
            className="flex items-center justify-between rounded-lg border border-line bg-panel-2/60 px-3 py-2 text-[13px]"
          >
            <span className="min-w-0 flex-1 truncate">
              {league.table.find((r) => r.code === s.home)?.name}
            </span>
            <span className="mx-2 shrink-0 font-mono font-semibold">
              {s.home_goals} - {s.away_goals}
            </span>
            <span className="min-w-0 flex-1 truncate text-right">
              {league.table.find((r) => r.code === s.away)?.name}
            </span>
            <span
              className={`w-9 text-right font-mono text-[11px] ${s.finished ? "text-muted" : "text-good"}`}
            >
              {s.finished ? "FT" : `${s.minute}'`}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------- player card ---------- */

export function PlayerCard({
  stats,
  meta,
}: {
  stats: PlayerStats | null;
  meta: Meta | null;
}) {
  if (!stats) return null;
  const color = clubColor(meta, stats.team);
  const items = [
    ["Passes", stats.passes],
    [
      "Accuracy",
      stats.pass_accuracy_pct != null ? `${stats.pass_accuracy_pct}%` : "–",
    ],
    [
      "Distance",
      stats.distance_m != null
        ? `${(stats.distance_m / 1000).toFixed(1)} km`
        : "–",
    ],
    [
      "Top speed",
      stats.top_speed_kmh ? `${stats.top_speed_kmh.toFixed(1)} km/h` : "–",
    ],
    ["Shots", stats.shots],
    ["Goals", stats.goals],
  ];
  return (
    <div className="rise pointer-events-none absolute right-[2%] top-[4%] w-[190px] overflow-hidden rounded-lg bg-[rgba(7,11,20,.86)] ring-1 ring-white/10 backdrop-blur-md">
      <div
        className="flex items-center gap-2 px-3 py-2"
        style={{ borderTop: `3px solid ${color}` }}
      >
        <span className="text-[13px] font-semibold">{stats.name}</span>
        <span className="ml-auto text-[10px] uppercase tracking-[0.12em] text-muted">
          {stats.team}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 px-3 pb-2.5">
        {items.map(([k, v]) => (
          <div key={k as string}>
            <div className="font-mono text-[13px]">{v}</div>
            <div className="text-[9px] uppercase tracking-[0.12em] text-muted">
              {k}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------- recap ---------- */

export function RecapCard({
  card,
  meta,
  voice,
  lang,
}: {
  card: Overlay | undefined;
  meta: Meta | null;
  voice: boolean;
  lang: string;
}) {
  const [shown, setShown] = useState<Overlay | undefined>();
  useEffect(() => {
    if (!card) return;
    setShown(card);
    if (voice) speak(`${card.content.headline}. ${card.content.body}`, lang, true);
    const t = window.setTimeout(() => setShown(undefined), 14000);
    return () => window.clearTimeout(t);
  }, [card?.overlay_id]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!shown || !meta) return null;
  const c = shown.content;
  const score =
    (c.evidence as { metric: string; value: string }[]).find(
      (e) => e.metric === "score",
    )?.value ?? "";
  const [, hg, ag] = score.match(/(\d+)-(\d+)/) ?? [];
  return (
    <div className="rise absolute inset-0 grid place-items-center bg-black/55 backdrop-blur-[2px]">
      <div className="w-[min(620px,86%)] overflow-hidden rounded-xl bg-[rgba(7,11,20,.94)] shadow-2xl ring-1 ring-white/10">
        <div className="flex items-center justify-between border-b border-line px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.16em]">
          <span className="text-warn">{momentLabel(c.moment_type)}</span>
          <span className="flex items-center gap-1 text-good">
            <svg
              viewBox="0 0 12 12"
              className="h-2.5 w-2.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M2 6.5 5 9l5-6" />
            </svg>
            Verified
          </span>
        </div>
        <div className="flex items-center justify-center gap-5 px-5 pt-5">
          <span className="text-right text-[15px] font-semibold">
            {meta.home.name}
          </span>
          <span className="font-mono text-4xl">
            {hg ?? "-"} : {ag ?? "-"}
          </span>
          <span className="text-[15px] font-semibold">{meta.away.name}</span>
        </div>
        <div dir={dirOf(c.lang)} className="px-6 pt-4 pb-6 text-center">
          <div className="text-lg font-semibold">{c.headline}</div>
          <p className="mt-2 text-[14px] leading-relaxed text-soft">{c.body}</p>
        </div>
      </div>
    </div>
  );
}

/* ---------- ask pitchside ---------- */

type QA = {
  q: string;
  a?: string;
  verified?: boolean;
  checked?: number;
  pending?: boolean;
};

export function AskPanel({
  matchKey,
  lang,
  profile,
  suggestions,
  voice,
}: {
  matchKey: string | null;
  lang: string;
  profile: string;
  suggestions: string[];
  voice: boolean;
}) {
  const [log, setLog] = useState<QA[]>([]);
  const [text, setText] = useState("");
  const busy = log.some((x) => x.pending);

  async function ask(q: string) {
    if (!q.trim() || !matchKey || busy) return;
    setText("");
    setLog((l) => [...l, { q, pending: true }]);
    try {
      const r = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          match_key: matchKey,
          question: q,
          lang,
          profile,
        }),
      }).then((x) => x.json());
      const checked = (r.steps ?? []).filter(
        (s: { agent: string }) => s.agent === "verifier",
      ).length;
      setLog((l) =>
        l.map((x) =>
          x.q === q && x.pending
            ? { q, a: r.answer, verified: r.verified, checked }
            : x,
        ),
      );
      if (voice && r.verified) speak(r.answer, lang, true);
    } catch {
      setLog((l) =>
        l.map((x) =>
          x.q === q && x.pending
            ? { q, a: "Couldn't reach the studio. Try again.", verified: false }
            : x,
        ),
      );
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="text-[13px] font-semibold">Ask the studio</div>
      <div className="mb-3 text-[12px] text-muted">
        The Pundit agent answers from live match data. Every number is checked
        before you see it.
      </div>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => ask(s)}
            disabled={busy || !matchKey}
            className="rounded-full border border-line bg-panel-2/60 px-3 py-1 text-[12px] text-soft transition-colors hover:border-accent hover:text-white disabled:opacity-40"
          >
            {s}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
        {log.map((x, i) => (
          <div key={i} className="rise space-y-1.5">
            <div dir="auto" className="ml-8 rounded-lg rounded-br-sm bg-accent/15 px-3 py-2 text-[13px]">
              {x.q}
            </div>
            <div dir="auto" className="mr-4 rounded-lg rounded-bl-sm border border-line bg-panel-2/60 px-3 py-2 text-[13px] leading-relaxed text-soft">
              {x.pending ? (
                <span className="flex items-center gap-2 text-muted">
                  <i className="live-dot h-1.5 w-1.5 rounded-full bg-accent" />{" "}
                  Pundit is checking the numbers…
                </span>
              ) : (
                <>
                  {x.a}
                  <div
                    className={`mt-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] ${x.verified ? "text-good" : "text-warn"}`}
                  >
                    {x.verified
                      ? `✓ Verified${x.checked && x.checked > 1 ? " after a rewrite" : ""}`
                      : "Not verified"}
                  </div>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          ask(text);
        }}
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={
            matchKey
              ? "Ask about the match, a player or the table…"
              : "Kick off to ask questions"
          }
          className="min-w-0 flex-1 rounded-lg border border-line bg-ink px-3 py-2 text-[13px] outline-none focus:border-accent"
        />
        <button
          disabled={busy || !text.trim()}
          className="rounded-lg bg-accent px-3 text-[13px] font-semibold text-ink disabled:opacity-40"
        >
          Ask
        </button>
      </form>
    </div>
  );
}

/* ---------- goal replay ---------- */

function ReplayLayer({ replay, meta }: { replay: Replay; meta: Meta | null }) {
  const pts = replay.path.map((p) => `${p.x.toFixed(1)},${(68 - p.y).toFixed(1)}`);
  const d = `M${pts.join(" L")}`;
  const color = clubColor(meta, replay.team);
  const dur = Math.max(2.5, replay.path.length * 0.55);
  return (
    <g key={replay.id}>
      <rect x="-3" y="-3" width="111" height="74" fill="black" opacity="0.35" />
      <path d={d} fill="none" stroke={color} strokeWidth="0.7" strokeLinecap="round" strokeLinejoin="round" pathLength={1} strokeDasharray="1" strokeDashoffset="1">
        <animate attributeName="stroke-dashoffset" from="1" to="0" dur={`${dur}s`} fill="freeze" />
      </path>
      {replay.path.slice(0, -1).map((p, i) => (
        <circle key={i} cx={p.x} cy={68 - p.y} r="1.1" fill={color} stroke="white" strokeWidth="0.25" opacity="0">
          <animate attributeName="opacity" from="0" to="1" begin={`${(i / replay.path.length) * dur}s`} dur="0.2s" fill="freeze" />
        </circle>
      ))}
      <circle r="1.1" fill="white">
        <animateMotion path={d} dur={`${dur}s`} fill="freeze" />
      </circle>
    </g>
  );
}

/* ---------- studio (producer) mode ---------- */

export type Decision = { status: "approved" | "rejected"; headline?: string; body?: string; edited?: boolean };

export function ProducerQueue({
  cards,
  decisions,
  decide,
  matchKey,
  meta,
}: {
  cards: Overlay[];
  decisions: Record<string, Decision>;
  decide: (id: string, d: Decision) => void;
  matchKey: string | null;
  meta: Meta | null;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState({ headline: "", body: "" });
  const [problems, setProblems] = useState<string[]>([]);
  const [checking, setChecking] = useState(false);
  if (!cards.length) return <Empty text="AI captions wait here for your approval before they go on air." />;

  async function approveEdit(id: string) {
    setChecking(true);
    const r = await fetch("/api/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ match_key: matchKey, text: `${draft.headline}. ${draft.body}` }),
    })
      .then((x) => x.json())
      .catch(() => ({ ok: false, problems: ["couldn't reach the verifier"] }));
    setChecking(false);
    if (r.ok) {
      decide(id, { status: "approved", headline: draft.headline, body: draft.body, edited: true });
      setEditing(null);
      setProblems([]);
    } else setProblems(r.problems);
  }

  return (
    <div>
      <div className="mb-3 text-[12px] text-muted">
        Studio mode: nothing airs until you approve it. Edits are checked by the Verifier against the live match too.
      </div>
      <ol className="space-y-2.5">
        {[...cards].reverse().map((c) => {
          const d = decisions[c.overlay_id];
          const minute = Math.floor(c.anchor_t_ms / 60000) + 1;
          const isEditing = editing === c.overlay_id;
          return (
            <li
              key={c.overlay_id}
              className={`rise rounded-lg border p-3 ${!d ? "border-accent/40 bg-accent/5" : d.status === "approved" ? "border-good/30 bg-good/5" : "border-line bg-panel-2/40 opacity-60"}`}
            >
              <div className="mb-1 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.14em]">
                <span className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-soft">{minute}'</span>
                <span style={{ color: clubColor(meta, c.content.team) }}>{momentLabel(c.content.moment_type)}</span>
                <span className={`ml-auto ${!d ? "text-accent" : d.status === "approved" ? "text-good" : "text-muted"}`}>
                  {!d ? "awaiting approval" : d.status === "approved" ? (d.edited ? "on air · edited" : "on air") : "rejected"}
                </span>
              </div>
              {isEditing ? (
                <div className="space-y-2">
                  <input
                    value={draft.headline}
                    onChange={(e) => setDraft({ ...draft, headline: e.target.value })}
                    className="w-full rounded-md border border-line bg-ink px-2 py-1.5 text-[13px] font-semibold outline-none focus:border-accent"
                  />
                  <textarea
                    value={draft.body}
                    rows={3}
                    onChange={(e) => setDraft({ ...draft, body: e.target.value })}
                    className="w-full resize-none rounded-md border border-line bg-ink px-2 py-1.5 text-[13px] outline-none focus:border-accent"
                  />
                  {problems.length > 0 && (
                    <ul className="space-y-0.5 text-[12px] text-bad">
                      {problems.map((p) => (
                        <li key={p}>✕ {p}</li>
                      ))}
                    </ul>
                  )}
                  <div className="flex gap-2">
                    <button
                      onClick={() => approveEdit(c.overlay_id)}
                      disabled={checking}
                      className="rounded-md bg-good px-3 py-1 text-[12px] font-semibold text-ink disabled:opacity-50"
                    >
                      {checking ? "Checking…" : "Verify & put on air"}
                    </button>
                    <button onClick={() => setEditing(null)} className="rounded-md border border-line px-3 py-1 text-[12px] text-soft">
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="text-[14px] font-semibold leading-snug">{d?.headline ?? c.content.headline}</div>
                  <div className="mt-0.5 text-[13px] leading-snug text-soft">{d?.body ?? c.content.body}</div>
                  {!d && (
                    <div className="mt-2 flex gap-2">
                      <button onClick={() => decide(c.overlay_id, { status: "approved" })} className="rounded-md bg-good px-3 py-1 text-[12px] font-semibold text-ink">
                        Approve
                      </button>
                      <button
                        onClick={() => {
                          setEditing(c.overlay_id);
                          setDraft({ headline: c.content.headline, body: c.content.body });
                          setProblems([]);
                        }}
                        className="rounded-md border border-line px-3 py-1 text-[12px] text-soft hover:text-white"
                      >
                        Edit
                      </button>
                      <button onClick={() => decide(c.overlay_id, { status: "rejected" })} className="rounded-md border border-line px-3 py-1 text-[12px] text-muted hover:text-bad">
                        Reject
                      </button>
                    </div>
                  )}
                </>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/* ---------- live events feed ---------- */

function eventText(e: MatchEvent, meta: Meta): { icon: string; text: string } | null {
  const who = (id?: string) => (id ? playerName(meta, id) : "");
  const x = e as any;
  switch (e.type) {
    case "goal":
      return { icon: "⚽", text: `GOAL! ${who(e.player)}${x.assist_player ? `, assist ${who(x.assist_player)}` : ""}` };
    case "shot":
      if (e.outcome === "goal") return null;
      return {
        icon: "◎",
        text: `${({ saved: "Shot saved", blocked: "Shot blocked", off_target: "Shot wide" } as Record<string, string>)[e.outcome ?? ""] ?? "Shot"}: ${who(e.player)} (${Math.round(x.shot_speed_kmh)} km/h)`,
      };
    case "card":
      return { icon: x.card === "red" ? "🟥" : "🟨", text: `${x.card === "red" ? "Red" : "Yellow"} card: ${who(e.player)}` };
    case "substitution":
      return { icon: "⇄", text: `On ${who(x.player_on)}, off ${who(e.player)}` };
    case "corner":
      return { icon: "⚑", text: `Corner, ${e.team === meta.home.code ? meta.home.name : meta.away.name}` };
    case "foul":
      return { icon: "!", text: `Foul by ${who(e.player)}` };
    case "dribble":
      return { icon: "↗", text: `${who(e.player)} beats ${who(x.past_player)}` };
    case "tackle":
      return { icon: "✕", text: `Tackle won by ${who(e.player)}` };
    case "interception":
      return { icon: "✋", text: `Interception: ${who(e.player)}` };
    case "period_start":
      return { icon: "▶", text: e.period === 1 ? "Kick-off" : "Second half under way" };
    case "period_end":
      return { icon: "⏸", text: e.period === 1 ? "Half-time" : "Full-time" };
    default:
      return null;
  }
}

export function LiveEvents({ feed, meta }: { feed: MatchEvent[]; meta: Meta | null }) {
  return (
    <Panel title="Live events">
      {!meta || !feed.length ? (
        <div className="text-sm text-muted">Waiting for kick-off</div>
      ) : (
        <ol className="h-full space-y-1 overflow-hidden">
          {feed.slice(0, 7).map((e) => {
            const line = eventText(e, meta);
            if (!line) return null;
            return (
              <li key={e.event_id} className="rise flex items-center gap-2 text-[12px]">
                <span className="w-7 shrink-0 font-mono text-muted">{e.minute}'</span>
                <i className="h-2 w-2 shrink-0 rounded-full" style={{ background: clubColor(meta, e.team) }} />
                <span className="w-4 shrink-0 text-center">{line.icon}</span>
                <span className={`truncate ${e.type === "goal" ? "font-semibold text-white" : "text-soft"}`}>{line.text}</span>
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}

/* ---------- full time ---------- */

export function FullTime({
  meta,
  snapshot,
  league,
  recap,
  onLeave,
}: {
  meta: Meta;
  snapshot: Snapshot | null;
  league: League | null;
  recap: Overlay | undefined;
  onLeave: () => void;
}) {
  const s = snapshot?.score ?? {};
  const pos = (code: string) => league?.table.find((r) => r.code === code);
  return (
    <div className="rise absolute inset-0 z-10 grid place-items-center bg-black/65 backdrop-blur-sm">
      <div className="w-[min(640px,90%)] rounded-2xl bg-[rgba(7,11,20,.96)] p-6 shadow-2xl ring-1 ring-white/10">
        <div className="text-center text-[11px] font-semibold uppercase tracking-[0.2em] text-warn">Full-time</div>
        <div className="mt-3 flex items-center justify-center gap-5">
          <Crest code={meta.home.code} colors={meta.home.colors} size={44} />
          <span className="font-mono text-5xl">
            {s[meta.home.code] ?? 0} : {s[meta.away.code] ?? 0}
          </span>
          <Crest code={meta.away.code} colors={meta.away.colors} size={44} />
        </div>
        <div className="mt-1 text-center text-sm text-soft">
          {meta.home.name} v {meta.away.name}
        </div>
        {recap && (
          <div dir={dirOf(recap.content.lang)} className="mt-4 rounded-lg border border-line bg-panel-2/60 p-4">
            <div className="font-semibold">{recap.content.headline}</div>
            <p className="mt-1 text-[14px] leading-relaxed text-soft">{recap.content.body}</p>
          </div>
        )}
        {league && (
          <div className="mt-4 grid grid-cols-2 gap-3 text-center text-[13px]">
            {[meta.home.code, meta.away.code].map((c) => (
              <div key={c} className="rounded-lg border border-line px-3 py-2">
                <div className="font-mono text-2xl">{pos(c)?.pos}</div>
                <div className="text-[11px] uppercase tracking-[0.12em] text-muted">
                  {pos(c)?.name} · {pos(c)?.points} pts
                </div>
              </div>
            ))}
          </div>
        )}
        <button onClick={onLeave} className="mt-5 w-full rounded-xl bg-accent py-2.5 font-semibold text-ink">
          Watch another match
        </button>
      </div>
    </div>
  );
}

/* ---------- my metric ---------- */

export const METRICS: { id: string; label: string; note: string }[] = [
  { id: "possession", label: "Possession", note: "share of the ball, whole match" },
  { id: "chances", label: "Chance quality", note: "expected goals from every shot" },
  { id: "shots", label: "Shots", note: "attempts on goal" },
  { id: "pressing", label: "Pressing", note: "balls won in the opponent's half" },
  { id: "win", label: "Win probability", note: "live, from the score, time left and chance quality" },
];

function metricValues(metric: string, s: Snapshot, home: string, away: string): [number, number, (v: number) => string] {
  const tm = s.teams ?? {};
  switch (metric) {
    case "chances":
      return [s.xg[home] ?? 0, s.xg[away] ?? 0, (v) => v.toFixed(2)];
    case "shots":
      return [tm[home]?.shots ?? 0, tm[away]?.shots ?? 0, String];
    case "pressing":
      return [tm[home]?.high_regains ?? 0, tm[away]?.high_regains ?? 0, String];
    case "win":
      return [s.win_probability_pct?.[home] ?? 0, s.win_probability_pct?.[away] ?? 0, (v) => `${v}%`];
    default:
      return [s.possession_pct[home] ?? 0, s.possession_pct[away] ?? 0, (v) => `${v}%`];
  }
}

/** The one number a "my metric" viewer follows, live, in the corner of the pitch. */
export function MetricTracker({ metric, snapshot, meta }: { metric: string; snapshot: Snapshot | null; meta: Meta | null }) {
  const [history, setHistory] = useState<[number, number][]>([]);
  const info = METRICS.find((m) => m.id === metric) ?? METRICS[0];
  const values = snapshot && meta ? metricValues(metric, snapshot, meta.home.code, meta.away.code) : null;
  useEffect(() => {
    if (values) setHistory((h) => [...h.slice(-59), [values[0], values[1]]]);
  }, [snapshot?.t_ms]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => setHistory([]), [metric]);
  if (!values || !meta) return null;
  const [hv, av, fmt] = values;
  const max = Math.max(1e-6, ...history.flat());
  const path = (i: 0 | 1) =>
    history.map((p, k) => `${k ? "L" : "M"}${((k / Math.max(1, history.length - 1)) * 100).toFixed(1)},${(28 - (p[i] / max) * 26).toFixed(1)}`).join(" ");
  return (
    <div className="pointer-events-none absolute right-[3%] top-[4%] w-56 rounded-lg bg-[rgba(7,11,20,.86)] px-3 py-2 shadow-2xl ring-1 ring-white/10 backdrop-blur-md">
      <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-accent">My metric · {info.label}</div>
      <div className="mt-1 flex items-baseline justify-between font-mono">
        <span className="text-xl" style={{ color: meta.home.colors[0] }}>{fmt(hv)}</span>
        <span className="text-[11px] text-muted">{meta.home.code} v {meta.away.code}</span>
        <span className="text-xl" style={{ color: meta.away.colors[0] }}>{fmt(av)}</span>
      </div>
      {history.length > 1 && (
        <svg viewBox="0 0 100 30" className="mt-1 h-7 w-full" preserveAspectRatio="none">
          <path d={path(0)} fill="none" stroke={meta.home.colors[0]} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
          <path d={path(1)} fill="none" stroke={meta.away.colors[0]} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
        </svg>
      )}
      <div className="mt-0.5 text-[10px] text-muted">{info.note}</div>
    </div>
  );
}

/* ---------- analyst: last action ---------- */

/** What the analyst view adds to every touch: how hard the pass was, how fast the ball went, the chance quality. */
export function LastAction({ e, meta }: { e: MatchEvent | null; meta: Meta | null }) {
  if (!e || !meta) return null;
  const d = e as any;
  const name = [...meta.home.players, ...meta.away.players].find((p) => p.id === e.player)?.name.split(" ").at(-1) ?? "";
  const cells: [string, string][] = [];
  const cap = (x?: string) => (x ? x[0].toUpperCase() + x.slice(1) : "");
  if (e.type === "shot") {
    cells.push(["Shot", cap(e.outcome)], ["xG", (d.xg ?? 0).toFixed(2)], ["Speed", `${Math.round(d.shot_speed_kmh ?? 0)} km/h`]);
    if (d.body_part) cells.push(["With", cap(d.body_part)]);
  } else if (e.type === "carry") {
    cells.push(["Carry", cap(e.outcome ?? "complete")], ["Speed", `${Math.round(d.speed_kmh ?? 0)} km/h`]);
  } else {
    cells.push([e.type === "clearance" ? "Clearance" : "Pass", cap(e.outcome)]);
    if (d.length_m) cells.push(["Length", `${Math.round(d.length_m)} m`]);
    if (d.difficulty !== undefined) cells.push(["Difficulty", `${d.difficulty}/100`]);
    if (d.ball_speed_kmh) cells.push(["Ball", `${Math.round(d.ball_speed_kmh)} km/h`]);
    if (d.under_pressure) cells.push(["", "under pressure"]);
  }
  return (
    <div className="pointer-events-none absolute left-[3%] top-[4%] flex items-center gap-3 rounded-lg bg-[rgba(7,11,20,.82)] px-3 py-1.5 text-[11px] shadow-xl ring-1 ring-white/10 backdrop-blur-md">
      <i className="h-2 w-2 rounded-full" style={{ background: clubColor(meta, e.team) }} />
      <span className="font-semibold">{name}</span>
      {cells.map(([k, v], i) => (
        <span key={i} className="flex gap-1">
          {k && <span className="uppercase tracking-[0.1em] text-muted">{k}</span>}
          <span className="font-mono text-white">{v}</span>
        </span>
      ))}
    </div>
  );
}

/* ---------- how it works ---------- */

const REPO = "https://github.com/Wolverine-07/pitchside";

/** The proof page: how a caption is made, and what was measured, including where the agent team is not better. */
export function ProofModal({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  const stages = [
    ["Ingest", "A simulator streams every pass, tackle, shot and sprint, with positions and speeds. Three other games of the matchday run alongside."],
    ["Interpret", "A deterministic stats engine computes possession, pass difficulty, xG, pressing, momentum, control vs chaos, win probability and the live table, and flags the moments that matter."],
    ["Explain", "The Analyst agent works out why the moment matters, pulling numbers from the stats engine over MCP. Every number it cites is matched to the engine before it is kept."],
    ["Show", "Each caption becomes a timed overlay (JSON schema in the repo) that any graphics system could draw. This page is one renderer."],
    ["Personalize", "The Persona agent rewrites each caption for a casual fan, an analyst, a club supporter, a player follower and a metric follower; the Linguist translates into up to three languages."],
  ];
  const agents = [
    ["Director", "picks what goes on air"],
    ["Analyst", "explains why, with MCP stats tools"],
    ["Narrator", "writes the caption"],
    ["Verifier", "plain code: checks every number, name and minute; two rewrites, then a safe template"],
    ["Persona", "one rewrite per viewer type, re-verified"],
    ["Linguist", "translation, re-verified; Azure Translator if it fails twice"],
    ["Pundit", "answers viewers' questions, numbers verified"],
  ];
  const results = [
    ["0 of 104", "captions with a wrong number, single agent and agent team alike (5 matches, same model)"],
    ["17% → 0%", "captions breaking broadcast style rules (mostly \"at 55 minutes\" phrasing), single agent vs the team"],
    ["29", "agent drafts the Verifier sent back before they reached a viewer"],
    ["102 / 104", "Foundry groundedness for the team (single agent: 103 / 104)"],
    ["179 / 180", "pairs of viewers who got different captions for the same moment"],
    ["0 s", "for goals, cards and big saves (instant verified caption); agent captions follow in about 7 to 10 s"],
  ];
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="max-h-[90vh] w-[min(860px,100%)] overflow-y-auto rounded-2xl border border-line bg-panel p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold">How Pitchside works</h2>
            <p className="mt-1 text-[13px] text-soft">
              The stats engine owns every number. The agents only write words, and nothing they write airs until code has checked it.
            </p>
          </div>
          <button onClick={onClose} className="rounded-lg border border-line px-3 py-1 text-[13px] text-soft hover:text-white">
            Close
          </button>
        </div>

        <ol className="mt-5 grid gap-2 sm:grid-cols-5">
          {stages.map(([name, text], i) => (
            <li key={name} className="rounded-lg border border-line bg-panel-2/60 p-3">
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-accent">
                {i + 1}. {name}
              </div>
              <p className="mt-1 text-[12px] leading-snug text-soft">{text}</p>
            </li>
          ))}
        </ol>

        <div className="mt-5 grid gap-5 md:grid-cols-2">
          <div>
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">Seven agents, Microsoft Agent Framework</h3>
            <ul className="mt-2 space-y-1 text-[13px]">
              {agents.map(([n, d]) => (
                <li key={n}>
                  <span className="font-semibold">{n}</span> <span className="text-soft">{d}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-[12px] text-muted">
              Model: gpt-4.1-mini on Microsoft Foundry. Every agent call is traced to Application Insights. Voices: Azure AI Speech.
              Backup translation: Azure AI Translator. Runs on Azure Container Apps.
            </p>
          </div>
          <div>
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">What I measured</h3>
            <ul className="mt-2 space-y-1.5 text-[13px]">
              {results.map(([n, d]) => (
                <li key={d} className="flex gap-3">
                  <span className="w-20 shrink-0 font-mono font-semibold text-white">{n}</span>
                  <span className="text-soft">{d}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-[12px] text-muted">
              Honest limits: the team is no better than one agent at getting numbers right, and it is slower (8.8 s vs 1.2 s per
              caption). What it adds is the explanation, the checks, the audience versions and a trace for every line. All data is
              synthetic.
            </p>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap gap-2 border-t border-line pt-4 text-[13px]">
          <a className="rounded-lg border border-line px-3 py-1.5 text-soft hover:border-accent hover:text-white" href={REPO} target="_blank" rel="noreferrer">
            Code on GitHub
          </a>
          <a className="rounded-lg border border-line px-3 py-1.5 text-soft hover:border-accent hover:text-white" href={`${REPO}/tree/main/backend/evals`} target="_blank" rel="noreferrer">
            Evaluation scripts and results
          </a>
          <a className="rounded-lg border border-line px-3 py-1.5 text-soft hover:border-accent hover:text-white" href={`${REPO}/blob/main/schemas/overlay.schema.json`} target="_blank" rel="noreferrer">
            Overlay schema
          </a>
        </div>
      </div>
    </div>
  );
}
