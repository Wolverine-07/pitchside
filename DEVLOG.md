# Devlog

Short notes on decisions and dead ends, newest last.

- Oct 26, 16:10 IST: Started. Deadline is Oct 27, 11:59 pm Pacific. Code in Python 3.12 (uv) because 3.14 is too new for some Azure libraries.
- Oct 26: Simulator is a possession-chain model, not random events. Rosters use a fixed seed per club so the same players appear in every match.
- Oct 26: First calibration gave about 8 goals a game. Attackers were being placed on the goal line when the team pushed up; capped open-play positions at the defensive line and lowered the xG intercept. Now about 2.9 goals, 80% pass completion, 20 fouls a game over 20 seeds.
- Oct 26: Fixed a clock bug where the second half was counted twice (match "lasted" 145 minutes).
- Oct 26: Demo seed 16 with the comeback storyline: RVA score in the 5th minute, KSC win 2-1 with goals at 68' and 71' during their pressing spell.
