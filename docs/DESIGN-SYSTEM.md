# Starting creative direction

These are adjustable defaults. The project brief and explicit user feedback take priority.

**Studio look (this fork, הסטודיו של אסף).** The studio UI follows Assaf’s website: dark ink #07070a, text #f5ede5, ember #ff6b2c accent with a soft ember glow, cards #121216 with #1f1f24 hairlines, pill buttons. The logo is a glowing ember dot (also the favicon); the name is “הסטודיו של אסף / Assaf’s Studio” with “עריכת וידאו עם Claude / Video editing with Claude”. Fonts are bundled OFL subsets: Heebo for UI, Karantina 700 for section headings, Secular One for page headlines (a slot-machine headline cycles Secular One, Bellefair, Karantina, Heebo 800 and Suez One), Bellefair for quiet serif lines, IBM Plex Mono for English labels. No italics; RTL first. The footer credits the upstream AI Video Studio (MIT). Notes below about the paper/olive/lime look, the “ai.” mark and Archivo/Instrument/Inter describe the upstream studio, not this fork’s UI.

Warm graphite #191b1e, ivory #f3eee5 and persimmon #f2734f. Archivo Black carries the headline, Instrument Serif italic adds a short human aside, Inter supports captions. Real logos keep their proportions/colors. (These are video defaults; the studio UI chrome is described above. Bundled UI fonts carry their own OFL notices.)

Lead with the creator's expression and performance. Keep headroom/eyes/hands readable through every crop. Use genuine product footage for behavior; conceptual graphics explain relationships. Large clear headlines carry one thought. Short captions transcribe actual edited speech; headline copy can summarize. Remap timings after cuts.

Motion should reveal, compare, emphasize or connect. Use smooth arrivals and enough reading hold; avoid arbitrary drifting logos and fixed repeated zooms. Audio accents should match meaningful clicks/cuts/arrivals. Music is optional. Inspect the full rendered motion and sound, not only still frames or a successful encode.

Use 1080×1920 for typical vertical video; choose carousel and presentation dimensions separately. Safe margins in studio.config.json are starting points, not permanent platform guarantees. Natural color and clean subject edges matter; blur/isolation is footage-specific.

Save reusable user preferences here after clear general feedback; keep one-off choices in the project's design notes. Do not promise virality or results.

## Studio interface direction

October 27 UX review: preserve warm paper and olive identity, with the studio brand updated to the waitlist green as described below. Lead project screens with the actual preview, short changes/next action and clear version context. Group historical and current versions within their creative stage. Keep useful working files behind readable Project details/More downloads. Use legible supporting text and clear controls; distinguish main navigation, library formats and filters. Newest saved references come first when creation dates are known. Collecting local feedback remains optional and separate from chat execution or approval.

## Studio interface refinement — October 27

Use waitlist lime #DFFF54 for the studio mark and small brand accents; keep everyday action buttons muted #DCE5A9 with hover #CEDD8E, and use dark green #445114 for legible accent text/focus/navigation on paper, and quiet olive surfaces. Keep production-video brand profiles and semantic review states separate. Source switching stays visible as My work / Other creators / All; search and sorting stay available, with additional filters expanding inline and removable active filters. Reference guidance explains the single-copy and multi-selection paths in two short lines. Feedback capture visibly confirms the attached moment/version and supports changing/removing it. Saving confirms the exact note; Copy feedback for chat clearly names the displayed version and selects only its saved open notes. All-project feedback is an explicit alternative.

October 27 follow-up: label the time capture action **Add timestamp**. Keep it available to replace the note time after the video moves, with one Note time label and Remove; omit a separate Change action or duplicate attached-state button. Copied requests use natural wording and one compact durable feedback link instead of raw file paths/JSON. The footer uses the same ai. studio mark, Built by credit, GitHub and a local Updates page.

October 27 V18: keep **AI Video Studio** as the brand, with **Video editing with AI** as its descriptor. A quiet Updates utility sits beside How it works; installed version is secondary and hidden at narrow widths. Do not imply an update is available without verifying an actual newer release. Anchor card palettes/creator credit to the bottom across each row regardless of tag/title length. Library removal uses More options → Remove from library for both collections, immediate Undo and a persistent Removed references recovery list. Keep files, source IDs, project history and saved links.

October 27 V19: ordinary reference actions are **Copy for chat** and **Add to selection**. Optional borrowing notes stay inline beside the preview, with the same timestamp/save/copy progression as project feedback. Keep the original reason for saving a reference as quiet background context. Put reference management in a compact title ellipsis menu; align icons with real SVGs, keep removal separated/last, and preserve Undo/Restore. Technique choices use larger preview cards, radio selection and exact excerpts, without outward arrows that imply navigation. Place View full video by the preview. Analysis prompts reflect pending/partial/completed state; reanalysis is occasional. Only explicit Copy buttons copy. Hide generated text behind optional Preview message; ordinary users do not choose a technical handoff format.

