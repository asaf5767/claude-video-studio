# Third-party and sample notices

The root MIT code license does not replace third-party terms. Verify the final release manifest before publication.

Bundled UI fonts (all SIL Open Font License 1.1, Hebrew and Latin subsets): Secular One, Bellefair, Karantina (700), Heebo (variable 100–900), Suez One and IBM Plex Mono (500, Latin only). Formats: WOFF2 for Karantina, IBM Plex Mono and the Secular One Hebrew subset; WOFF for Bellefair, Heebo, Suez One and the Secular One Latin subset (subset locally with fontTools). Each family’s upstream copyright/OFL text sits beside its files as <family>-LICENSE.txt in style-library/dist/assets/fonts/. Do not rename font licensing or claim ownership. The bundled font assets, their notices and the project-authored ember-dot logo (style-library/dist/assets/brand/ember-dot.svg) are the only pre-existing visual assets in the starter. The synthetic sample (examples/studio-check) uses its own local copy of Inter under the OFL.

Installed dependencies are downloaded from their package registries and excluded from the source export. HyperFrames declares Apache-2.0 (the pinned version is recorded in package.json); GSAP 3.14.2 declares its own Standard “no charge” License (https://gsap.com/standard-license/); Pillow 13.0.0 declares MIT-CMU. Inspect full dependency licenses when distributing bundled executable output. Font licenses and package-lock/requirements hashes are preserved.

The generic saved-link SVG poster is project-authored and contains no third-party source imagery. It is an illustration of a saved link, not a video frame.

Presenter image in look previews: AI-generated, supplied and cleared by the studio owner. The source photo (looks/_presenter/presenter-source.png, not shipped) is a plain, owner-provided AI-generated portrait; looks/_presenter/presenter-cutout.png is a transparent cutout of it made locally with the studio's own background-removal tool (scripts/matte.py) and is the only version included in the release. It depicts no real person.

The synthetic smoke source is produced locally by FFmpeg color/test pattern and tone generators. The sample composition/board/text are project-authored technical fixtures. No human likeness, voice, downloaded reference video, brand logo, commercial sound effect or customer footage is included. Generated outputs stay ignored and are not in the starter source export.

FFmpeg and the render browser are separate tools with their own licenses/distribution notices. Optional MLX Whisper/model dependencies and any generated/cloud media retain upstream terms; users supply their own account and assess usage rights. No commercial subscription rights are granted by this kit.
