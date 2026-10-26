import { useEffect, useMemo, useState } from "react";
import { AgentTrace, ChaosGauge, InsightCard, MomentumStrip, Pitch, ScoreBug, StatRow } from "./components";
import type { Lang, Meta, Mode } from "./types";
import { type Settings, useMatch } from "./useMatch";

const MODES: { id: Mode; label: string }[] = [
  { id: "casual", label: "Casual" },
  { id: "analyst", label: "Analyst" },
  { id: "club", label: "My club" },
  { id: "player", label: "My player" },
];
const LANGS: { id: Lang; label: string }[] = [
  { id: "en", label: "English" },
  { id: "hi", label: "हिन्दी" },
  { id: "es", label: "Español" },
];

export default function App() {
  const { view, start } = useMatch();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [settings, setSettings] = useState<Settings>({
    seed: 16,
    storyline: "comeback",
    speed: 10,
    club: "RVA",
    player: "KSC-09",
    langs: ["en", "hi", "es"],
  });
  const [mode, setMode] = useState<Mode>("casual");
  const [lang, setLang] = useState<Lang>("en");
  const [voice, setVoice] = useState(false);

  useEffect(() => {
    fetch(`/api/meta?seed=${settings.seed}&storyline=${settings.storyline}`)
      .then((r) => r.json())
      .then(setMeta)
      .catch(() => setMeta(null));
  }, [settings.seed, settings.storyline]);

  // ?kickoff starts straight away (handy for demos); ?mode= and ?lang= preselect the view.
  useEffect(() => {
    const q = new URLSearchParams(location.search);
    if (q.get("mode")) setMode(q.get("mode") as Mode);
    if (q.get("lang")) setLang(q.get("lang") as Lang);
    if (q.has("kickoff") && meta && view.status === "idle") {
      const speed = Number(q.get("speed") ?? settings.speed);
      start({ ...settings, speed });
    }
  }, [meta]); // eslint-disable-line react-hooks/exhaustive-deps

  const m = view.meta ?? meta;
  const profile = mode === "club" ? `club:${settings.club}` : mode === "player" ? `player:${settings.player}` : mode;
  const key = `${profile}:${lang}`;
  const myCards = useMemo(() => view.cards.filter((c) => c.profile_key === key), [view.cards, key]);
  const latest = myCards.at(-1);
  const snap = view.snapshot;
  const started = view.status !== "idle";

  return (
    <div className="flex h-full flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2.5">
        <div className="mr-2 text-lg font-bold tracking-tight">
          Pitch<span className="text-accent">side</span>
        </div>
        <div className="flex overflow-hidden rounded-md border border-line">
          {MODES.map((x) => (
            <button
              key={x.id}
              onClick={() => setMode(x.id)}
              className={`px-3 py-1.5 text-sm ${mode === x.id ? "bg-accent/20 font-semibold text-white" : "text-muted hover:text-white"}`}
            >
              {x.label}
            </button>
          ))}
        </div>
        <div className="flex overflow-hidden rounded-md border border-line">
          {LANGS.map((x) => (
            <button
              key={x.id}
              onClick={() => setLang(x.id)}
              className={`px-3 py-1.5 text-sm ${lang === x.id ? "bg-accent/20 font-semibold text-white" : "text-muted hover:text-white"}`}
            >
              {x.label}
            </button>
          ))}
        </div>
        <button
          onClick={() => setVoice((v) => !v)}
          className={`rounded-md border border-line px-3 py-1.5 text-sm ${voice ? "bg-accent/20 text-white" : "text-muted"}`}
        >
          Voice {voice ? "on" : "off"}
        </button>
        <div className="ml-auto flex items-center gap-2 text-xs text-muted">
          {view.provider && <span className="rounded bg-line px-2 py-1">model: {view.provider}</span>}
          <span className={`rounded px-2 py-1 ${view.status === "live" ? "bg-bad/20 text-bad" : "bg-line"}`}>
            {view.status === "live" ? "● LIVE" : view.status}
          </span>
        </div>
      </header>

      {!started ? (
        <Setup meta={meta} settings={settings} setSettings={setSettings} onStart={() => start(settings)} />
      ) : (
        <main className="grid min-h-0 flex-1 gap-4 p-4 lg:grid-cols-[1fr_380px]">
          <section className="flex min-h-0 flex-col gap-3 overflow-y-auto">
            <Pitch
              meta={m}
              trail={view.trail}
              tags={view.tags}
              clockMs={view.clock.t_ms}
              onPitch={view.onPitch}
              focus={mode === "player" ? settings.player : undefined}
            >
              <ScoreBug meta={m} snapshot={snap} minute={view.clock.minute} added={view.clock.added} />
              <InsightCard card={latest} voice={voice} lang={lang} meta={m} />
            </Pitch>
            <MomentumStrip data={view.momentum} meta={m} />
            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-3 rounded-lg border border-line bg-panel p-3">
                {snap && m && (
                  <>
                    <StatRow label="Possession %" home={snap.possession_pct[m.home.code]} away={snap.possession_pct[m.away.code]} meta={m} />
                    <StatRow label="xG" home={snap.xg[m.home.code]} away={snap.xg[m.away.code]} meta={m} fmt={(v) => v.toFixed(2)} />
                    <ChaosGauge value={snap.chaos_5min} />
                  </>
                )}
                {!snap && <div className="text-sm text-muted">Kick-off soon…</div>}
              </div>
              <div className="rounded-lg border border-line bg-panel p-3">
                <div className="mb-2 text-xs uppercase tracking-wider text-muted">The story so far · {MODES.find((x) => x.id === mode)?.label}</div>
                <ol className="max-h-56 space-y-2 overflow-y-auto pr-1 text-sm">
                  {[...myCards].reverse().map((c) => (
                    <li key={c.overlay_id} className="card-in">
                      <span className="mr-2 tabular-nums text-muted">{Math.floor(c.anchor_t_ms / 60000) + 1}'</span>
                      <span className="font-semibold">{c.content.headline}.</span> <span className="text-slate-300">{c.content.body}</span>
                    </li>
                  ))}
                  {myCards.length === 0 && <li className="text-muted">Nothing yet.</li>}
                </ol>
              </div>
            </div>
          </section>
          <aside className="min-h-0">
            <AgentTrace traces={view.traces} />
          </aside>
        </main>
      )}
    </div>
  );
}

