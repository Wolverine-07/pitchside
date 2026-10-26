import { useEffect, useRef, useState } from "react";
import type { Meta, Overlay, Snapshot, Trace } from "./types";
import { pitchPos, type BallPoint } from "./useMatch";

const clubColor = (meta: Meta | null, code?: string | null) =>
  meta && code ? (code === meta.home.code ? meta.home.colors[0] : meta.away.colors[0]) : "#8b98b3";

export function ScoreBug({ meta, snapshot, minute, added }: { meta: Meta | null; snapshot: Snapshot | null; minute: number; added?: number }) {
  if (!meta) return null;
  const s = snapshot?.score ?? { [meta.home.code]: 0, [meta.away.code]: 0 };
  return (
    <div className="absolute left-3 top-3 flex items-stretch overflow-hidden rounded-md text-sm font-semibold shadow-lg">
      <span className="px-2 py-1" style={{ background: meta.home.colors[0] }}>{meta.home.code}</span>
      <span className="bg-black/80 px-3 py-1 tabular-nums">
        {s[meta.home.code]} – {s[meta.away.code]}
      </span>
      <span className="px-2 py-1" style={{ background: meta.away.colors[0] }}>{meta.away.code}</span>
      <span className="bg-white/90 px-2 py-1 text-ink tabular-nums">
        {minute}
        {added ? `+${added}` : ""}'
      </span>
    </div>
  );
}

// Same 4-3-3 shape as the simulator: x from own goal line, y from right touchline.
const SHAPE: Record<number, [number, number]> = {
  1: [5, 34], 2: [30, 60], 4: [22, 44], 5: [22, 24], 3: [30, 8], 6: [42, 34], 8: [52, 46], 10: [52, 22],
  7: [76, 58], 9: [84, 34], 11: [76, 10], 13: [5, 34], 15: [22, 34], 14: [52, 34], 17: [76, 58], 19: [84, 34],
};

function PlayerDots({ meta, onPitch, ball, focus }: { meta: Meta; onPitch: string[]; ball?: BallPoint; focus?: string }) {
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
        const isFocus = p.id === focus;
        return (
          <g key={p.id} style={{ transition: "transform 700ms ease-out" }} transform={`translate(${x} ${68 - y})`}>
            {isFocus && <circle r="2.6" fill="none" stroke="#ffd166" strokeWidth="0.35" />}
            <circle r="1.55" fill={color} stroke="white" strokeOpacity="0.8" strokeWidth="0.2" />
            <text y="0.62" textAnchor="middle" fontSize="1.6" fontWeight="700" fill="white">
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
  const recentTags = tags.filter((t) => clockMs - t.anchor_t_ms < 25_000);
  return (
    <div
      className="relative mx-auto aspect-[105/68] w-full overflow-hidden rounded-xl border border-line bg-pitch"
      style={{ maxWidth: "calc(58vh * 105 / 68)" }}
    >
      <svg viewBox="-2 -2 109 72" className="absolute inset-0 h-full w-full">
        <g fill="none" stroke="var(--color-pitch-line)" strokeWidth="0.35">
          <rect x="0" y="0" width="105" height="68" />
          <line x1="52.5" y1="0" x2="52.5" y2="68" />
          <circle cx="52.5" cy="34" r="9.15" />
          <rect x="0" y="13.84" width="16.5" height="40.32" />
          <rect x="88.5" y="13.84" width="16.5" height="40.32" />
          <rect x="0" y="24.84" width="5.5" height="18.32" />
          <rect x="99.5" y="24.84" width="5.5" height="18.32" />
          <rect x="-1.5" y="30.34" width="1.5" height="7.32" />
          <rect x="105" y="30.34" width="1.5" height="7.32" />
        </g>
        {meta && <PlayerDots meta={meta} onPitch={onPitch} ball={ball} focus={focus} />}
        {recent.slice(1).map((p, i) => (
          <line
            key={i}
            x1={recent[i].x}
            y1={68 - recent[i].y}
            x2={p.x}
            y2={68 - p.y}
            stroke="white"
            strokeOpacity={0.1 + i * 0.12}
            strokeWidth="0.35"
          />
        ))}
        {ball && (
          <g style={{ transition: "transform 300ms linear" }} transform={`translate(${ball.x} ${68 - ball.y})`}>
            <circle r="2.2" fill={clubColor(meta, ball.team)} opacity="0.35" />
            <circle r="1.1" fill="white" />
          </g>
        )}
        {recentTags.map((t) => {
          const team = t.content.player.split("-")[0];
          const p = pitchPos(meta, team, t.content.x ?? 52, t.content.y ?? 34);
          return (
            <g key={t.overlay_id} transform={`translate(${p.x} ${68 - p.y})`}>
              <circle r="0.9" fill={clubColor(meta, team)} stroke="white" strokeWidth="0.25" />
              <g transform="translate(1.6 -4.2)">
                <rect width="24" height="3.6" rx="0.8" fill="rgba(5,10,20,0.85)" stroke={clubColor(meta, team)} strokeWidth="0.25" />
                <text x="1" y="2.55" fontSize="2" fill="white">
                  {t.content.name.split(" ").at(-1)} · {t.content.speed_kmh} km/h
                </text>
              </g>
            </g>
          );
        })}
      </svg>
      {children}
    </div>
  );
}

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

/** Shows the newest card for the viewer's profile for a few seconds, like a lower third. */
export function InsightCard({ card, voice, lang, meta }: { card: Overlay | undefined; voice: boolean; lang: string; meta: Meta | null }) {
  const [shown, setShown] = useState<Overlay | undefined>();
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (!card) return;
    setShown(card);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setShown(undefined), 9000);
    if (voice) speak(card.content.body, lang);
  }, [card?.overlay_id]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!shown) return null;
  const c = shown.content;
  return (
    <div key={shown.overlay_id} className="card-in absolute inset-x-3 bottom-3 rounded-lg border-l-4 bg-black/80 px-4 py-3 shadow-2xl backdrop-blur" style={{ borderColor: clubColor(meta, c.team) }}>
      <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-muted">
        <span>{c.moment_type.replace("_", " ")}</span>
        <span className="rounded bg-good/15 px-1.5 py-0.5 text-good">verified</span>
        {shown.provenance.fallback && <span className="rounded bg-amber-400/15 px-1.5 py-0.5 text-amber-300">template</span>}
      </div>
      <div className="mt-1 text-lg font-semibold leading-tight">{c.headline}</div>
      <div className="mt-0.5 text-[15px] leading-snug text-slate-200">{c.body}</div>
    </div>
  );
}

