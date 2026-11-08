# Sound: effects, music, mix

Read `docs/SOUND-DESIGN.md` for the studio's defaults. The voice always stays on top.

## What the choices mean

- `sound`: `music-calm` / `music-energetic` use a music file the creator uploaded (`materials.json` tag `music`, prepared to `work/media/*.wav`) whose note or name does not say it is the voice-over. No suitable file means no music: never download, generate or take music from a reference video; say in the step detail and the reply that they can add a music file and send again. `no-music` means none.
- `sfx: true` (the default): sparse effects on visual events, as the look card describes (a whoosh on a cut or a title, a soft pop when a sticker or word lands, a tick on an underline). Never on every word. `sfx: false`: none.

## Make effects locally (free, no account)

Write each into the version's `sfx/` folder, then mix them at their times:

```bash
ffmpeg -nostdin -v error -n -f lavfi -i "anoisesrc=color=pink:duration=0.45:amplitude=0.6" -af "highpass=f=400,lowpass=f=5000,afade=t=in:d=0.15,afade=t=out:st=0.2:d=0.25,volume=0.5" -ar 48000 -ac 2 "projects/<id>/versions/v01/sfx/whoosh.wav"
ffmpeg -nostdin -v error -n -f lavfi -i "sine=frequency=880:duration=0.09" -af "afade=t=out:st=0.02:d=0.07,volume=0.4" -ar 48000 -ac 2 "projects/<id>/versions/v01/sfx/pop.wav"
ffmpeg -nostdin -v error -n -f lavfi -i "sine=frequency=2000:duration=0.03" -af "afade=t=out:d=0.03,volume=0.3" -ar 48000 -ac 2 "projects/<id>/versions/v01/sfx/tick.wav"
```

Effects sit 16-22 dB under the voice. Listen-check by reading loudness, not by guessing.

## Mix

Build one `versions/vNN/mix.wav` with a single ffmpeg call: the voice (the cut's audio, or the prepared voice-over), each effect delayed to its cue time (`adelay=<ms>|<ms>`), and the music looped/trimmed to the length, ducked under the voice (`sidechaincompress`) and faded out at the end. Then normalize to -16 LUFS with a true-peak ceiling:

```bash
ffmpeg -nostdin -v error -n -i "projects/<id>/versions/v01/cut.mp4" -i "projects/<id>/versions/v01/sfx/whoosh.wav" -filter_complex "[1:a]adelay=1200|1200[w];[0:a][w]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11" -ar 48000 -ac 2 "projects/<id>/versions/v01/mix.wav"
ffmpeg -nostdin -hide_banner -i "projects/<id>/versions/v01/mix.wav" -af ebur128=peak=true -f null -
```

The second command prints the measured loudness: about -16 LUFS integrated, true peak under -1 dB. Record the plan in `versions/vNN/sound-plan.json` (`{"music": false or {"file", "title", "rights"}, "cues": [{"time", "sound", "why"}], "direction": "<one line>"}`): the studio's Edit view reads it. Generated effects and owner-supplied music go into `asset-ledger.csv` with their source.
