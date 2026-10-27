# Pitchside

**AI agents that explain the game, not just the score.**

Pitchside watches a synthetic football match event by event, works out which moments matter and why, checks every number before it goes on screen, and tells the story differently for each viewer: analyst or casual fan, your club, your player, the one stat you care about, in any of eight languages.

Built for the Microsoft *Inside the Game* hackathon with Microsoft Foundry, Microsoft Agent Framework, MCP, Azure Container Apps and Azure AI Speech.

- **Live app:** https://pitchside-web.mangostone-cc37c1d4.polandcentral.azurecontainerapps.io (pick a club and a player, choose 3x speed, kick off; the first load can take ~20 s while the container wakes up)
- **Demo video:** _link coming_

![Pitchside broadcast view](docs/screenshot.png)

## Why I built this

> _Your sentence goes here, in your own words._

## What it does

One pipeline, five stages, as the challenge asks:

1. **Ingest.** A match simulator streams synthetic events (passes, carries, dribbles, shots, tackles, interceptions, pressure, fouls, cards, substitutions, sprints, possession changes) as they happen. Three other fixtures of the same matchday play alongside it.
2. **Interpret.** A deterministic stats engine turns them into live numbers: possession, pass difficulty, xG, momentum, pressing intensity (PPDA), tempo, a control vs chaos index and a live win probability. It flags candidate moments with a significance score and the evidence behind each one.
3. **Explain.** Agents work out why a moment matters and back it up with numbers they fetch through MCP tools, including the live league table.
4. **Render.** Every insight becomes a timed overlay object ([schema](schemas/overlay.schema.json)) that a broadcast graphics system could draw over a live feed. The React app is one renderer.
5. **Personalize.** The same insight is rewritten for casual fans, analysts, a chosen club, a chosen player and a viewer who follows one stat (possession, chance quality, shots, pressing or win probability). Each viewer picks up to three languages besides English (Hindi, Spanish, French, Portuguese, Arabic, German, Japanese); captions, voice and Ask answers come in that language (Arabic right to left) while the interface stays in English, and Azure AI Speech reads captions aloud in a native neural voice.

What a viewer gets on top of that:

- **The Coastal League.** Eight fictional clubs. The featured match is one of four on matchday 10; a live table moves with every goal, and goals elsewhere that matter to the two clubs on the pitch come through as "around the league" moments.
- **Half-time and full-time recaps**, written by the same agents from stats-engine facts, for every viewer and language.
- **Ask Pitchside.** Viewers ask the studio a question ("How is Wexavi playing?", "What does this do to the table?") and a Pundit agent answers from live data, in their language, with every number verified before it is shown.
- **Watch any of the four matchday fixtures.** Every club has its own squad, colours, playing style and home ground; the rest of the league plays around whichever match you pick.
- **Studio mode.** For broadcasters: no caption airs until a producer approves it, and a producer's own edits are checked by the Verifier against the live match before they go out.
- **Why trust this?** Every caption in the feed opens to show the Analyst's reasoning, the numbers it rests on (as the stats engine reported them) and its path through the agents: what the Verifier sent back and why, how many audience versions were rewritten, and how each language was produced.
- **How it works**, in the app header: the five stages, the agents, and what I measured, including where the agent team is not better than one agent.
- **Broadcast touches:** goal banner and animated goal replays, scorers on the scoreboard, a shot map and a last-action strip in analyst mode (pass length, difficulty and ball speed; shot xG and speed), a live card for the player you follow, a win-probability bar and a scores ticker.

## How it works

```mermaid
flowchart LR
    sim[Match simulator] --> stats[Stats engine<br/>MatchState]
    stats -- candidate moments --> D
    subgraph wf [Agent Framework workflow]
        D[Director] --> A[Analyst] --> N[Narrator] --> V{Verifier}
        V -- reject, with reasons --> N
        V -- failed twice --> T[Template line]
        V -- pass --> P[Persona]
        T --> P --> L[Linguist]
    end
    A <-. MCP tools .-> stats
    L --> O[Overlay API<br/>WebSocket] --> UI[Broadcast view]
    stats -- score, momentum, player tags --> O
```

**Numbers come from code, words come from agents.** The stats engine is the only source of numbers. Agents read it through an MCP server (`/mcp`), and the Verifier, which is plain code rather than another model call, checks every caption before it airs:

- every number must match a fact the stats engine produced, metric by metric for the Analyst's citations;
- a named player must be part of the moment;
- no end-of-match talk before the 80th minute, British plural verbs for clubs ("Kingsport press"), no chatbot phrases.

A rejected caption goes back to the Narrator with the reasons. If it fails twice, a template line built only from verified numbers airs instead, so the broadcast never waits.

| Agent | Job | Falls back to |
| --- | --- | --- |
| Director | Picks which moments air and when, keeps variety, never floods the screen | Rule: highest significance, varied type |
| Analyst | Explains why the moment matters, citing numbers fetched over MCP (stats and league table) | The moment's own summary |
| Narrator | Writes a headline and a live line in commentator style, and the half-time and full-time recaps | Template line |
| Verifier | Checks numbers, names, timing and style; sends drafts back | (plain code, cannot fail) |
| Persona | Rewrites for casual, analyst, club, player and metric viewers; one retry with the Verifier's reasons | The verified base line |
| Pundit | Answers viewers' questions from live data (Ask Pitchside) | An honest "I can't confirm that" |
| Linguist | Localizes into each viewer's languages, one parallel call per language; every translation is re-checked for numbers and names, with one retry | Azure AI Translator (football glossary, names protected), then English |

Shared state is one `MatchState` per match. Each live match gets its own key, and the Analyst's MCP client sends it as a header, so tools always answer for the right match. Live matches stream continuously while up to three moments are handled in parallel.

