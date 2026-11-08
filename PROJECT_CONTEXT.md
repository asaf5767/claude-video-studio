# Your creative home

This is the reusable AI Video Studio starter, version **0.1.0-he.1**. Each installation starts with empty personal project/reference registries. Users bring their own footage, references, preferences and accounts. Existing installations keep their collections when upgrading.

## Start a new chat

Read AGENTS.md, docs/WORKFLOW.md and docs/DESIGN-SYSTEM.md. For creative work read the requested project's STATUS.md, approval-state.json, brief, current storyboard/design and latest review notes. Use SETUP.md for first installation and docs/HANDOFF.md to continue an existing project. CLAUDE.md points to the same shared instructions.

For script-writing work, use docs/SCRIPTING-BASELINE.md as the core shared editorial reference and docs/SCRIPTING.md for the Studio workflow, plus relevant local writing memory through scripting.voice_recall. An idea-first video can start in Script before recording; people with footage retain the existing editing path.

The chat is where you create. Projects holds spoken cuts, storyboards, designed reviews and final assets. Reference Library holds your work and outside inspiration, with exact technique examples and borrowing notes. How it works explains the process. Start a project prepares one request with optional script/inspiration; it does not create a project or send an AI message automatically. Raw takes get a spoken cut first; already edited speech is preserved.

Save project scripts, feedback and approvals with their exact versions. Reference notes belong to the selected source/example. Copy for chat prepares a local handoff; inspect the real source and current project before editing. Saving a source link or cover never means it was analyzed. Library removal is reversible and retains source files/dependencies. Read AGENTS.md for exact-link receiving and preservation rules.

Open with `python3 style-library/start.py` and use its printed HTTP address. Ports are discovered, not hardcoded. Local links work only in this installation. A new chat needs access to this folder and its saved notes.

## Software maintenance and upgrades

Read docs/RELEASE.md for application development/publication: branch → pull request → checks → merge → numbered release. Read docs/UPDATING.md before changing an installed studio. Package.json is the canonical release version; the installed interface, lock, setup prompts and release notes must agree. Markdown instructions provide workflow continuity; .env is private configuration/secrets, not context memory.

Publish reviewed application source only from the clean starter. Never copy a private production studio, owner catalogs, footage, techniques, reference covers, feedback, journals or accounts into a release. During an upgrade preserve those existing owner records and local customizations; never replace populated data with empty seeds. Check both clean installation and populated upgrade/rollback before a release. A merge and a published tag/release are separate steps and need appropriate user authorization.

## Validation boundaries

See docs/VALIDATION.md for observed results and docs/PILOT.md for independent-user checks. Full local media validation targets Apple Silicon macOS. Optional speech, browser connections, image generation and sound libraries depend on actual tools/accounts; no paid membership or private global skill is assumed. A synthetic sample or CI pass does not prove human take selection, audible quality or full assistant/platform compatibility. This remains a beta while those pilots continue.