function Setup({ meta, settings, setSettings, onStart }: { meta: Meta | null; settings: Settings; setSettings: (s: Settings) => void; onStart: () => void }) {
  const players = meta ? [...meta.home.players, ...meta.away.players].filter((p) => p.starter && p.role !== "GK") : [];
  const clubs = meta ? [meta.home, meta.away] : [];
  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <div className="w-full max-w-xl rounded-2xl border border-line bg-panel p-6 shadow-xl">
        <h1 className="text-2xl font-bold">Make this match yours</h1>
        <p className="mt-1 text-sm text-muted">
          {meta ? `${meta.home.name} v ${meta.away.name} · ${meta.venue}` : "Loading match…"} · synthetic match, made-up clubs and players
        </p>
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <label className="text-sm">
            <span className="text-muted">Your club</span>
            <select
              className="mt-1 w-full rounded-md border border-line bg-ink px-3 py-2"
              value={settings.club}
              onChange={(e) => setSettings({ ...settings, club: e.target.value })}
            >
              {clubs.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="text-muted">Player to follow</span>
            <select
              className="mt-1 w-full rounded-md border border-line bg-ink px-3 py-2"
              value={settings.player}
              onChange={(e) => setSettings({ ...settings, player: e.target.value })}
            >
              {players.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.id.slice(0, 3)} #{p.number})
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="text-muted">Match speed</span>
            <select
              className="mt-1 w-full rounded-md border border-line bg-ink px-3 py-2"
              value={settings.speed}
              onChange={(e) => setSettings({ ...settings, speed: Number(e.target.value) })}
            >
              {[1, 5, 10, 20].map((s) => (
                <option key={s} value={s}>
                  {s === 1 ? "Real time" : `${s}x`}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="text-muted">Match</span>
            <select
              className="mt-1 w-full rounded-md border border-line bg-ink px-3 py-2"
              value={`${settings.seed}:${settings.storyline}`}
              onChange={(e) => {
                const [seed, storyline] = e.target.value.split(":");
                setSettings({ ...settings, seed: Number(seed), storyline });
              }}
            >
              <option value="16:comeback">Demo: the comeback</option>
              <option value="3:none">Random match A</option>
              <option value="7:none">Random match B</option>
              <option value="11:none">Random match C</option>
            </select>
          </label>
        </div>
        <button onClick={onStart} disabled={!meta} className="mt-6 w-full rounded-lg bg-accent py-2.5 font-semibold text-ink disabled:opacity-50">
          Kick off
        </button>
      </div>
    </main>
  );
}
