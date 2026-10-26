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