## Sound, previews and editor access — UX V20

Use a centered dot for a single selected technique example. Keep public cover-image availability separate from analysis: Awaiting analysis and Partly analyzed reflect recorded inspection, not image presence. Missing previews use state-aware copy: Ready for analysis for pending sources, Preview not saved for partial sources, and Video preview unavailable for other saved sources. Cover images never imply playable video.

Open in HyperFrames is a quiet action beside downloads in Edit, tied to a known version-local composition. The explicit launch creates a separate working copy. Sound stays in Edit as a concise expandable summary with the existing timestamped feedback flow. Generated/free sounds are the starting point; owner-provided libraries remain optional and have no assumed connection.

## Analysis-first reference intake — UX V21

After saving: Reference saved. Next: analyze it. Copy analysis request is the primary explicit clipboard action, with a visible Copied confirmation and paste guidance. Public cover retrieval stays quiet and separate; no user-facing preview-retry controls or cover-status toasts. Pending placeholders explain style notes, useful moments and a preview when available without guaranteeing playable media. Partially analyzed sources retain progress-specific copy. Pending borrowing controls remain available in a secondary Use the saved link section; drafts, saved notes and exact-source copying retain their existing behavior.

## Review and script context — UX V23

Latest names the newest review; Final appears only after explicit approval succeeds. A registered older preferred video does not block final promotion of the current exact reviewed version. Keep earlier exports, source analysis and technique examples attached to their original media. Version menus dismiss on outside click and Escape, returning focus on Escape. Spoken cut offers optional Your script, Save script and Copy request for chat, with explicit saved/unsaved feedback. Distinguish supplied script from the selected spoken script. New-project requests can include the script without a required wizard step.

## Starter journey — UX V24

Starting belongs to Projects: one modal, shared by guide entry points. Use Start a project as its title; keep the expressive introduction in How it works. Show Video/Carousel/Presentation as keyboard-accessible visible choices. Goal precedes optional source location/script; adapt source wording by format. Copy request for chat stays explicit and keeps the modal open with Copied/Done and a visible next step to paste and attach raw video/source material. Outside/Escape/Close retain the draft and return focus. A narrow viewport fills the screen with scrolling fields and visible footer actions. Session-only browser draft persistence is independent of production project files. Existing start URLs remain valid.

## Project starter inspiration — UX V25

Keep optional complexity out of the default form. Show raw-video attachment guidance and tuck file locations under Use a file on your computer instead. Use one clear Copy request action and concise paste/attachment guidance; avoid repeating the button label in surrounding copy.

Inspiration for the visual edit is optional below the script and can be added later. Browse within the same dialog, with a back path, search, visible Videos/Techniques and source toggles. Show exact technique examples and readable source previews. Keep the project form, script and edited request intact while browsing. Show chosen thumbnails, optional project-only borrowing notes and removal; importing a browser selection is explicit and does not modify it. One final request combines context and exact sources. Raw takes get the spoken cut first; approved speech/timing stays intact. Keep source-pinned saved notes visible and block stale copying rather than substituting another example.

## Starter reference notes and back behavior — UX V26

Keep intake additions optional. In Edit my footage, requirements belong in the main brief and links belong with inspiration, as refined below. Within a starter reference, preview and selected card edit one project-specific note. Show Add timestamp only when a playable timeline is available; pause/capture exact source time and show a removable time chip. A cover image has no playback clock, so offer an optional Moment or time range field. Keep typed notes without adding the reference automatically. Once selected, include the same note/position in Copy request. Preserve exact technique example/source windows and do not silently carry timing to a changed source. These draft notes do not alter library borrowing notes.

X and Escape go one level back: preview to library, library to starter, then close. Return to the same search/source/type and browsing scroll. Keep the visible Back links and accessible action labels in sync. Escape must work when a replaced native video control leaves focus outside the dialog. Retain ordinary fullscreen Escape behavior.


## Script simplicity — November 3

Lead Script with the readable draft and a quiet Saved/Versions/Refine in chat toolbar. Present a readable document with an explicit Edit script affordance. Grow the editor with its text; avoid nested scrolling, duplicate headings/taglines, extra preference links or required readiness steps. Editing reveals a sticky Save changes/Cancel bar; comparison handles a conflicting/earlier version. Original idea/reference intent belongs read-only under Your idea & references; assistant reasoning/access diagnostics belong in project notes. Writing memory remains in the footer. Offer a few distinct hooks in chat and save compatible opening alternatives with the draft. Hook options keeps compact previews visible near the first line and marks the selected choice. Choosing one preserves page position and earlier versions, briefly highlights the changed words, and offers local Undo under the current revision guard. Respect reduced motion. Keep selection optional and preserve accepted direction. Keep scripts, history, owner preferences and existing editor workflows intact. Script toolbar controls share a 44px height and vertical alignment, with a comfortably inset chevron, consistent corners and visible keyboard focus. Check the actual control bounds and mobile layout rather than assuming inherited styles align.


