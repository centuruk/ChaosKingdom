# Chaos Kingdom development instructions

## Agent and skill provenance

- Record every additional agent or skill actually used in `docs/production/workflow-tools.json` and the Korean manuscript's chapter 13. Include its name, instruction source, purpose, execution status, invoked tools and resulting artifacts.
- Distinguish reading a skill's instructions from executing its CLI or external service. Record subagent task IDs only after an actual spawn; role contracts are not execution history.
The game is an original fictional medieval officer strategy game, written in Python with pygame-ce. Preserve 200 officers, 20 castles, 30 outposts, and a maximum of 1000 deployed soldiers per side.

Keep world state and simulation independent of Pygame. Use stable IDs, seeded randomness, explicit validation, and atomic saves. Every gameplay change must preserve save compatibility or provide an explicit migration. Combat, editor, and report tools must use the same battlefield schema.

Update the Korean manuscript in docs/book alongside meaningful design or implementation work. Record actual tests and failures. Clearly distinguish shipped behavior, experiments, future proposals, and external validation that has not happened. Never invent agent runs, playtester feedback, image provenance, or platform build results.

Use the existing GPT Image Generator assets and their manifest; retain original files and prompt provenance. Korean text and game statistics belong in runtime UI. Do not bake changing map ownership or troop counts into artwork.

Validate meaningful changes with the relevant tests. Before packaging, run the full pytest suite, validate-maps, and the beta audit when simulation changed. Rebuild book screenshots after visual changes. Build PC binaries on their actual target OS. Do not commit saves, diagnostic bundles, caches, or build output.

Development role specifications in docs/production/agents.json are a documented workflow, not evidence that separate agents are active. Use delegation only when authorized by the user or applicable higher-level instructions.
