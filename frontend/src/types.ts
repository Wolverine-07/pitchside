export type MatchEvent = {
  match_id: string;
  event_id: number;
  t_ms: number;
  period: number;
  minute: number;
  added?: number;
  type: string;
  team?: string;
  player?: string;
  x?: number;
  y?: number;
  end_x?: number;
  end_y?: number;
  outcome?: string;
  speed_kmh?: number;
  data?: any;
};

export type Snapshot = {
  t_ms: number;
  minute: number;
  period: number;
  score: Record<string, number>;
  possession_pct: Record<string, number>;
  momentum: number;
  chaos_5min: number;
  xg: Record<string, number>;
};

export type Evidence = {
  metric: string;
  value: number | string;
  team?: string | null;
  player?: string | null;
  window_s?: number | null;
};

export type Overlay = {
  overlay_id: string;
  match_id: string;
  moment_id: string | null;
  type: "insight_card" | "player_tag" | "stat_strip" | "score_bug" | "momentum_strip" | "recap_card";
  slot: string;
  anchor_t_ms: number;
  start_t_ms: number;
  duration_ms: number;
  priority: number;
  profile_key: string;
  content: any;
  provenance: { verified: boolean; fallback?: boolean; agents?: string[] };
};

export type TraceStep = { agent: string; ms: number; status: string; note: string };
export type Trace = { moment_id: string; minute: number; type: string; steps: TraceStep[] };

export type Player = { id: string; name: string; number: number; role: string; starter: boolean };
export type Club = { code: string; name: string; colors: string[]; players: Player[] };
export type Meta = { home: Club; away: Club; venue: string; seed: number; storyline: string };

export type Mode = "casual" | "analyst" | "club" | "player";
export type Lang = "en" | "hi" | "es";
