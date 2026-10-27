import { useEffect, useMemo, useState } from "react";
import {
  AgentSummary,
  AskPanel,
  type Decision,
  ProducerQueue,
  AgentTrace,
  CommentaryFeed,
  Crest,
  FullTime,
  LiveEvents,
  GoalBanner,
  isRecap,
  RecapCard,
  LeagueTable,
  LastAction,
  LowerThird,
  MatchStats,
  METRICS,
  MetricTracker,
  Momentum,
  ProofModal,
  Pitch,
  PlayerCard,
  Scoreboard,
  ScoresTicker,
  momentLabel,
} from "./components";
import type { Lang, Meta, Mode } from "./types";
import { type Settings, useMatch } from "./useMatch";
import { LANGUAGES, t } from "./i18n";
import { setVoice as setVoiceOutput, speak, stop as stopVoice } from "./voice";

const modes = (lang: string): { id: Mode; label: string }[] => [
  { id: "casual", label: t(lang, "casual") },
  { id: "analyst", label: t(lang, "analyst") },
  { id: "club", label: t(lang, "myClub") },
  { id: "player", label: t(lang, "myPlayer") },
  { id: "metric", label: t(lang, "myMetric") },
];
const MAX_EXTRA_LANGS = 3; // each language is one more parallel Linguist call per moment

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
  const { view, start, leave } = useMatch();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [settings, setSettings] = useState<Settings>({
    seed: 16,
    storyline: "comeback",
    fixture: "KSC-RVA",
    speed: 3,
    club: "RVA",
    player: "KSC-09",
    metric: "possession",
    langs: ["en", "hi", "es"],
  });
  const [mode, setMode] = useState<Mode>("casual");
  const [lang, setLang] = useState<Lang>("en");
  const [voice, setVoice] = useState(false);
  const [tab, setTab] = useState<"producer" | "commentary" | "ask" | "agents" | "league">("commentary");
  const [studio, setStudio] = useState(false);
  const [proof, setProof] = useState(false);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});

  useEffect(() => {
    fetch(`/api/meta?seed=${settings.seed}&storyline=${settings.storyline}&fixture=${settings.fixture}`)
      .then((r) => r.json())
      .then((m: Meta) => {
        setMeta(m);
        // Keep the chosen club and player valid for whichever fixture is selected.
        setSettings((s) => {
          const codes = [m.home.code, m.away.code];
          const attackers = [...m.home.players, ...m.away.players].filter((p) => p.starter && p.role === "ST");
          return {
            ...s,
            club: codes.includes(s.club) ? s.club : m.away.code,
            player: s.player.slice(0, 3) && codes.includes(s.player.slice(0, 3)) ? s.player : attackers[0]?.id ?? s.player,
          };
        });
      })
      .catch(() => setMeta(null));
  }, [settings.seed, settings.storyline, settings.fixture]);

  // ?kickoff starts straight away (handy for demos); ?mode=, ?lang= and ?tab= preselect the view.
  useEffect(() => {
    const q = new URLSearchParams(location.search);
    if (q.get("mode")) setMode(q.get("mode") as Mode);
    let langs = settings.langs;
    const ql = q.get("lang");
    if (ql && LANGUAGES.some((l) => l.id === ql)) {
      setLang(ql);
      if (!langs.includes(ql)) {
        langs = ["en", ql, ...langs.filter((l) => l !== "en" && l !== ql)].slice(0, 1 + MAX_EXTRA_LANGS);
        setSettings((x) => ({ ...x, langs }));
      }
    }
    if (q.get("tab") === "agents" || q.get("tab") === "league") setTab(q.get("tab") as "agents" | "league");
    const fixture = q.get("fixture");
    if (fixture && fixture !== settings.fixture) {
      setSettings((x) => ({ ...x, fixture }));
      return; // meta reloads for that fixture, then this runs again
    }
    if (q.has("kickoff") && meta && view.status === "idle") {
      start({ ...settings, langs, speed: Number(q.get("speed") ?? settings.speed) });
    }
  }, [meta]); // eslint-disable-line react-hooks/exhaustive-deps

  const m = view.meta ?? meta;
  const profile =
    mode === "club" ? `club:${settings.club}` : mode === "player" ? `player:${settings.player}` : mode === "metric" ? `metric:${settings.metric}` : mode;
  const key = `${profile}:${lang}`;
  const myCards = useMemo(() => {
    const mine = view.cards.filter((c) => c.profile_key === key);
    // Fast-path captions (already in this language) fill the gap until the agents' caption lands.
    const done = new Set(mine.map((c) => c.moment_id));
    const flashes = view.cards.filter((c) => c.profile_key === `flash:${lang}` && !done.has(c.moment_id));
    return [...mine, ...flashes].sort((a, b) => a.anchor_t_ms - b.anchor_t_ms || (a.provenance.fallback ? -1 : 1));
  }, [view.cards, key, lang]);
  // In studio mode only approved captions air, with the producer's edits applied.
  const airable = studio
    ? myCards
        .filter((c) => decisions[c.overlay_id]?.status === "approved")
        .map((c) => {
          const d = decisions[c.overlay_id];
          return { ...c, content: { ...c.content, headline: d.headline ?? c.content.headline, body: d.body ?? c.content.body } };
        })
    : myCards;
  const latest = airable.filter((c) => !isRecap(c)).at(-1);
  const awaiting = myCards.filter((c) => !decisions[c.overlay_id]).length;
  // Languages are chosen per match; fall back to English if the current one was dropped.
  useEffect(() => {
    if (!settings.langs.includes(lang)) setLang("en");
  }, [settings.langs]); // eslint-disable-line react-hooks/exhaustive-deps
  // A new language means new voices: stop the old one mid-sentence.
  useEffect(() => stopVoice(), [lang]);
  // Voice takes effect at once: on reads the caption on screen now, off stops speaking.
  useEffect(() => {
    setVoiceOutput(voice);
    if (voice && latest) speak(`${latest.content.headline}. ${latest.content.body}`, lang, true);
  }, [voice]); // eslint-disable-line react-hooks/exhaustive-deps
  const latestRecap = airable.filter(isRecap).at(-1);
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
            <Segmented label={t(lang, "view")} items={modes(lang)} value={mode} onChange={setMode} />
            <Segmented
              label={t(lang, "language")}
              items={LANGUAGES.filter((l) => settings.langs.includes(l.id)).map((l) => ({ id: l.id as Lang, label: l.short }))}
              value={lang}
              onChange={setLang}
            />
            <button
              onClick={() => {
                setStudio((s) => !s);
                setTab(studio ? "commentary" : "producer");
              }}
              className={`rounded-lg border px-3 py-1.5 text-[13px] font-medium transition-colors ${studio ? "border-warn bg-warn/15 text-white" : "border-line bg-panel text-soft hover:text-white"}`}
              title="Studio mode: approve or edit every caption before it airs"
            >
              {t(lang, "studio")}
            </button>
            <button
              onClick={() => setVoice((v) => !v)}
              className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-[13px] font-medium transition-colors ${voice ? "border-accent bg-accent/15 text-white" : "border-line bg-panel text-soft hover:text-white"}`}
              title="Read captions aloud with Azure AI Speech"
            >
              <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6">
                <path d="M4 8h3l4-3v10l-4-3H4z" />
                {voice && <path d="M14 7.5a3.5 3.5 0 0 1 0 5M16 5.5a6.5 6.5 0 0 1 0 9" />}
              </svg>
              {t(lang, "voice")}
            </button>
            <button
              onClick={() => {
                if (view.status !== "live" || confirm("Leave this match? It will stop for you.")) {
                  stopVoice();
                  setDecisions({});
                  leave();
                }
              }}
              className="rounded-lg border border-line bg-panel px-3 py-1.5 text-[13px] font-medium text-soft hover:border-bad hover:text-white"
              title="Leave this match and pick another"
            >
              {t(lang, "leave")}
            </button>
            <div className="flex items-center gap-2 border-l border-line pl-4 text-[12px]">
              {view.status === "live" ? (
                <span className="flex items-center gap-1.5 font-semibold text-bad">
                  <i className="live-dot h-2 w-2 rounded-full bg-bad" />
                  {t(lang, "live")}
                </span>
              ) : (
                <span className="capitalize text-muted">{view.status}</span>
              )}
            </div>
          </div>
        )}
        <button
          onClick={() => setProof(true)}
          className={`${started ? "" : "ml-auto "}rounded-lg border border-line bg-panel px-3 py-1.5 text-[13px] font-medium text-soft hover:text-white`}
          title="How the agents work and what was measured"
        >
          {t(lang, "howItWorks")}
        </button>
      </header>
      {proof && <ProofModal onClose={() => setProof(false)} />}

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
                carrier={view.carrier}
              >
                <LowerThird card={latest} voice={voice} lang={lang} meta={m} />
                {mode === "player" && <PlayerCard stats={view.player} meta={m} />}
                {mode === "metric" && <MetricTracker metric={settings.metric} snapshot={view.snapshot} meta={m} />}
                {mode === "analyst" && !replay && <LastAction e={view.lastAction} meta={m} />}
                <GoalBanner goal={view.lastGoal} meta={m} />
                {view.status !== "done" && <RecapCard card={latestRecap} meta={m} voice={voice} lang={lang} />}
                {view.status === "done" && m && (
                  <FullTime meta={m} snapshot={view.snapshot} league={view.league} recap={latestRecap} onLeave={leave} lang={lang} />
                )}
              </Pitch>
            </div>
            <div className="grid h-[200px] shrink-0 grid-cols-[minmax(0,1.5fr)_minmax(0,1.3fr)_minmax(0,1.2fr)] gap-3">
              <Momentum data={view.momentum} meta={m} goals={view.goals} chaos={view.snapshot?.chaos_5min} lang={lang} />
              <MatchStats snapshot={view.snapshot} meta={m} lang={lang} />
              <LiveEvents feed={view.feed} meta={m} lang={lang} />
            </div>
          </section>

          <aside className="flex min-h-0 flex-col rounded-xl border border-line bg-panel">
            <div className="flex shrink-0 gap-1 border-b border-line p-1.5">
              {(
                [
                  ...(studio ? ([["producer", t(lang, "producer"), awaiting]] as const) : []),
                  ["commentary", t(lang, "commentary"), myCards.length],
                  ["ask", t(lang, "ask"), null],
                  ["agents", t(lang, "agents"), view.traces.length],
                  ["league", t(lang, "league"), view.league?.scores.reduce((a, s) => a + s.home_goals + s.away_goals, 0) ?? 0],
                ] as const
              ).map(([id, label, n]) => (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-1 py-2 text-[12px] font-semibold transition-colors ${tab === id ? "bg-panel-2 text-white" : "text-muted hover:text-soft"}`}
                >
                  {label}
                  {n !== null && <span className="rounded-full bg-white/5 px-1.5 font-mono text-[11px] text-soft">{n}</span>}
                </button>
              ))}
            </div>
            {view.pending.length > 0 && (
              <div className="flex shrink-0 items-center gap-2 border-b border-line px-4 py-2 text-[12px] text-soft">
                <i className="live-dot h-1.5 w-1.5 rounded-full bg-accent" />
                {t(lang, "agentsWriting")}: {view.pending.slice(-2).map((p) => `${momentLabel(p.type, lang)} ${p.minute}'`).join(", ")}
              </div>
            )}
            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              {tab === "producer" ? (
                <ProducerQueue
                  cards={myCards}
                  decisions={decisions}
                  decide={(id, d) => setDecisions((x) => ({ ...x, [id]: d }))}
                  matchKey={view.matchKey}
                  meta={m}
                />
              ) : tab === "commentary" ? (
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
                  <CommentaryFeed cards={myCards} meta={m} liveId={latest?.overlay_id} traces={view.traces} lang={lang} />
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
              {view.provider === "templates" ? "Template mode: no model connected" : "Seven agents on Microsoft Foundry · every number verified"}
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
    fr: [`Comment joue ${player} ?`, "Pourquoi le match tourne-t-il ainsi ?", `Que change ce score pour ${club} au classement ?`],
    pt: [`Como está a jogar o ${player}?`, "Porque é que o jogo está assim?", `O que muda este resultado para o ${club} na tabela?`],
    ar: [`كيف يلعب ${player}؟`, "لماذا تسير المباراة هكذا؟", `ماذا تعني هذه النتيجة لـ ${club} في الترتيب؟`],
    de: [`Wie spielt ${player}?`, "Warum läuft das Spiel so?", `Was bedeutet das Ergebnis für ${club} in der Tabelle?`],
    ja: [`${player}の出来は？`, "なぜこういう試合展開なの？", `この結果で${club}の順位はどうなる？`],
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
              <Crest code={meta.home.code} colors={meta.home.colors} size={44} />
              <div className="text-center">
                <div className="font-semibold">
                  {meta.home.name} <span className="text-muted">v</span> {meta.away.name}
                </div>
                <div className="text-xs text-muted">{meta.venue} · synthetic match, made-up clubs and players</div>
                {meta.league && (
                  <div className="mt-1 text-xs text-soft">
                    {meta.league.league} · Matchday {meta.league.matchday} ·{" "}
                    {ordinal(meta.league.table.find((r) => r.code === meta.home.code)?.pos)} v{" "}
                    {ordinal(meta.league.table.find((r) => r.code === meta.away.code)?.pos)} in the table · three other games at the same time
                  </div>
                )}
              </div>
              <Crest code={meta.away.code} colors={meta.away.colors} size={44} />
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
                value={`${settings.seed}:${settings.storyline}:${settings.fixture}`}
                onChange={(e) => {
                  const [seed, storyline, fixture] = e.target.value.split(":");
                  setSettings({ ...settings, seed: Number(seed), storyline, fixture });
                }}
              >
                <optgroup label="Matchday 10">
                  <option value="16:comeback:KSC-RVA">Kingsport City v Riverside Athletic (demo)</option>
                  <option value="16:comeback:AVU-DMA">Ashvale United v Dunmore Albion</option>
                  <option value="16:comeback:BWF-CHT">Brightwater FC v Coldharbour Town</option>
                  <option value="16:comeback:FHF-EMW">Fairhaven Forest v Eastmere Wanderers</option>
                </optgroup>
              </select>
            </Field>
            <Field label="Stat to follow (My metric view)">
              <select className={selectClass} value={settings.metric} onChange={(e) => setSettings({ ...settings, metric: e.target.value })}>
                {METRICS.map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Speed">
              <select className={selectClass} value={settings.speed} onChange={(e) => setSettings({ ...settings, speed: Number(e.target.value) })}>
                {[1, 3, 5, 10].map((s) => (
                  <option key={s} value={s}>
                    {s === 1 ? "Real time" : `${s}x${s === 3 ? " (recommended)" : ""}`}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <div className="mt-4">
            <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
              Commentary languages <span className="normal-case tracking-normal text-soft">(English plus up to {MAX_EXTRA_LANGS})</span>
            </span>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {LANGUAGES.map((l) => {
                const on = settings.langs.includes(l.id);
                const full = !on && settings.langs.length >= 1 + MAX_EXTRA_LANGS;
                return (
                  <button
                    key={l.id}
                    disabled={l.id === "en" || full}
                    onClick={() =>
                      setSettings({ ...settings, langs: on ? settings.langs.filter((x) => x !== l.id) : [...settings.langs, l.id] })
                    }
                    className={`rounded-full border px-3 py-1 text-[13px] transition-colors ${on ? "border-accent bg-accent/15 text-white" : "border-line text-soft hover:text-white"} disabled:cursor-not-allowed ${full ? "opacity-40" : ""}`}
                  >
                    {l.label}
                  </button>
                );
              })}
            </div>
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