## Focused project starter — November 3

Start with What are you making? (Video / Carousel / Presentation), then Where are you starting? for video. Help me write a script and Edit my footage explicitly identify the two jobs. A fresh draft waits for that choice before revealing fields on the same screen, with no Next step or separate wizard. Returning drafts retain their choice/text. The writing path shows one idea field and two quiet, optional disclosures: Add a draft and Use a reference video. Any one input is sufficient. Keep editing-only library selection, extra details/links and request preview out of this path, and never silently include their hidden values in generated writing requests. Use Copy request as the writing footer’s single action, with the header X as its close action. Clipboard failure can reveal a manual-copy fallback. Keep desktop dialog top position stable as fields appear; mobile keeps its full-screen form and visible footer actions. Retain carousel/presentation and exact visual-reference handoffs; the footage path follows the refinement below.


## Focused footage starter — November 3

Edit my footage leads with What would you like to make? The brief includes the purpose, audience and anything the edit should preserve. Add your recorded script starts collapsed when empty. Add inspiration groups Browse library and Paste a video link; either produces a selected card with one short What would you like to borrow? field. Exact library examples, source-pinned notes and timestamps remain available under Reference details, without filling the default card with technical context. Pasted links are project-only intent; adding one never downloads, analyzes or catalogues the source.

Copy request is the primary footer action, beside a quiet See message control. The message is an exact read-only preview of what will be copied, visually distinct from creator inputs. Explain Attach your video in chat after copying this request immediately above Or include a file location. The expanded field is Video file location, without another optional label, followed by Included in your copied request. Keep the footer concise: Paste into your editing chat. Use comfortable 44px controls, subtle olive input focus and a visible footer on narrow screens. Avoid repeated optional guidance, an extra Close action and empty Details/Other links fields. Earlier requirements remain editable in the footage brief; populated earlier link text stays visible under inspiration. Preserve original browser draft fields and custom request text. Keep footage-only details out of newly generated script-writing requests.


## Script iteration — November 3

Keep Script focused on writing: saved draft, optional compatible openings, and a visible What would you like to change? area below it. Refine in chat focuses that area. Add a reference is one quiet disclosure for a video link plus borrowing intent. Feedback or reference intent alone enables Copy feedback for chat. Copy saves an exact local handoff and confirms the next action to paste; it never sends an AI request. Preserve draft text across reload/navigation and never quietly move unsent feedback to a newer script. Keep copied feedback recoverable with its earlier version. New reference intent remains with the project. Use Your idea & references as the only ordinary context disclosure in Script; omit duplicated summary/next-step metadata and raw working-document controls. Keep their underlying files and other editing/review interfaces intact.


## Visible script changes — November 3

Keep the opening choices integrated with the document, including the selected choice after a change. Avoid collapsing choices or moving the page after selection. Put Opening updated and Undo beside the options, with a brief highlight on the actual changed opening. Edit script explicitly enters the existing document editor; Save changes and Cancel remain within reach while writing, and save confirmation is visible even when the toolbar is offscreen. Feedback with manual edits uses Save & copy feedback: save first, bind the request to the resulting version, preserve earlier feedback, and stop on a conflict. Keep an active editing session intact during background refresh.


## Script approval and recording handoff — November 4

Place Approve script at the end of the current saved script for an idea-first project. After approval, keep the script readable, mark the exact version approved and put Hook options in a compact disclosure that retains all alternatives and lead-ins. Ready to record explains that recording happens outside the studio, then names Copy prompt for chat before asking the creator to paste and attach raw footage. The copied text states the intended cut and review, with a version-pinned studio link. Keep the receiving instructions in HANDOFF.md. Copy prompt for chat is the primary action; Make changes reopens the script and preserves history. The approved state hides writing controls and retains feedback drafts. Keep the copy action on one line on narrow screens. Do not add a recording tab or advance to a spoken cut before it exists.


### Starter draft arrival

When a copied writing request returns a saved script, show “Your script is ready” with the project name and **Open draft**. Use the existing modal footer if it still holds that request; show the action on Projects as well. Keep the user’s current page, text and playback in place until they choose Open draft. Match by the exact request ID and confirm a saved script before showing the action.


## Writing memory — November 5

Present readable learned notes with optional source details and actual earlier/preferred wording plus feedback. Keep correction in the editing chat through a compact, exact-ID handoff. Forget saves immediately, with Undo restoring the same note and evidence. Use Done to close. Start empty on a fresh installation. The assistant maintains supported lessons during script work and recalls relevant examples for later chats; the interface does not infer preferences or call a model.
