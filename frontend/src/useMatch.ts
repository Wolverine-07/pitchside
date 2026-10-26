import { useCallback, useRef, useState } from "react";
import type { Goal, League, MatchEvent, Meta, Overlay, PlayerStats, Shot, Snapshot, Trace } from "./types";

export type Settings = {
  seed: number;
  storyline: string;
  speed: number;
  club: string;
  player: string;
  langs: string[];
};

export type BallPoint = { x: number; y: number; team?: string; type: string };
export type Replay = { id: number; minute: number; team: string; player: string; path: BallPoint[] };

export type MatchView = {
  status: "idle" | "connecting" | "live" | "done" | "error";
  provider: string | null;
  meta: Meta | null;
  clock: { t_ms: number; minute: number; added?: number; period: number };
  trail: BallPoint[];
  snapshot: Snapshot | null;
  momentum: { t: number; v: number }[];
  chaos: { t: number; v: number }[];
  cards: Overlay[];
  tags: Overlay[];
  traces: Trace[];
  feed: MatchEvent[];
  onPitch: string[];
  pending: { id: string; type: string; minute: number }[];
  league: League | null;
  shots: Shot[];
  goals: Goal[];
  lastGoal: (Goal & { at: number }) | null;
  player: PlayerStats | null;
  matchKey: string | null;
  recent: BallPoint[];
  replays: Replay[];
};

const EMPTY: MatchView = {
  status: "idle",
  provider: null,
  meta: null,
  clock: { t_ms: 0, minute: 0, period: 1 },
  trail: [],
  snapshot: null,
  momentum: [],
  chaos: [],
  cards: [],
  tags: [],
  traces: [],
  feed: [],
  onPitch: [],
  pending: [],
  league: null,
  shots: [],
  goals: [],
  lastGoal: null,
  player: null,
  matchKey: null,
  recent: [],
  replays: [],
};

const ON_BALL = new Set(["pass", "carry", "dribble", "shot", "clearance", "corner"]);
const FEED = new Set(["goal", "shot", "card", "substitution", "corner", "period_start", "period_end", "match_end"]);

/** Events use the acting team's attacking direction; draw everything with the home side attacking right. */
function toPitch(meta: Meta | null, team: string | undefined, x: number, y: number) {
  return meta && team && team !== meta.home.code ? { x: 105 - x, y: 68 - y } : { x, y };
}

export function profilesFor(s: Settings) {
  return ["casual", "analyst", `club:${s.club}`, `player:${s.player}`];
}

export function useMatch() {
  const [view, setView] = useState<MatchView>(EMPTY);
  const ws = useRef<WebSocket | null>(null);

  const stop = useCallback(() => {
    ws.current?.close();
    ws.current = null;
  }, []);

  const start = useCallback(
    (s: Settings) => {
      stop();
      setView({ ...EMPTY, status: "connecting" });
      const params = new URLSearchParams({
        seed: String(s.seed),
        storyline: s.storyline,
        speed: String(s.speed),
        profiles: profilesFor(s).join(","),
        langs: s.langs.join(","),
      });
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const sock = new WebSocket(`${proto}://${location.host}/ws/match?${params}`);
      ws.current = sock;

      sock.onmessage = (msg) => {
        const item = JSON.parse(msg.data);
        setView((v) => reduce(v, item));
      };
      sock.onerror = () => setView((v) => ({ ...v, status: "error" }));
      sock.onclose = () => setView((v) => (v.status === "live" ? { ...v, status: "done" } : v));
    },
    [stop],
  );

  return { view, start, stop };
}

function reduce(v: MatchView, item: any): MatchView {
  switch (item.kind) {
    case "hello":
      return { ...v, status: "live", provider: item.provider, matchKey: item.match_key };
    case "event": {
      const e: MatchEvent = item.event;
      if (e.type === "match_start") {
        const meta = e.data as Meta;
        const starters = [...meta.home.players, ...meta.away.players].filter((p) => p.starter).map((p) => p.id);
        return { ...v, meta, onPitch: starters };
      }
      const next = { ...v, clock: { t_ms: e.t_ms, minute: e.minute, added: e.added, period: e.period } };
      if (ON_BALL.has(e.type) && e.x !== undefined) {
        const end = e.end_x !== undefined && e.outcome !== "incomplete" ? { x: e.end_x, y: e.end_y! } : { x: e.x, y: e.y! };
        const start = toPitch(v.meta, e.team, e.x, e.y!);
        const point = { ...toPitch(v.meta, e.team, end.x, end.y), team: e.team, type: e.type };
        next.trail = [...v.trail.slice(-7), point];
        // The build-up for replays: where each touch started, newest last.
        next.recent = [...v.recent.slice(-14), { ...start, team: e.team, type: e.type }];
      }
      if (FEED.has(e.type)) next.feed = [e, ...v.feed].slice(0, 30);
      if (e.type === "shot" && e.x !== undefined) {
        const p = toPitch(v.meta, e.team, e.x, e.y!);
        next.shots = [...v.shots, { ...p, team: e.team!, outcome: e.outcome!, xg: (e as any).xg, minute: e.minute, player: e.player! }];
      }
      if (e.type === "goal") {
        const g = { team: e.team!, player: e.player!, minute: e.minute, added: e.added };
        next.goals = [...v.goals, g];
        next.lastGoal = { ...g, at: Date.now() };
        // Keep the scoring side's last run of touches, ending in the goal mouth.
        const run: BallPoint[] = [];
        for (const p of [...v.recent].reverse()) {
          if (p.team !== e.team) break;
          run.unshift(p);
          if (run.length === 8) break;
        }
        const homeScored = v.meta && e.team === v.meta.home.code;
        run.push({ x: homeScored ? 105 : 0, y: 34, team: e.team, type: "goal" });
        next.replays = [...v.replays, { id: Date.now(), minute: e.minute, team: e.team!, player: e.player!, path: run }];
      }
      if (e.type === "substitution" && e.player)
        next.onPitch = v.onPitch.map((id) => (id === e.player ? (e as any).player_on : id));
      if (e.type === "card" && (e as any).card === "red") next.onPitch = v.onPitch.filter((id) => id !== e.player);
      return next;
    }
    case "snapshot": {
      const s: Snapshot = item.snapshot;
      return {
        ...v,
        snapshot: s,
        momentum: [...v.momentum, { t: s.t_ms, v: s.momentum }],
        chaos: [...v.chaos, { t: s.t_ms, v: s.chaos_5min }],
      };
    }
    case "overlay": {
      const o: Overlay = item.overlay;
      if (o.type === "player_tag") return { ...v, tags: [...v.tags.slice(-4), o] };
      return { ...v, cards: [...v.cards, o] };
    }
    case "league":
      return { ...v, league: item.league };
    case "player":
      return { ...v, player: item.player };
    case "pending":
      return { ...v, pending: [...v.pending, ...item.moments] };
    case "trace":
      // Every moment in a batch has been handled once any trace for that batch arrives.
      return {
        ...v,
        traces: [item.trace, ...v.traces].slice(0, 40),
        pending: v.pending.filter((p) => p.id !== item.trace.moment_id && p.minute > item.trace.minute),
      };
    case "done":
      return { ...v, status: "done" };
    default:
      return v;
  }
}

export function pitchPos(meta: Meta | null, team: string | undefined, x: number, y: number) {
  return toPitch(meta, team, x, y);
}
