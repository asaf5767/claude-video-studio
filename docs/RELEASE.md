# Maintaining and releasing AI Video Studio

This file is the shared release procedure for new Codex and Claude Code chats. AGENTS.md, CLAUDE.md and PROJECT_CONTEXT.md point here. Workflow knowledge belongs in these versioned Markdown files; .env is for private configuration/secrets and is never published.

## Two separate responsibilities

- **Maintainer publication:** reusable application code, docs, templates and empty examples from the clean public starter. A private production studio is never the release source. Port reusable fixes explicitly; do not copy personal projects, catalogs, techniques, media, notes or runtime evidence.
- **Installed-user upgrade:** update application files in that user's existing studio while retaining their projects, library, techniques, scripts, settings, feedback, decisions and local source customizations. Read docs/UPDATING.md. A release's empty examples are for first installation, never replacements for existing data.

## Normal development flow

1. Read the shared instructions, current status and Git status/remotes. Preserve existing changes and make a recoverable source checkpoint. Fingerprint owner metadata and media before release work.
2. Work on a descriptive branch. Open a pull request early or when the changes are ready; continue work on that branch. The PR explains the resulting behavior, validation and any upgrade actions.
3. Run the checks below. GitHub's required checks must pass for the exact PR head before merging. Protect main against unreviewed direct pushes, force pushes and deletion. A solo maintainer need not require an unavailable second human reviewer.
4. Merge the reviewed PR after publication authorization. Do not fold unrelated dependency proposals into a feature release. A renderer upgrade requires separate setup/render verification.
5. Publish a new numbered tag and GitHub Release at the tested merged commit, with a reviewed source ZIP, checksum manifest, changes, upgrade instructions and known limits. Never overwrite a previous release/tag. A merge alone does not publish a release.
6. Verify the public tag/tree/assets and anonymous installation after publication. Confirm the new tag is the newest published release by published_at and numeric version, which is what the version-free starter prompt requests; do not infer this from raw API list position. Retain the previous release and local checkpoint for rollback.

Publication, repository settings changes and messages to others need appropriate user authorization. Authorization to release application code does not authorize publication of creative media or sending team messages.

## Required checks before each release

CI runs once per pull-request update, plus pushes to main and numbered v* tags. Manual dispatch is available for verification. Superseded runs of the same PR are canceled; event/ref-specific concurrency keeps release tags and main independent. The required release-gate still fails unless every matrix job and audit passes. Check the exact current PR head before merging; an intentionally superseded run is not evidence for its replacement.

The standard-library/UI matrix uses Linux and macOS Intel on Python 3.11/3.13. macos-15-intel avoids the Apple Silicon hosted pool's observed runner-acquisition failures; it does not prove Apple Silicon media compatibility. Complete the separate Apple Silicon setup/render pilot locally and retain its actual evidence. Revisit the runner pin before its documented retirement or if hosted availability changes. Do not turn a canceled/incomplete job into a successful gate or weaken audits to merge an update.

- **Version:** package.json is the canonical release version. Match package-lock.json, the interface studio-version meta tag and release notes. README, INSTALL_PROMPT, SETUP and PILOT stay version-free: the starter prompt installs the newest published release (betas included), and README and INSTALL_PROMPT must carry the identical prompt. Never hardcode a tag there. Remove local-preview wording from a published build. Run `python3 scripts/check_release.py`.
- **Source/privacy:** review every path in release-files.txt and the actual Git tree, including new files. Exporter scanning is an additional guard, not a substitute for review. Owner projects, catalogs, removed-reference metadata, reference notes, previews, accounts, environments, logs and journals must be absent. Third-party font/dependency notices stay included.
- **Tests:** run Python unit tests, all Node UI tests, JS syntax and registry validators. Tests that write or approve use temporary fixtures. Run supported Python/OS checks in CI; do not mistake them for full media-platform support.
- **Dependencies/security:** audit the pinned npm, core Python and optional speech locks. Review local HTTP/path boundaries, outbound cover retrieval and editor launch if changed. Keep production tools pinned unless an explicit change is tested. Report actual findings and limitations.
- **Fresh installation:** export the exact source, extract into a fresh directory, run setup, confirm empty registries, then complete synthetic assembly and motion render with local media dependencies. Inspect the actual encoded sample. Never render/approve a real owner project as a release test.
- **Upgrade and rollback:** start from the previous published tag/ZIP in disposable Git and ZIP copies. Populate projects, raw/exported media, references, a real source-pinned technique, settings, scripts, feedback/links and approvals; record their bytes/hashes. Apply only reviewed source, rerun studio-only setup, validate/read the retained records and confirm all owner fingerprints match. Test rollback of affected source while keeping data created after upgrading. Exercise detection/preservation of local source customizations. Before applying the update, run the new release's `scripts/check_install.py --root <fixture>` against the previous release's manifest; it should report only the planted customization. Before restarting each upgraded fixture, run both registry validators, including the served-file check. Record the baseline and target versions and observed scope.
- **Exact commit:** after committing, `python3 scripts/check_release.py --git-ref HEAD` must confirm the committed tree exactly matches the selected source. Repeat for the final merged commit and generate its release archive there, so tags, source hashes and assets agree.

