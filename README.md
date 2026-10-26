# Pitchside

AI agents that explain the game, not just the score.

Pitchside watches a synthetic football match event by event, works out which moments matter and why, checks every number before it goes on screen, and tells the story differently for each viewer: analyst or casual fan, your club, your player, your language.

Built for the Microsoft "Inside the Game" hackathon on Microsoft Foundry, Microsoft Agent Framework and Azure.

Work in progress. Setup instructions, architecture and the demo video will be added here as the pieces land.

## Layout

- `backend/` Python: match simulator, stats engine, agents, API
- `frontend/` React broadcast view
- `schemas/` JSON Schemas for events and overlays
- `data/samples/` seeded synthetic matches
- `infra/` Azure Bicep templates

All match data is synthetic. Clubs and players are made up.

## License

MIT
