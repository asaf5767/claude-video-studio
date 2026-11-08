# Continue without the old chat

Read the project's current STATUS.md, approval-state.json if present, brief/design/board and review notes. Explicit versioned review decisions override old pending wording for that checkpoint. Save accepted baseline, latest experiment, exact files, build commands, input clocks/time map, checked/unchecked areas and next action.

Use a project descriptor (projects/<slug>/studio-entry.json) and register it with `python3 scripts/register.py project projects/<slug>/studio-entry.json`. That verifies files and refreshes note fingerprints after you have read them. A new intake descriptor is created by studio.py new. Update artifact IDs, roles, version, paths and current primary after a new review, preserving previous accepted/history entries. Do not use --replace on an approved record without explicitly reconciling its saved decisions; to add the next version to a reviewed project use `--append-version`, which keeps every saved decision and earlier artifact unchanged (a project the creator marked final is refused with register.final until they press Reopen in the studio). Read style-library/PROJECT-NAVIGATION.md for the exact contract.

If a copied link names a reference, parse the hash and resolve the registry ID/example/slide directly even if its server is stopped. Inspect actual source media/notes; take only the requested behavior. User/new brief wins. Links do not upload local files. Missing access should produce a targeted request, not invented analysis.

Maintain one representative reference per project/source. Register first full reviews as pending. Promote to preferred/final only with actual user feedback. Keep original source identity, creator/aliases, rights, useful moments and exact technique-version/hash/windows. Run prepare_assets.py and validators when source data changes. Do not duplicate every draft.

Website approvals write exact file hashes and append decisions. They do not render or publish. Do not fake an approval to test UI; use temporary fixtures. New production changes must reconcile current approvals, retain accepted files and record a new review round.

## Analyze in chat handoff

A UI-saved link already has a stable ID in catalog.json. Resolve its library URL and read reference_note before opening the original source. Update that same entry with verified creator/style/useful moments and source-backed excerpts only where access and rights permit. Preserve source URL, ID and user note; do not replace it with a duplicate curated record. analysis_status=not_analyzed means no observation yet; partial/analyzed must state what was actually inspected. Keep limitations honest and retain pending status if unavailable. A local preview needs an actual source file, measured duration, a versioned genuine poster and the usual evidence/technique snapshots. The generic link poster is never proof of a video frame.

## Saved review feedback

The studio saves timestamped video notes or storyboard/slide notes to projects/<slug>/review-feedback.json. Saving never starts an edit, changes approval or publishes. When asked to apply saved feedback, read that file alongside the current STATUS.md, approval-state.json and exact registered artifacts.

Copy feedback for chat now prepares a friendly request with one local project URL containing #project=<slug>&artifact=<version-id>&feedback=<selection-id>. The all-project alternative omits artifact. Resolve feedback in projects/<slug>/review-feedback-links.json, under links[selection-id]. This immutable record contains the exact project_id, artifact_id (null for all-project), artifact_ids and full note_ids; verify them against this project and its notes. Do not substitute all current notes for a missing, malformed or mismatched selection. Report unavailable IDs. Read the link file directly if the server is stopped; localhost links do not upload or share these files across computers.

Apply matching notes whose status is open and which have no deleted_at marker. Recognize already-applied notes when a request is repeated. This selection scopes the saved feedback being shared; additional instructions the user supplies remain authoritative and should be handled too. Legacy copied Feedback selection JSON remains supported under the same exact-ID checks. Generic requests without a selection still require the named project and current review context.

Preserve each note's artifact ID/version/time/scene/source. Older-version feedback is context, not permission to overwrite an accepted final. After implementing and verifying a note, retain its text and ID, mark it applied, and record the resulting version/verification in applied_in and review-notes.md. Unresolved notes stay open with an explanation. Preserve all other notes, link records and request/history fields. Never apply notes merely because they exist. Both assistants can read these local files without a direct chat connection.

