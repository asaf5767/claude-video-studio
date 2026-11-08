# Changelog

## 0.1.0-beta.11 — Safer existing-studio updates — 2026-11-05

- Before media setup installs anything, inspect the pinned renderer’s running preview inventory and stop safely if this installation owns an active preview or the inventory cannot be verified. Other installations are left running. Fresh installs and studio-only mode need no preview check.
- Explain the existing-install update path, recoverable composition-source checkpoints, active-editor handling and disposable verification in the shared update guide. Do not automatically restart a preview on an accepted original composition. HyperFrames 0.9.16, its security override and other dependency pins remain unchanged.

## 0.1.0-beta.10 — Renderer notice correction — 2026-11-05

- Make the HyperFrames dependency notice version-free after the renderer upgrade; its Apache-2.0 license is unchanged. Retains the tested 0.9.16 renderer, Undici 7.30.2 security override, Node requirement and CI reliability changes from beta.9. No application logic, dependency pin or owner-data change.

## 0.1.0-beta.9 — Renderer upgrade and CI reliability — 2026-11-05

- Upgrade the pinned local HyperFrames renderer from 0.8.144 to 0.9.16, with a scoped Undici 7.30.2 override for the upstream HTTP dependency security fixes. GSAP and Python dependency pins stay unchanged.
- Full media setup requires Node 22.12.0 or newer and rejects older versions before installation. Studio-only setup still needs no Node or renderer packages.
- CI runs once per PR update, retains main/release-tag checks and manual dispatch, cancels superseded PR runs and uses the supported macOS Intel pool. The full Linux/macOS Python matrix, audits and release gate remain. Apple Silicon setup/render validation stays a separate release pilot.
- Existing projects, media, saved reviews, editing working copies, libraries, scripts and writing memory are retained. Saved videos are not re-rendered by an application update.

Follow docs/UPDATING.md from the published release and preserve local customizations.

## 0.1.0-beta.8 — Library registration and approval — 2026-11-05

- Assistant/CLI reference registration automatically records a creation date for new undated entries and preserves existing dates on replacement. Older undated entries stay unknown; their dates are not fabricated during upgrades or approval.
- Registering a project and its own video reference in either order stores the exact link. The reference and project link save together with conflict guards and recoverable writes.
- Final approval reconnects one missing link when project ID, current version and media path match exactly. It retains the existing library entry, original added date, analysis and media. Ambiguous, removed, archived, foreign, wrong-version/path and hash-mismatched candidates remain blocked.
- Newest added continues to mean original added date. Approval does not move an existing entry by changing its date. No dependency, renderer or owner-data migration.

Follow docs/UPDATING.md in your existing installation. Preserve all owner data and local customizations.

## 0.1.0-beta.7 — Script writing — 2026-11-05

- Start videos with Help me write a script or Edit my footage. The focused writing form accepts an idea, draft or video reference, with shared writing guidance and private writing memory.
- Optional Script section with a readable growing editor, exact saved versions, retained drafts and Refine in chat. Integrated opening choices show the current selection, highlight changed words and offer Undo while preserving saved versions. Edit script exposes Save changes/Cancel, and Save & copy feedback saves manual edits before copying the exact revision request. A visible feedback area with an optional reference copies an exact local revision request; original context stays under Your idea & references.
- Approve the current script before recording. Hook options stay available, and the approved view provides a copyable handoff for raw footage and the spoken cut.
- Writing memory retains supported lessons with actual wording, feedback and source context. Readable notes offer Correct in chat and Forget with Undo. New chats recall relevant examples, while each fresh installation starts empty.
- Simplified footage starter: one brief, optional recorded script, unified library/link inspiration cards and an exact read-only See message preview beside Copy request. Existing browser drafts and exact references are retained.
- A compact shared scriptwriting reference provides flexible principles and an optional storytelling framework. Writing and refinement continue in the editing chat.
- Copied starters have exact request IDs so the matching saved script can be opened without losing an in-progress form.
- No embedded AI service, analytics integration, dependency or renderer changes.

### Upgrading from beta.6

Use Updates in your existing studio and follow docs/UPDATING.md. Apply reviewed source only; preserve projects, media, catalogs/techniques, scripts and their histories, briefs, hooks, feedback, settings, writing memory and local customizations. Scripting records are optional and created only by explicit saves. Earlier footage-first projects continue normally.


## 0.1.0-beta.6 — 2026-11-01

- A newly registered project now appears first on the Projects home instead of last. Replacing an existing project keeps its place, and reference registrations are unchanged.

### Upgrading from beta.5

Follow docs/UPDATING.md. This release changes scripts/register.py and its docs and tests only; there is no interface, dependency, renderer or data change. Your existing project order is kept as it is: only projects registered after updating go to the top. Prepared for the November 2 public launch.

## 0.1.0-beta.5 — 2026-11-01

- Registry validation now fails when a registered library file exists but the local server would refuse to serve it (outside projects/<slug> or references/<slug>, hidden, or an unsupported type). Updates run this before restarting, so an upgrade cannot silently stop someone's videos from playing.
- New read-only `scripts/check_install.py` compares installed application files with a published release manifest and lists identical, modified (local customizations or older copies) and missing files, so "am I up to date?" no longer depends on the version label.
- docs/UPDATING.md and the Updates page request now require confirming that existing projects and the reference library still open and play before restarting.

