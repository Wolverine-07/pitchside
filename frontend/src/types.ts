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
export type TableRow = {
  pos: number;
  code: string;
  name: string;
  color: string;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  gf: number;
  ga: number;
  gd: number;
  points: number;
  moved?: number;
};
export type Score = { id: string; home: string; away: string; home_goals: number; away_goals: number; minute: number; finished: boolean };
export type League = { league: string; matchday: number; table: TableRow[]; scores: Score[] };

export type Meta = {
  home: Club;
  away: Club;
  venue: string;
  seed: number;
  storyline: string;
  league?: League;
  fixtures?: { home: string; away: string }[];
};

export type PlayerStats = {
  player: string;
  name: string;
  team: string;
  passes: number;
  pass_accuracy_pct: number | null;
  shots: number;
  xg: number;
  goals: number;
  assists: number;
  regains: number;
  high_regains: number;
  distance_m: number | null;
  top_speed_kmh: number | null;
};

export type Shot = { x: number; y: number; team: string; outcome: string; xg: number; minute: number; player: string };
export type Goal = { team: string; player: string; minute: number; added?: number };

export type Mode = "casual" | "analyst" | "club" | "player";
export type Lang = "en" | "hi" | "es";
