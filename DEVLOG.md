# Devlog

Short notes on decisions and dead ends, newest last.

- Oct 26, 16:10 IST: Started. Deadline is Oct 27, 11:59 pm Pacific. Code in Python 3.12 (uv) because 3.14 is too new for some Azure libraries.
- Oct 26: Simulator is a possession-chain model, not random events. Rosters use a fixed seed per club so the same players appear in every match.
- Oct 26: First calibration gave about 8 goals a game. Attackers were being placed on the goal line when the team pushed up; capped open-play positions at the defensive line and lowered the xG intercept. Now about 2.9 goals, 80% pass completion, 20 fouls a game over 20 seeds.
- Oct 26: Fixed a clock bug where the second half was counted twice (match "lasted" 145 minutes).
- Oct 26: Demo seed 16 with the comeback storyline: RVA score in the 5th minute, KSC win 2-1 with goals at 68' and 71' during their pressing spell.
- Oct 26: Stats engine (MatchState) is the only place numbers come from: possession, pass difficulty, xG, momentum, PPDA, tempo, a control vs chaos index, and moment detection with evidence attached.
- Oct 26: First pass flagged 26 momentum swings a match, which would flood the screen. Raised the threshold and added a 5-minute cooldown; now about 10. The demo match flags Kingsport's pressing spell in the 64th minute, four minutes before their equaliser.
- Oct 26: Agent layer on Microsoft Agent Framework 1.23: Director, Analyst, Narrator, Verifier, Persona, Linguist as executors in one workflow graph, with a switch-case edge from the Verifier (pass, retry, fall back to template).
- Oct 26: The Verifier is plain code, not another model call. It checks every number in a caption against the stats engine, and the Analyst's cited numbers are matched metric by metric. A model can't argue its way past it.
- Oct 26: Installing the `agent-framework` meta-package pulled in ~30 integrations (including a 120 MB SDK) and stalled; switched to core + foundry + openai + orchestrations only.
- Oct 26: Templates-only mode runs a full match in 0.5 s with 15 moments on air, so the app works even with no model at all.
- Oct 26: First real runs on gpt-4.1-mini (Poland Central, Azure for Students). All captions verified, but reading them showed problems the number check can't see: "frantic finish" in the 10th minute, "Kingsport wins", and a team's pressing credited to one player. Added context and grammar checks to the Verifier and stopped naming a player on team moments. Now the Verifier sends a few drafts back each match and the rewrites come out right.
- Oct 26: gpt-5.4-mini has no quota on the student subscription, so everything runs on gpt-4.1-mini for now (code supports a separate deeper model for the Analyst).
- Oct 26: The runner used to pause the match while the agents worked (~14 s per moment). Live mode now streams events continuously and a background worker delivers overlays when they're ready.
- Oct 26: Agents read numbers over MCP per match: the API gives each live match a key and the Analyst's MCP client sends it as a header.
- Oct 26: Deploying to Azure Container Apps took four tries. ACR Tasks are blocked on Azure for Students, so the image is built locally and pushed. The first environment came up as an "express" environment, which can't pull from a private registry with a password or a managed identity; the Bicep now asks for a standard environment with the Consumption profile. Then Container Apps rejected Docker-style layer media types, so infra/oci_retag.py rewrites the manifest to OCI types in the registry without re-uploading layers.
- Oct 26: Live mode handles up to three moments in parallel (one workflow run per batch), so cards keep up at 5x speed. Agent traces now go to the Application Insights resource connected to the Foundry project, so they show up in Foundry's tracing view.
- Oct 26: A/B test, 5 seeded matches, 102 moments, same model and tools: neither one agent nor the team stated a wrong number. So no accuracy claim. Reading the captions side by side, the single agent is generic ("RVA's momentum swung sharply") and the team explains why with specifics; the Verifier sent back 15 drafts. Scoring both with Foundry evaluators (groundedness, relevance, coherence, fluency) to put a number on it.
- Oct 26: The A/B captions showed a few slips no rule covered ("after the half-hour" in the 53rd minute, "at 41 minutes"), so the Verifier now checks stated minutes against the moment.
