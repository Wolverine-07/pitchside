import { useEffect, useMemo, useState } from "react";
import {
  AgentSummary,
  AskPanel,
  AgentTrace,
  CommentaryFeed,
  ControlGauge,
  GoalBanner,
  isRecap,
  RecapCard,
  LeagueTable,
  LowerThird,
  MatchStats,
  Momentum,
  Pitch,
  PlayerCard,
  Scoreboard,
  ScoresTicker,
  momentLabel,
} from "./components";
import type { Lang, Meta, Mode } from "./types";
import { type Settings, useMatch } from "./useMatch";

const MODES: { id: Mode; label: string }[] = [
  { id: "casual", label: "Casual" },
  { id: "analyst", label: "Analyst" },
  { id: "club", label: "My club" },
  { id: "player", label: "My player" },
];
const LANGS: { id: Lang; label: string }[] = [
  { id: "en", label: "EN" },
  { id: "hi", label: "हिं" },
  { id: "es", label: "ES" },
];

function Segmented<T extends string>({ items, value, onChange, label }: { items: { id: T; label: string }[]; value: T; onChange: (v: T) => void; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="hidden text-[11px] font-medium uppercase tracking-[0.14em] text-muted xl:inline">{label}</span>
      <div className="flex rounded-lg border border-line bg-panel p-0.5">
        {items.map((x) => (
          <button
            key={x.id}
            onClick={() => onChange(x.id)}
            className={`rounded-md px-3 py-1 text-[13px] font-medium transition-colors ${value === x.id ? "bg-accent text-ink" : "text-soft hover:text-white"}`}
          >
            {x.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="h-7 w-7">
        <rect width="32" height="32" rx="8" fill="#10331f" />
        <rect x="5" y="8" width="22" height="16" rx="1" fill="none" stroke="#7fd3a0" strokeWidth="1.5" />
        <line x1="16" y1="8" x2="16" y2="24" stroke="#7fd3a0" strokeWidth="1.5" />
        <circle cx="16" cy="16" r="3" fill="#4f9cff" />
      </svg>
      <span className="text-[17px] font-bold tracking-tight">
        Pitch<span className="text-accent">side</span>
      </span>
    </div>
  );
}

export default function App() {
  const { view, start } = useMatch();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [settings, setSettings] = useState<Settings>({
    seed: 16,
    storyline: "comeback",
    speed: 5,
    club: "RVA",
    player: "KSC-09",
    langs: ["en", "hi", "es"],
  });
  const [mode, setMode] = useState<Mode>("casual");
  const [lang, setLang] = useState<Lang>("en");
  const [voice, setVoice] = useState(false);
  const [tab, setTab] = useState<"commentary" | "ask" | "agents" | "league">("commentary");

  useEffect(() => {
    fetch(`/api/meta?seed=${settings.seed}&storyline=${settings.storyline}`)
      .then((r) => r.json())
      .then(setMeta)
      .catch(() => setMeta(null));
  }, [settings.seed, settings.storyline]);

  // ?kickoff starts straight away (handy for demos); ?mode=, ?lang= and ?tab= preselect the view.
  useEffect(() => {
    const q = new URLSearchParams(location.search);
    if (q.get("mode")) setMode(q.get("mode") as Mode);
    if (q.get("lang")) setLang(q.get("lang") as Lang);
    if (q.get("tab") === "agents" || q.get("tab") === "league") setTab(q.get("tab") as "agents" | "league");
    if (q.has("kickoff") && meta && view.status === "idle") {
      start({ ...settings, speed: Number(q.get("speed") ?? settings.speed) });
    }
  }, [meta]); // eslint-disable-line react-hooks/exhaustive-deps

  const m = view.meta ?? meta;
  const profile = mode === "club" ? `club:${settings.club}` : mode === "player" ? `player:${settings.player}` : mode;
  const key = `${profile}:${lang}`;
  const myCards = useMemo(() => view.cards.filter((c) => c.profile_key === key), [view.cards, key]);
  const latest = myCards.filter((c) => !isRecap(c)).at(-1);
  const latestRecap = myCards.filter(isRecap).at(-1);
  // Each goal replays its build-up once the banner has gone; feed buttons replay any goal again.
  const [replayId, setReplayId] = useState<number | null>(null);
  const lastReplay = view.replays.at(-1);
  useEffect(() => {
    if (!lastReplay) return;
    const show = window.setTimeout(() => setReplayId(lastReplay.id), 3300);
    return () => window.clearTimeout(show);
  }, [lastReplay?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const replay = view.replays.find((r) => r.id === replayId) ?? null;
  useEffect(() => {
    if (!replay) return;
    const hide = window.setTimeout(() => setReplayId(null), Math.max(2500, replay.path.length * 550) + 2500);
    return () => window.clearTimeout(hide);
  }, [replay?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const started = view.status !== "idle";

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 shrink-0 items-center gap-5 border-b border-line bg-ink/70 px-5 backdrop-blur">
        <Logo />
        {m && (
          <div className="hidden min-w-0 border-l border-line pl-5 lg:block">
            <div className="truncate text-[13px] font-semibold">
              {m.home.name} v {m.away.name}
            </div>
            <div className="truncate text-[11px] text-muted">{m.venue} · synthetic match</div>
          </div>
        )}
        {started && (
          <div className="ml-auto flex items-center gap-4">
            <Segmented label="View" items={MODES} value={mode} onChange={setMode} />
            <Segmented label="Language" items={LANGS} value={lang} onChange={setLang} />
            <button
              onClick={() => setVoice((v) => !v)}
              className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-[13px] font-medium transition-colors ${voice ? "border-accent bg-accent/15 text-white" : "border-line bg-panel text-soft hover:text-white"}`}
              title="Read captions aloud with Azure AI Speech"
            >
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6">
                <path d="M4 8h3l4-3v10l-4-3H4z" />
                {voice && <path d="M14 7.5a3.5 3.5 0 0 1 0 5M16 5.5a6.5 6.5 0 0 1 0 9" />}
              </svg>
              Voice
            </button>
            <div className="flex items-center gap-2 border-l border-line pl-4 text-[12px]">
              {view.status === "live" ? (
                <span className="flex items-center gap-1.5 font-semibold text-bad">
                  <i className="live-dot h-2 w-2 rounded-full bg-bad" />
                  LIVE
                </span>
              ) : (
                <span className="capitalize text-muted">{view.status}</span>
              )}
            </div>
          </div>
        )}
      </header>

      {started && <ScoresTicker league={view.league} />}

      {!started ? (
        <Setup meta={meta} settings={settings} setSettings={setSettings} onStart={() => start(settings)} />
      ) : (
        <main className="grid min-h-0 flex-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_400px]">
          <section className="flex min-h-0 flex-col gap-3">
            <Scoreboard meta={m} snapshot={view.snapshot} clock={view.clock} goals={view.goals} />
            <div className="pitch-stage grid min-h-0 flex-1 place-items-center">
              <Pitch
                meta={m}
                trail={view.trail}
                tags={view.tags}
                clockMs={view.clock.t_ms}
                onPitch={view.onPitch}
                focus={mode === "player" ? settings.player : undefined}
                shots={mode === "analyst" ? view.shots : []}
                replay={replay}
              >
                <LowerThird card={latest} voice={voice} lang={lang} meta={m} />
                {mode === "player" && <PlayerCard stats={view.player} meta={m} />}
                <GoalBanner goal={view.lastGoal} meta={m} />
                <RecapCard card={latestRecap} meta={m} voice={voice} lang={lang} />
              </Pitch>
            </div>
            <div className="grid h-[164px] shrink-0 grid-cols-[minmax(0,2fr)_minmax(0,1.2fr)_minmax(0,1fr)] gap-3">
              <Momentum data={view.momentum} meta={m} goals={view.goals} />
              <MatchStats snapshot={view.snapshot} meta={m} />
              <ControlGauge value={view.snapshot?.chaos_5min} />
            </div>
          </section>

          <aside className="flex min-h-0 flex-col rounded-xl border border-line bg-panel">
            <div className="flex shrink-0 gap-1 border-b border-line p-1.5">
              {(
                [
                  ["commentary", "Commentary", myCards.length],
                  ["ask", "Ask", null],
                  ["agents", "Agents", view.traces.length],
                  ["league", "League", view.league?.scores.reduce((a, s) => a + s.home_goals + s.away_goals, 0) ?? 0],
                ] as const
              ).map(([id, label, n]) => (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  className={`flex flex-1 items-center justify-center gap-2 rounded-lg py-2 text-[13px] font-semibold transition-colors ${tab === id ? "bg-panel-2 text-white" : "text-muted hover:text-soft"}`}
                >
                  {label}
                  {n !== null && <span className="rounded-full bg-white/5 px-1.5 font-mono text-[11px] text-soft">{n}</span>}
                </button>
              ))}
            </div>
            {view.pending.length > 0 && (
              <div className="flex shrink-0 items-center gap-2 border-b border-line px-4 py-2 text-[12px] text-soft">
                <i className="live-dot h-1.5 w-1.5 rounded-full bg-accent" />
                Agents writing: {view.pending.slice(-2).map((p) => `${momentLabel(p.type)} ${p.minute}'`).join(", ")}
              </div>
            )}
            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              {tab === "commentary" ? (
                <>
                  {view.replays.length > 0 && (
                    <div className="mb-3 flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">Goal replays</span>
                      {view.replays.map((r) => (
                        <button
                          key={r.id}
                          onClick={() => setReplayId(r.id)}
                          className="rounded-full border border-line bg-panel-2/60 px-2.5 py-0.5 text-[12px] text-soft hover:border-accent hover:text-white"
                        >
                          ▶ {r.team} {r.minute}'
                        </button>
                      ))}
                    </div>
                  )}
                  <CommentaryFeed cards={myCards} meta={m} liveId={latest?.overlay_id} />
                </>
              ) : tab === "ask" ? (
                <AskPanel
                  matchKey={view.matchKey}
                  lang={lang}
                  profile={profile}
                  voice={voice}
                  suggestions={askSuggestions(m, settings, view.snapshot?.chaos_5min, lang)}
                />
              ) : tab === "league" ? (
                <LeagueTable league={view.league ?? m?.league ?? null} highlight={m ? [m.home.code, m.away.code] : []} />
              ) : (
                <>
                  <AgentSummary traces={view.traces} />
                  <AgentTrace traces={view.traces} />
                </>
              )}
            </div>
            <div className="shrink-0 border-t border-line px-4 py-2.5 text-[11px] text-muted">
              {view.provider === "templates" ? "Template mode: no model connected" : "Six agents on Microsoft Foundry · every number verified"}
            </div>
          </aside>
        </main>
      )}
    </div>
  );
}

function askSuggestions(m: Meta | null, s: Settings, chaos: number | undefined, lang: string) {
  if (!m) return [];
  const player = [...m.home.players, ...m.away.players].find((p) => p.id === s.player)?.name.split(" ").at(-1) ?? "my player";
  const club = s.club === m.home.code ? m.home.name : m.away.name;
  const byLang: Record<string, string[]> = {
    en: [
      `How is ${player} playing?`,
      `Why ${chaos !== undefined && chaos > 0.6 ? "is the game so chaotic" : "is this game going the way it is"}?`,
      `What does this score do to ${club} in the table?`,
      "Who has been the best player?",
    ],
    hi: [`${player} कैसा खेल रहे हैं?`, "अभी मैच में क्या हो रहा है?", `तालिका में ${club} की स्थिति क्या है?`],
    es: [`¿Cómo está jugando ${player}?`, "¿Por qué el partido va así?", `¿Qué significa este resultado para ${club} en la tabla?`],
  };
  return byLang[lang] ?? byLang.en;
}

function ordinal(n?: number) {
  if (!n) return "";
  const s = n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${s}`;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">{label}</span>
      <div className="mt-1.5">{children}</div>
    </label>
  );
}

const selectClass = "w-full rounded-lg border border-line bg-ink px-3 py-2.5 text-sm outline-none transition-colors focus:border-accent";

function Setup({ meta, settings, setSettings, onStart }: { meta: Meta | null; settings: Settings; setSettings: (s: Settings) => void; onStart: () => void }) {
  const players = meta ? [...meta.home.players, ...meta.away.players].filter((p) => p.starter && p.role !== "GK") : [];
  const clubs = meta ? [meta.home, meta.away] : [];
  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <div className="w-full max-w-2xl">
        <div className="mb-6 text-center">
          <h1 className="text-3xl font-bold tracking-tight">The story of the game, made for you</h1>
          <p className="mt-2 text-soft">
            AI agents watch the match, explain why each moment matters, check every number, and tell it your way.
          </p>
        </div>
        <div className="rounded-2xl border border-line bg-panel p-6 shadow-2xl">
          {meta && (
            <div className="mb-6 flex items-center justify-center gap-4 border-b border-line pb-5">
              <span className="grid h-11 w-11 place-items-center rounded-full text-xs font-extrabold" style={{ background: meta.home.colors[0] }}>
                {meta.home.code}
              </span>
              <div className="text-center">
                <div className="font-semibold">
                  {meta.home.name} <span className="text-muted">v</span> {meta.away.name}
                </div>
                <div className="text-xs text-muted">{meta.venue} · synthetic match, made-up clubs and players</div>
                {meta.league && (
                  <div className="mt-1 text-xs text-soft">
                    {meta.league.league} · Matchday {meta.league.matchday} ·{" "}
                    {ordinal(meta.league.table.find((r) => r.code === meta.home.code)?.pos)} v{" "}
                    {ordinal(meta.league.table.find((r) => r.code === meta.away.code)?.pos)} · three other games at the same time
                  </div>
                )}
              </div>
              <span className="grid h-11 w-11 place-items-center rounded-full text-xs font-extrabold" style={{ background: meta.away.colors[0] }}>
                {meta.away.code}
              </span>
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Your club">
              <select className={selectClass} value={settings.club} onChange={(e) => setSettings({ ...settings, club: e.target.value })}>
                {clubs.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Player to follow">
              <select className={selectClass} value={settings.player} onChange={(e) => setSettings({ ...settings, player: e.target.value })}>
                {players.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} · {p.id.slice(0, 3)} #{p.number}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Match">
              <select
                className={selectClass}
                value={`${settings.seed}:${settings.storyline}`}
                onChange={(e) => {
                  const [seed, storyline] = e.target.value.split(":");
                  setSettings({ ...settings, seed: Number(seed), storyline });
                }}
              >
                <option value="16:comeback">The comeback (demo)</option>
                <option value="3:none">Match A</option>
                <option value="7:none">Match B</option>
                <option value="11:none">Match C</option>
              </select>
            </Field>
            <Field label="Speed">
              <select className={selectClass} value={settings.speed} onChange={(e) => setSettings({ ...settings, speed: Number(e.target.value) })}>
                {[1, 3, 5, 10].map((s) => (
                  <option key={s} value={s}>
                    {s === 1 ? "Real time" : `${s}x${s === 5 ? " (recommended)" : ""}`}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <button
            onClick={onStart}
            disabled={!meta}
            className="mt-6 w-full rounded-xl bg-accent py-3 text-[15px] font-semibold text-ink transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            Kick off
          </button>
        </div>
      </div>
    </main>
  );
}