export function MomentumStrip({ data, meta }: { data: { t: number; v: number }[]; meta: Meta | null }) {
  const w = 600,
    h = 56;
  const tMax = Math.max(95 * 60_000, data.at(-1)?.t ?? 0);
  const pts = data.map((d) => [(d.t / tMax) * w, h / 2 - (d.v / 100) * (h / 2 - 2)]);
  const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  return (
    <div className="rounded-lg border border-line bg-panel px-3 py-2">
      <div className="mb-1 flex justify-between text-[11px] uppercase tracking-wider text-muted">
        <span>Momentum</span>
        <span>
          <span style={{ color: clubColor(meta, meta?.home.code) }}>▲ {meta?.home.code}</span>{" "}
          <span style={{ color: clubColor(meta, meta?.away.code) }}>▼ {meta?.away.code}</span>
        </span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="h-14 w-full" preserveAspectRatio="none">
        <line x1="0" y1={h / 2} x2={w} y2={h / 2} stroke="var(--color-line)" />
        <line x1={w * (45 / 95)} y1="0" x2={w * (45 / 95)} y2={h} stroke="var(--color-line)" strokeDasharray="3 3" />
        {pts.length > 1 && <polyline points={line} fill="none" stroke="var(--color-accent)" strokeWidth="1.6" />}
      </svg>
    </div>
  );
}

export function StatRow({ label, home, away, meta, fmt = (v: number) => String(v) }: { label: string; home: number; away: number; meta: Meta | null; fmt?: (v: number) => string }) {
  const total = home + away || 1;
  return (
    <div className="text-sm">
      <div className="flex justify-between tabular-nums">
        <span>{fmt(home)}</span>
        <span className="text-xs uppercase tracking-wider text-muted">{label}</span>
        <span>{fmt(away)}</span>
      </div>
      <div className="mt-1 flex h-1.5 overflow-hidden rounded-full bg-line">
        <div style={{ width: `${(home / total) * 100}%`, background: clubColor(meta, meta?.home.code) }} />
        <div style={{ width: `${(away / total) * 100}%`, background: clubColor(meta, meta?.away.code) }} />
      </div>
    </div>
  );
}

export function ChaosGauge({ value }: { value: number }) {
  const label = value >= 0.65 ? "Chaos" : value <= 0.4 ? "Control" : "Contested";
  return (
    <div className="text-sm">
      <div className="flex justify-between text-xs uppercase tracking-wider text-muted">
        <span>Control</span>
        <span className="text-slate-200">
          {label} · {Math.round(value * 100)}
        </span>
        <span>Chaos</span>
      </div>
      <div className="relative mt-1 h-1.5 rounded-full bg-gradient-to-r from-good via-amber-300 to-bad">
        <div className="absolute -top-1 h-3.5 w-1 rounded bg-white shadow" style={{ left: `calc(${value * 100}% - 2px)` }} />
      </div>
    </div>
  );
}

const STATUS_STYLE: Record<string, string> = {
  ok: "bg-good/15 text-good",
  pass: "bg-good/15 text-good",
  rule: "bg-slate-500/20 text-slate-300",
  corrected: "bg-amber-400/15 text-amber-300",
  fallback: "bg-amber-400/15 text-amber-300",
  reject: "bg-bad/15 text-bad",
};

export function AgentTrace({ traces }: { traces: Trace[] }) {
  return (
    <div className="flex h-full flex-col rounded-xl border border-line bg-panel">
      <div className="border-b border-line px-4 py-3">
        <div className="font-semibold">Agent trace</div>
        <div className="text-xs text-muted">Every moment's path through the agents, newest first</div>
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto p-3">
        {traces.length === 0 && <div className="text-sm text-muted">Waiting for the first moment…</div>}
        {traces.map((t) => (
          <div key={t.moment_id} className="card-in rounded-lg border border-line bg-ink/60 p-2.5">
            <div className="mb-1.5 flex justify-between text-xs">
              <span className="font-semibold uppercase tracking-wider">{t.type.replace("_", " ")}</span>
              <span className="text-muted">{t.minute}'</span>
            </div>
            <ol className="space-y-1">
              {t.steps.map((s, i) => (
                <li key={i} className="flex items-start gap-2 text-xs">
                  <span className={`w-[74px] shrink-0 rounded px-1.5 py-0.5 text-center capitalize ${STATUS_STYLE[s.status] ?? ""}`}>{s.agent}</span>
                  <span className="min-w-0 flex-1 text-slate-300">
                    <span className="text-muted">{s.status}</span>
                    {s.note ? ` · ${s.note}` : ""}
                  </span>
                  <span className="shrink-0 tabular-nums text-muted">{s.ms >= 1000 ? `${(s.ms / 1000).toFixed(1)}s` : `${s.ms}ms`}</span>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>
    </div>
  );
}