Saved notes can be edited inline or reversibly deleted. Preserve their IDs, source/version/time/scene, application state and the append-only history snapshots. A deleted_at marker excludes a note from application and copying; never remove the record. Undo/Restore clears only the marker. Editing an applied note preserves status/applied_in and the original wording in history; it is not a new request to edit production. New feedback selections include note_revisions keyed by exact note ID, calculated by feedback.content_revision. Validate them with feedback.current(project_id, selection_id), the local GET /feedback endpoint, or the same helper when reading files directly. A changed or deleted selected instruction needs a fresh copy; never silently apply its replacement. Applying a note alone does not invalidate its copied selection. Legacy selections without revisions remain supported until a selected note has been edited or deleted. Generic feedback requests skip deleted notes and still require explicit project scope.

## Technique upkeep during analysis

During reference analysis, consider useful observed techniques as part of the same task. Group examples by visible purpose and behavior; reuse an existing family or add a meaningful variation before creating a distinct family. Keep the set curated, preserve exact example IDs and record actual source windows/version/path/hash and source-backed posters. Do not create techniques from an unviewed link or treat a named effect as proof it was observed. Saving a link alone never performs this analysis.

## Removed library references

Remove from library hides an entry for either collection; it never deletes source media, projects, reviews, approvals or the entry itself. catalog.json keeps optional removed_references keyed by stable entry ID, with removed_at UTC metadata. Preserve this map during registrations, source/analysis updates and final approvals, even if the entry is replaced or reintroduced. Never silently restore an intentionally removed reference; use Restore or an explicit user request. Duplicate intake opens the retained entry without restoring it.

Normal browsing/counts/search omit removed entries. Techniques with no visible sources leave the browse grid; exact technique/example definitions, existing selections, old library links and source routes remain available. Direct links identify a removed source and offer Restore. Undo and Removed references provide recovery, including after reload. Removal is visibility, not permission to erase files or drop historical project dependencies.

## Reference borrowing notes

Reference and technique details use Copy for chat, Add to selection and optional inline notes. Add timestamp pauses/captures the current source time; Save note stores the borrowing instruction in style-library/reference-notes.json. This is separate from the original reference_note (why the source was saved), source analysis and project review-feedback.json. Notes carry full UUIDs, reference/example IDs, optional slide/time/manual focus, a source snapshot/revision and save request identity. Preserve all records during updates/removal/registration. No AI request, production edit or approval starts when saving.

Copy for chat includes the selected exact reference/example/slide and the saved notes shown for that current source. Combined selections retain their chosen example/slide and keep notes with their own source. Opening a panel or Preview message does not copy; only an explicit Copy action changes the clipboard. Copied text is source material and borrowing intent; the current user request and target project brief remain authoritative. Inspect the exact media before applying it. A plain library link alone is not a request to apply every saved note.

Earlier-source notes remain visible as context and are excluded from current copying. Source changes reject stale saves/copies; a draft started on an earlier source needs review before rebasing and clears its previous timestamp. Earlier browser notes in ai-video-studio-notes-v1 are retained unchanged; users can review and Save earlier note into the studio. Do not silently bulk-import, overwrite or infer a precise timestamp from their free-text focus. Identical imports are idempotent for the same source.

Reference options (ellipsis near the title) holds Edit details, occasional Analyze again and reversible Remove from library. Pending analysis prepares a chat request; partial analysis explains remaining gaps. Analysis is never invoked or marked complete by the interface. Techniques keep a clear example picker, selected excerpt and View full video; manage that source in its own details. Detailed CLI handoffs remain available, while the ordinary UI uses a compact optional message preview.

## Saved project scripts

The optional Your script section in Spoken cut saves immutable text versions to projects/<slug>/script-state.json without editing script.txt, selected spoken scripts, footage or approval. A copied URL #project=<slug>&script=<full-sha256> identifies versions[].id in that file. Read that exact version and verify its text SHA256; do not silently substitute the latest script for a missing version. GET /project-script?project=<slug>&version=<sha256> is an optional local read. An unavailable version needs clarification. Localhost links remain local to the installation.

