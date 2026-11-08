# Sound design

## Current defaults — October 27, 2026

No sound-library membership is required. Prefer original effects synthesized locally by Codex or Claude with code/FFmpeg, or suitable free assets. Simple clicks, snaps, pops, short impacts and airy movement can be generated locally; this is not a promise of a full generative music service. Optional generated-music services need verified availability and any required cost authorization. Music is a brief-specific choice; silence can be intentional. Keep the voice dominant.

Owners can use their own sound-library membership: ask which library and use supplied downloads or an available authorized integration. Do not display a Connect action or assume API/browser access merely because they subscribe. No library credentials or licensed asset collection is bundled with the starter.

Free resources are optional:

- [Freesound](https://freesound.org/help/faq/#licenses) offers effects under several licenses. Prefer individually verified CC0 files for the simplest reuse; CC BY requires credit and noncommercial files do not fit commercial campaigns. Downloads may require a free account.
- [Incompetech](https://incompetech.com/music/royalty-free/licenses/) offers a free Creative Commons music option with required credit. Check the chosen track and retain the generated credit.

Record the actual file, author/source URL, license/credit, acquisition date and project usage in asset-ledger.csv. Generated effects keep the generator source, settings and provenance. Free price alone does not establish reusable rights; do not copy music from reference videos. Keep optional vendor downloads separate from the open-source release.

## Plan, place and review

Plan sound alongside storyboard visuals. Use sparse event-driven accents, useful musical changes, drops and silence; do not accent every cut. Keep cues on the edited clock in sound-cues.csv and a version-local sound-plan.json. When cuts change, retime the cues and check their full attack/tail. Keep a music source clock moving through dips rather than restarting the same phrase.

The Edit view’s Sound section reads that exact version’s sound plan. It names recorded music and counts timed effects; missing records say unrecorded. Users listen with sound on, leave timestamped notes in Your feedback, or copy a sound-direction request for chat. This does not trigger audio generation or remix an existing version.

A compact plan can use {"music": false, "cues": [], "direction": "Sparse tactile effects; clear voice"}. A music object can include title, artist, source, file and rights. Existing richer plans remain valid; this view does not replace their details.

Use actual audio files in the project, mix/fade/duck against the voice, and check complete exports for clipping, pumping, chopped breaths and sync. Listen when the session supports it; record perceptual limits otherwise. Retain accepted exports/source files and create a new review for changes. Subscription changes never automatically remove or replace audio in existing projects.
