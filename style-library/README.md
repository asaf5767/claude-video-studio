# Your local studio

Projects is the home for current cuts, actual storyboard frames, reviews and final assets. Reference Library keeps reusable examples; How it works explains the chat-driven process. Start with `python3 style-library/start.py` and use the printed HTTP address.

Personal projects.json, catalog.json and settings.json are created from empty/configurable example files. They are ignored and excluded from source releases. The synthetic demo is generated locally by scripts/smoke.py; no private creator media is included.

Use scripts/register.py for an inspected project or pending reference descriptor. Read PROJECT-NAVIGATION.md and docs/HANDOFF.md before updating versions or approvals. The + is only browser-local selection. Copy for chat copies a library URL; notes/handoff is optional. Local links do not share media across computers or automatically send chat messages.

The site runs on Python's standard library. The media helpers/render sample need SETUP.md's additional tools. Bind to loopback only; see SECURITY.md. Do not expose this personal service publicly.

## Save inspiration from the interface

Add reference accepts a public http(s) source link and optional title/creator/what caught your eye. It saves locally, then tries the public page’s cover image without downloading or analyzing the video. Duplicates open the existing reference without replacing its notes. New cards say Awaiting analysis; cover images and analysis are separate. Missing covers use the Video preview unavailable poster. Edit details updates basic metadata while preserving source/analysis and rejecting stale edits. Analyze in chat copies a short request with the library link, original URL and saved note. Paste it into the editing chat in this workspace; the assistant enriches the same entry after inspection. No automatic AI service or account connection is implied.

Reference saves use exact loopback Host/Origin, explicit JSON/header/size checks, safe local paths, shared catalog locking and backup/rollback/recovery. Their transaction backups live with other private metadata journals and are excluded from release exports. Reference saving does not approve or modify project checkpoints.

## Review-first interface

Stages keep their versions together. Project details and More downloads keep production notes accessible without crowding review. Storyboards offer larger thumbnails, a scene overview and an enlarged viewer. Add timestamp captures the paused video time; storyboard notes retain the selected scene. Save feedback writes into the local project. In chat, say “Apply my saved feedback for [project].” It does not send automatically or approve anything.

The library defaults to Newest added using saved creation dates, with Oldest added and Name A–Z alternatives. My work / Other creators / All stays visible as a source switch. Creator, technique/category and availability filters expand inline; active filters remain removable beside the result count. Undated legacy entries retain relative library order; dates are never inferred from filenames or fabricated. Register new inspected entries through scripts/register.py reference; it records a real created_at UTC timestamp when absent and preserves saved dates during replacement. Existing undated entries remain unknown until reliable evidence supports a correction. Existing reference IDs, exact examples, selections and personal notes are retained.

## Clear feedback and reference controls

Add timestamp pauses the preview and shows a persistent Note time/version label with Remove. Move the video and use Add timestamp again to replace it. Save feedback confirms persistence separately. Copy feedback for chat copies a friendly request with a compact local feedback link. Its immutable exact-note selection lives in projects/<slug>/review-feedback-links.json and resolves to full project/artifact/note IDs. Repeated copies of the same selection reuse its record; note text and status stay unchanged. All saved notes offers a separately labeled all-project request. Clipboard failures expose the same request for manual copying. Run `node --test style-library/test_feedback_ui.js` for the focused feedback UI regressions alongside the Python suite.

The footer includes the studio ai. mark, configurable Built by credit, GitHub and Updates. #updates shows this copy’s version, a link to the latest changes on the main branch of https://github.com/asaf5767/claude-video-studio and a copyable assistant update request (git pull, or the main ZIP copied over without touching owner data, then the setup-studio skill and a restart). See docs/UPDATING.md. The page itself never fetches or installs anything.

## Library visibility and header utilities

Updates is reachable beside How it works and in the footer; the installed version appears quietly on larger screens. The brand remains AI Video Studio, described as Video editing with AI. Card palettes and creator credits stay at the bottom of their row.

Open a video/carousel reference, then Reference options (⋯) → Remove from library to hide it. This works for both collections. Undo immediately, or use Removed references → Restore later. Saved links can still open the retained entry and restore it. Normal technique browsing omits removed sources; saved exact examples remain usable. Projects, media, notes, approvals and browser selections are kept.

Visibility metadata lives in catalog.json under removed_references. GET/POST /reference-visibility use stable IDs and revisions; writes require exact same-origin loopback requests and the explicit action header, bounded JSON, the shared lock, current-entry checks and atomic recovery journal. Registrations/approvals retain the removal map, and duplicate source saves do not restore hidden items.

## Reference borrowing notes

Reference and technique details use Copy for chat, Add to selection and optional inline notes. Add timestamp pauses/captures the current source time; Save note stores the borrowing instruction in style-library/reference-notes.json. This is separate from the original reference_note (why the source was saved), source analysis and project review-feedback.json. Notes carry full UUIDs, reference/example IDs, optional slide/time/manual focus, a source snapshot/revision and save request identity. Preserve all records during updates/removal/registration. No AI request, production edit or approval starts when saving.

Copy for chat includes the selected exact reference/example/slide and the saved notes shown for that current source. Combined selections retain their chosen example/slide and keep notes with their own source. Opening a panel or Preview message does not copy; only an explicit Copy action changes the clipboard. Copied text is source material and borrowing intent; the current user request and target project brief remain authoritative. Inspect the exact media before applying it. A plain library link alone is not a request to apply every saved note.

Earlier-source notes remain visible as context and are excluded from current copying. Source changes reject stale saves/copies; a draft started on an earlier source needs review before rebasing and clears its previous timestamp. Earlier browser notes in ai-video-studio-notes-v1 are retained unchanged; users can review and Save earlier note into the studio. Do not silently bulk-import, overwrite or infer a precise timestamp from their free-text focus. Identical imports are idempotent for the same source.

Reference options (ellipsis near the title) holds Edit details, occasional Analyze again and reversible Remove from library. Pending analysis prepares a chat request; partial analysis explains remaining gaps. Analysis is never invoked or marked complete by the interface. Techniques keep a clear example picker, selected excerpt and View full video; manage that source in its own details. Detailed CLI handoffs remain available, while the ordinary UI uses a compact optional message preview.