Use `python3 scripts/export_release.py` to create a new source archive and checksum manifest. The default name comes from package.json. It never stages or publishes. Preserve existing archives; do not zip the entire working folder or use `git add .` as a publication audit.

## Publishing the Hebrew studio to the public repository (RULING R49)

The public repository `asaf5767/claude-video-studio` is the update channel users `git pull` (R46), so anything in its history is public forever. Its history is built **only from release exports**: never push this development repository, its branches or its history there (they hold internal plans, the presenter source image and a personal path). Every commit on the public `main` is one export of `release-files.txt`, nothing else.

**First publication** (a fresh orphan history):

1. In this repository, on the reviewed, committed release commit: `python3 scripts/check_release.py --git-ref HEAD`, then `python3 scripts/export_release.py --name claude-video-studio-<version>` (`<version>` from package.json). The archive lands in `releases/`.
2. Make a new, empty folder **outside** this checkout, for example `../claude-video-studio-public`, and run `git init -b main` in it.
3. Extract the archive and copy the contents of its `claude-video-studio-<version>/` folder into the new folder, **without** `RELEASE-MANIFEST.json` (it goes with the GitHub Release assets, not into git). Windows: `Expand-Archive releases\claude-video-studio-<version>.zip -DestinationPath $env:TEMP\studio-export`, then copy; macOS: `unzip` into a temporary folder, then copy.
4. In the new folder: `git add -A`, check `git status` lists exactly the exported files, then `git commit -m "Hebrew studio v<version>"`. Run `python3 scripts/check_release.py --git-ref HEAD` there too (the tree must equal release-files.txt).
5. With the owner's explicit go-ahead only: `git remote add origin https://github.com/asaf5767/claude-video-studio.git` and `git push origin main`. If the public repository already has a `main` from older history, replacing it needs the owner's separate decision (it changes what existing clones pull); never do that by default.

**Later releases:** clone the public repository (not this one) into a fresh folder, delete every tracked file there, copy in the new export as in step 3, review `git status` (removed files must be intended), commit `Hebrew studio v<version>` on top of the public `main`, check, and push with the owner's go-ahead. The public history stays a sequence of export commits that `git pull` can follow.

`export_release.py` (and so `check_release.py`) refuses any shipped text file that contains a user-profile path in any spelling (`C:\Users\<name>\`, `C:/Users/<name>/`, `/c/Users/<name>/`, `/Users/<name>/`, `/home/<name>/`) or the owner's account name (checked against a stored hash, so the name itself is never shipped).

## Version policy and beta testing

Use numbered prereleases while independent-user/fresh-assistant coverage is outstanding: 0.1.0-beta.1, 0.1.0-beta.2, etc. Broad availability does not by itself prove stable compatibility. After the beta pilot passes, publish 0.1.0; use patch versions for fixes and minor versions for compatible feature additions. Describe any data migration and backup/rollback requirements explicitly.

GitHub's releases/latest endpoint excludes prereleases. Beta-aware checks must inspect the releases list and actual version/tag rather than report no update from that endpoint alone. The current Updates page shows the installed version and copies an assistant request; it performs no background remote check or automatic installation.

After the beta is published, a teammate can rehearse the real upgrade prompt from their existing installation after backing it up. Follow docs/PILOT.md in fresh Codex/Claude Code sessions with their own footage/accounts. Record anonymized results, resolve friction in a new release and link the public guide when available. Private media/logs never belong in public issues or release assets. No team messages are implied.
