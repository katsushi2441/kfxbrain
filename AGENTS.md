# kfxbrain Agent Rules

- Follow `/home/kojima/work/AGENTS.md`, `WORKFLOW.md`, and `QUALITY_RULES.md`.
- Keep broker credentials and order execution outside this project.
- Use only `gemma4:12b-it-qat` unless the user explicitly changes the model.
- Always send `think: false` to Gemma 4.
- Do not add silent model, template, or rule-based fallbacks. Return a visible error.
- Never commit `.env` or `public/kfxbrain_config.php`.