## Results

I tested the agent team against a single agent: same model (`gpt-4.1-mini`), same stats tools, same five seeded matches (104 moments). One agent writes each caption in one go; Pitchside runs its full workflow. Scripts: [`evals/ab_test.py`](backend/evals/ab_test.py) and [`evals/foundry_eval.py`](backend/evals/foundry_eval.py); raw output in `backend/evals/`.

| | Single agent | Pitchside team |
| --- | --- | --- |
| Wrong numbers (checked against the stats engine) | 0 / 104 | 0 / 104 |
| Foundry groundedness | 103 / 104 | 102 / 104 |
| Foundry relevance / coherence | 104 / 104 | 104 / 104 |
| Foundry fluency | 104 / 104 | 100 / 104 |
| Broke broadcast style rules (mostly "at 55 minutes") | 18 / 104 | 0 / 104 |
| Versions per moment | 1 caption, English | 4 audiences x 3 languages (now 5 x up to 4) |
| Drafts sent back by the Verifier | n/a | 29 (6 fell back to templates) |
| Time per moment | 1.2 s | 8.8 s |

What I take from this:

- **On accuracy the two are level.** With the same tools, a single agent didn't invent numbers either, so I'm not claiming the team is more accurate. The team passes the style rules by construction, because its Verifier enforces them.
- **The team earns its extra 7 seconds by doing more:** an explanation of why the moment matters, four audience versions in three languages, a checked trace for every caption, and a safe fallback when the model misbehaves. Live play absorbs the time by handling moments in parallel.
- **Foundry evaluations made the team better.** The first run scored the team at 91/102 for groundedness against 100/102 for the single agent: the Narrator and Persona agents were embellishing ("lifting spirits", "a wild spell", "after the half-hour" in the 53rd minute). That led to the audience rules, minute checks and stricter player mode; the re-run scored 102/104.

## Brief coverage

| Brief item | Where |
| --- | --- |
| Ingest synthetic events as they happen | `backend/pitchside/sim`, `runner.py` |
| Interpret into stats, patterns, context | `backend/pitchside/stats` |
| Explain why moments matter (control vs chaos, pressure, rhythm) | stats engine moments + Analyst agent |
| Render on screen, timed and machine-readable | `overlays.py`, `schemas/overlay.schema.json`, `frontend/` |
| Personalize: modes, favourite club, favourite player, favourite metric | Persona agent, setup screen, My metric view |
| Player identification with speed and distance triggers | `sprint` and `physical` events, player tags |
| Pass quality: distance, accuracy, difficulty | `stats/metrics.py` `pass_difficulty` |
| Ball speed and shot speed | simulator physics, `shot_speed_kmh`, `ball_speed_kmh` |
| Narratives, milestones, recaps | Narrator agent, milestone moments, half-time and full-time recaps |
| Data innovation | the simulator, five sample matches in `data/samples`, `schemas/event.schema.json` |
| Multi-language storytelling | Linguist agent, eight languages, Azure AI Translator backup, native Speech voices |
| Auto-eventing from video | not built; see roadmap |

## The data

Everything is synthetic, with made-up clubs and players. The simulator is a possession-chain model: each action depends on where the ball is, who has it, how much pressure they're under, how tired they are and the score (a side that is behind after the hour presses higher and plays more directly). Calibrated over 20 seeds it averages about 2.9 goals, 80% pass completion, 22 shots and 20 fouls a match, and the hardest runner covers about 12 km. Any match replays exactly from its seed. Seed 16 with the `comeback` storyline is the demo match.

## Run it locally

```bash
cd backend
uv sync
uv run pytest                                   # 37 tests
PITCHSIDE_PROVIDER=templates uv run python -m pitchside.run   # whole match, no model needed
cp .env.example .env                            # add your Foundry endpoint, deployment and key
uv run uvicorn pitchside.api:app --port 8000

cd ../frontend && npm install && npm run dev    # http://localhost:5173
```

Every push runs lint, the tests and the frontend build in GitHub Actions (`.github/workflows/ci.yml`).

Generate a match: `uv run python -m pitchside.sim --seed 7 --out ../data/samples/seed7.jsonl`

Use the stats tools from any MCP client (for example GitHub Copilot in VS Code): point it at `http://localhost:8000/mcp/`.

## Deploy to Azure

`infra/main.bicep` provisions Log Analytics, Application Insights, a container registry, a Container Apps environment (Consumption profile), Azure AI Speech, Azure AI Translator and the app, with the model key held as a Container Apps secret. `infra/deploy.sh` builds the image, pushes it and rolls it out. Agent traces are exported with OpenTelemetry to the Application Insights resource connected to the Foundry project, so every workflow run, agent call and tool call shows up in Foundry's tracing view.

Things I hit on an Azure for Students subscription: ACR Tasks are blocked (so the image is built locally), the default "express" Container Apps environment can't pull private images (so the Bicep asks for a Consumption workload profile), and Container Apps wanted OCI layer media types (`infra/oci_retag.py` rewrites the manifest).

## Limitations and next steps

- The event stream runs in-process; the next step is Azure Event Hubs between the simulator and the stats engine so several consumers can share one match.
- Auto-eventing from video (running a pose and ball detection model over a feed) is out of scope for this build.
- The Verifier's style checks are rules; some wording slips through (for example a wrong time reference it doesn't have a rule for yet).

## Acknowledgements

Built with Microsoft Foundry, Microsoft Agent Framework, Azure Container Apps, Application Insights, Azure AI Speech, Azure AI Translator and the Model Context Protocol. I used Claude Code as a coding assistant during the build.

## License

MIT