### Upgrading from beta.4

Follow docs/UPDATING.md. There is no dependency, renderer or data change. If `python3 style-library/library.py validate` now reports a registered file that would not be served, that item already could not play in the studio: reconcile its registration or the installation rather than moving media. Prepared for the November 2 public launch.

## 0.1.0-beta.4 — 2026-11-01

- SETUP.md points new installations to the current release; it previously named beta.2, which could steer a fresh setup to an older build than the install prompt requested.
- Current-version labels in STATUS.md, BRIEF.md and PROJECT_CONTEXT.md are corrected, and the release check now verifies them along with SETUP.md so they cannot fall behind again.
- studio.config.json no longer names a paid sound library as the default: generated or suitable free sounds come first and a personal library stays optional, matching docs/SOUND-DESIGN.md.

### Upgrading from beta.3

Follow docs/UPDATING.md. This release changes documentation, the studio.config.json sound-default wording and the maintainer release check only; there is no application code, dependency, renderer or data change. If you customized studio.config.json, keep your version. Prepared for the November 2 public launch.

## 0.1.0-beta.3 — Public Launch — 2026-10-31

- Edit saved project feedback inline, or delete with Undo and persistent recovery in All saved notes. Prior wording and applied history remain attached to the original version.
- Show applied feedback on earlier cuts, storyboards and edits, with links to the resulting version when registered. Order notes by newest save; chat copies include only open notes and detect subsequent edits.
- Keep the scene strip directly below its preview, with saved feedback in a separate scrollable list. Retain note reading positions and reveal the selected scene when returning from the overview.
- Browse storyboard scenes without jumping to the page header or resetting the scene strip/overview. Keep scene drafts and keyboard focus.
- Replace the heavy feedback field outline with a subtle olive focus border and glow, including forced-color keyboard support.

### Upgrading from beta.2

Follow docs/UPDATING.md in your existing installation. Apply the reviewed source release and retain your projects, videos, references, techniques, scripts, settings and feedback. There is no destructive migration; feedback history/deletion fields are added only when used. Back up first and retain local source customizations. Older interfaces do not understand deleted-note markers, so follow the rollback guidance before using an older version’s feedback-copy controls.

This is the public launch beta for Monday, November 2. The Mac-first validation scope remains; no dependency or renderer upgrade is included.

## 0.1.0-beta.2 — 2026-10-28

- Start projects from one modal with retained drafts, optional recorded scripts and videos/technique inspiration. Preview and selection cards share project-only notes and timestamps. X/Escape return one level at a time.
- Refined library source toggles, search/filter/sort controls, bottom-aligned card credits and reversible removal with Undo/Restore. New references lead with an explicit analysis request; public covers load quietly and refresh thumbnails.
- Cohesive reference/technique notes with exact examples, optional timestamps, saved notes and compact Copy for chat. Project review feedback retains exact versions and immutable selections.
- Stage/version navigation, larger storyboard inspection, optional versioned project scripts and corrected final promotion while preserving earlier sources and techniques.
- Optional isolated HyperFrames working copies and version-specific Sound summaries. Generated/free sound defaults; personal sound libraries remain optional. Renderer pins are unchanged. Optional transcription filelock/setuptools pins are patched for current security advisories.
- Consistent green branding, shared footer/header Updates entry and installed version. Copied update requests include the official repository, beta releases, backup and owner-data preservation.
- Documented branch/PR/check/merge/release workflow, release consistency checks and populated upgrade/rollback validation. Fresh installs start empty; existing collections, media and decisions are preserved.

### Upgrading

Follow docs/UPDATING.md in the existing installation. Back up first; apply reviewed source files only and retain local customizations. No owner-data schema migration is required from beta.1. This remains a beta: independent-user upgrades and fresh-assistant/other-platform media workflows need pilot feedback.

## 0.1.0-beta.1 — public pilot

MIT code license, concrete repository/setup prompt, prerequisite guidance, read-only capability reporting, optional browser/transcription/image/sound guidance and regression checks for setup readiness. Personal registries/media remain excluded. Fresh assistant/team and other-platform results remain pilot work.


## 0.1.0-rc.3 — analysis as the next step

Prominent analysis prompt immediately after saving and on pending-reference reopening, Not analyzed badges, Keep browsing, secondary utilities in More options and updated help. Clicking Analyze remains a copy/paste handoff and never completes analysis. Existing library data and source identity are preserved.

## 0.1.0-rc.2 — reference intake

Add reference form, optional title/creator/note, honest saved-link cards, duplicate handling, basic detail editing and Analyze in chat copied requests. Explicit local save guards and stale-edit checks preserve existing analysis and project decisions. No automatic source fetch or AI connection.

## 0.1.0-rc.1 — local candidate

Extracted the reusable studio shell and media helpers into an independent starter; empty personal registries, local licensed fonts, shared assistant instructions, setup/preflight, synthetic smoke workflow, hardened loopback/file routes, review persistence tests and explicit release export. Public release and fresh-user pilot pending.