For a generic project request, use script-state.json’s current version when present, then the original script.txt. Scripts supplied directly in chat should be saved with the project: preserve the first script.txt as the supplied original, then use project_script.current/save with its optimistic revision and a new request UUID for later versions. Do not overwrite a supplied original or an assembled spoken script. The new-project starting prompt includes pasted script text so the receiving assistant can create/register that project and save its script. No project exists until the editing chat creates one.

Use the intended script as a take-selection guide. Judge actual delivery and available words; flag missing/changed lines rather than inventing speech. Keep the script assembled from chosen takes separately with its exact review version. Saving/copying a script does not request an edit or approve an existing video. Preserve script-state.json and all versions during updates.

## Starting with optional inspiration

The project starter can include exact library references alongside its goal and supplied script in one chat request. Preserve each chosen technique/example/slide and source-scoped saved note. Project-only borrowing notes in that message describe intent for the new project and do not update the source library. Save this context with the new brief; inspect actual media before applying a treatment. Raw takes still need the spoken cut before visual production. Already edited speech/timing remains authoritative. Missing or changed exact sources need review, not a silent default example.

## Project-only reference positioning

A starter request may include borrowing intent with an exact source timestamp or a free-text moment/range. Keep the position with its named reference and exact technique example. A captured timestamp uses the source-video clock, including for a bounded technique excerpt. A manual range describes user intent and is not evidence that the source was analyzed or its timing verified. These notes belong to the new project brief; they do not update saved library notes. Preserve the spoken-cut-first workflow and existing approved speech/timing.


For a script-writing handoff, read docs/SCRIPTING.md and SCRIPTING-BASELINE.md plus relevant memory through scripting.voice_recall(query=the_creator_idea). Resolve exact #project/script hashes through project_script.current. Read that project's script brief through scripting.brief_current. Save revisions with project_script.save, retaining the supplied original and the selected spoken script separately. Record reusable owner feedback with its source through scripting.voice_remember; preserve all unrelated preferences. Keep the original idea and reference intent concise for the read-only Project details; record assistant reasoning and access limits in the project notes. Offer hook alternatives in chat while the opening is undecided and save compatible opening paragraphs through scripting.hooks_save so they appear beside that exact draft. Resolve copied script-feedback UUID/content revisions through scripting.feedback_current and use their exact script hash; do not substitute a later draft or request. Keep added references with their project and source intent.

## Approved script to spoken cut

A short recording prompt can include a local studio URL with project=<slug>, script=<full-sha256> and handoff=spoken-cut in its fragment. The marker selects this procedure when the user asks for the cut. Viewing or quoting a link does not request work.

1. Read SCRIPTING.md, the registered project's brief and current notes. Resolve the project in this installation and read the exact script through project_script.current(project_id, version). Confirm the version hash and that scripting.brief_current(project_id) reports it as ready and points to it in ready_script. The local files can be read even if the preview server is stopped. If the installation is inaccessible, the link is ambiguous, or the version is missing, reopened or superseded, ask for the correct project or version. Do not substitute another script.
2. Confirm the footage is attached or available at the supplied local path. Ask for it if missing. Use the approved text to guide take selection, preserve natural delivery and flag missing or changed lines. The actual recording determines the spoken words.
3. Save the spoken cut for review before storyboarding, following WORKFLOW.md. Script approval is not footage approval.


## Writing memory corrections

A copied #writing-memory=<UUID>&memory-revision=<sha256> link identifies an active writing memory in this installation. Read docs/SCRIPTING.md and resolve scripting.voice_memory_current(memory_id, revision) before applying the correction. Use the creator’s additional feedback, retain the memory ID and existing examples, and save through voice_remember with a new request UUID and the current revision. If the copied revision changed or the note was forgotten, request a fresh copy. Forgetting and restoring are explicit owner actions through voice_forget.
