# What your studio can do

The starter contains the working app, editing helpers and shared instructions. Your coding assistant supplies the judgment and any connected browser or generation tools. Copying the repository does not copy anyone’s accounts, logins, footage or personal reference library.

Run `python3 scripts/setup.py --check` for a local capability report. A status of `check_in_chat` means the assistant must actually test that capability in its own session. It does not mean the capability is missing. `ready_for_media` means prerequisites are present; the synthetic smoke workflow verifies a real render.

| Capability | Included or installed | What to check |
| --- | --- | --- |
| Projects, library, saved feedback and review decisions | Python standard library and empty personal registries | Run setup, then start the local HTTP service. |
| Cuts, proxies and audio processing | Helpers use FFmpeg/FFprobe | System tools must be installed. |
| Motion graphics and compositing | Pinned HyperFrames, GSAP and render-browser download | Run the full synthetic smoke workflow. |
| Contact sheets | Project-local Pillow | Installed by full setup. |
| Speech/word timing | Local whisper.cpp + a Hebrew (ivrit.ai) or English ggml model | Windows and macOS; `python scripts/transcribe.py <media> <out.json> --language he/en`. Setup downloads and SHA-256-checks the binary/model (see SETUP.md); until that lands, install whisper.cpp yourself or supply a word-timed transcript. |
| Reference browsing | Assistant’s available browser tools | Verify the connection, site access and login in that specific browser/profile. |
| Simple sound effects | Assistant-written code and FFmpeg | Clicks, pops, tones and noise-based whooshes can be synthesized locally. Listen and refine; tool availability does not establish sound quality. |
| Images and advanced generated media | Optional assistant feature or user-supplied service | Verify availability and cost first; supplied images and code-authored graphics remain usable alternatives. |
| Music and specialist sound libraries | User’s optional account/assets | Use only with appropriate project rights and any required authorization. |

## Two browsers, two jobs

HyperFrames’ render browser turns local designs into video frames. It does not sign in to Instagram or automatically give a coding assistant interactive browser tools.

Codex’s desktop browser capability may already be available in the app. Check the actual session’s browser tools and permissions; see [OpenAI’s browser guidance](https://learn.chatgpt.com/docs/browser#computer-use-in-the-browser). Claude Code can use its official [Chrome integration](https://code.claude.com/docs/en/chrome); the user enables that connection and it can share that browser’s login state. Availability also depends on the user’s app, plan and organization settings. A downloaded repository must not silently enable access to a personal browser.

If a source asks for sign-in, the user signs in in the browser the assistant can access. A login in a different browser/profile may not carry over. Some sources remain blocked or cannot be downloaded. Ask for the original video file, a usable source or screenshots, and record the inspection limit. Never invent a creator, preview, timing or sound analysis from an inaccessible link.

Add reference saves a link and note, then tries to save its public cover image without downloading or analyzing the video. Copy analysis request explicitly copies a request for inspection; it does not automatically download or send anything. A reference downloader is not installed by the baseline. Use an available, authorized method when appropriate, preserve original files and record provenance. Reference inspiration is separate from permission to reuse its footage or audio.

## How the assistant should handle a missing capability

1. Check the local report and actual tools in the current chat.
2. Use existing supported tools before suggesting another service.
3. Guide the user through browser connection/sign-in or authorized official prerequisite installation when needed.
4. Offer an uploaded file, existing transcript, supplied image or locally synthesized effect as appropriate.
5. Ask before paid services or system-wide changes. Do not weaken security settings to make setup pass.
6. Report what was actually checked. An unavailable optional tool does not stop the core studio from opening.

The full media workflow has been verified on Apple Silicon macOS on the maintainer’s machine. Windows, Intel Mac, Linux and fresh Codex/Claude sessions are pilot coverage. See [PILOT.md](PILOT.md). The website itself uses Python’s standard library; that is separate from a claim of complete media compatibility on every platform.

Saved studio feedback is local data in projects/<slug>/review-feedback.json. Either assistant can read it when you ask to apply your notes. No direct chat integration, extra AI key or background agent is required. The website captures a version and a video time or storyboard scene; it does not start the edit.
