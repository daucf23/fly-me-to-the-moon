# Twitter edit: three fly brains, one rocket

Source reviewed: `video/Screen Recording 2026-09-11 at 4.55.06 PM.mov`.
34:19.78, 2338 × 896, approximately 60 fps, no audio track. Reviewed sampled frames
throughout, with additional samples around the flyby, re-entry and landing; the
windows below are selection ranges, not frame-accurate edit decisions.

**Recommendation: a 75-second, captioned miniature mission story.** Use the fiery
re-entry as a three-second cold open, then launch, explain the neural control in one
clear visual, fly around the Mun, and bring everyone home. The unusual premise gets
attention; the visible cause-and-effect and actual landing make it satisfying.

## Proposed cut

All source times below refer to the MOV, not the telemetry or cockpit replay.

| Finished timeline | Picture and source selection window | Suggested text / purpose |
| --- | --- | --- |
| 00–03 | Fiery capsule, around **24:00–24:15**. Tight crop, near real time. | **“Three fly brains. One rocket.”** A glimpse of the stakes before returning to launch. |
| 03–10 | Launch, **00:25–00:55**. Remove the opening pause menu and idle time. | **“I put three fruit-fly connectome models in the cockpit.”** |
| 10–20 | A close-up of one seat's panel, sampled spikes and output during ascent; select within **00:45–01:30**. Keep a short continuous interval at 1×. | **“Pixels in → neural spikes → steering out.”** Identify the panel, recorded neural sample and command in sequence. Small supporting caption: “Computer guidance + control augmentation.” |
| 20–27 | Booster separation near **02:20–02:35**, then an orbital view around **05:30–05:45**. | **“Orbit.”** Use hard cuts across the long circularization rather than showing an entire fast-forwarded burn. |
| 27–35 | Departure burn, choose within **06:20–08:50**. Optionally show Bob's instrument shrinking and cutoff near the end after checking exact sync. | **“Next stop: the Mun.”** Reuse the panel explanation through a visible example rather than another text block. |
| 35–44 | Recognizable Mun approach around **14:50–15:15**, plus a flyby view selected within **15:35–16:20**. | **“232 km above the Mun.”** The strongest clearly recognizable moon view matters more than a frame at exact closest approach. |
| 44–51 | Return correction, select within **17:00–18:30**. | **“Getting home needed one more correction.”** The log supports this: the uncorrected return periapsis was below ground. Avoid implying the brains planned that correction. |
| 51–63 | Re-entry, **23:20–24:55**. Favor the bright plasma near **23:30 / 24:10**; modest acceleration or short cuts. | **“4.5 G. Three passengers.”** Label 4.5 G as the mission's peak unless the text is synchronized to that instant. Let the visuals breathe here. |
| 63–71 | Parachutes, select around **26:10–26:55**, then final descent/ground contact **34:00–34:12**. | **“And… home.”** Return to real time for the touchdown payoff. |
| 71–75 | Landed capsule around **34:10–34:18**, with a brief crew/result insert if readable. | **“3 crew home. One continuous mission.”** Then “Code + full flight in the post.” |

The run log reports a landing, not a splashdown: use “landed” / “home” in this edit.
The dark flyby and landing shots benefit from a modest shadow lift. Do not invent a
sunlit view or supplement with a different mission without labeling it.

## Composition

The original side-by-side capture is about 2.6:1. Shrinking all of it into a phone feed
makes both the rocket and the instruments hard to read. Do not retain that layout for
the whole edit.

Make a **4:5 mobile composition** the primary cut, with gameplay dominant and a
compact, synchronized instrument area below it. For the mechanism explanation,
expand one seat to fill most of the frame; return to the spacecraft for the big
moments. Crop/reposition per shot so the rocket or capsule stays large. Preserve the
Kerbal faces for one or two reaction shots where they are readable. Favor purposeful
reframing and hard cuts over constant zooming and transitions.

The game begins at approximately x=900 in the 2338-pixel source. This gives a useful
starting crop for editing, but inspect its exact edge before export. The live cockpit
occupies the left side, with unused black space beneath it. A fresh telemetry replay
can produce a cleaner, readable insert without asking for another flight.

Use large captions, one thought at a time, and a small chapter indicator if helpful:
“LAUNCH → MUN → HOME.” Keep full telemetry tables and explanations in the companion
post. Make the first frame a useful poster frame, not a logo or a blank title card.

## Preserve the actual causal evidence

A few uninterrupted seconds of panel → sampled activity → command are worth more
than a minute of flashing instruments. Keep the gameplay and telemetry at the same
source time whenever they appear together. Apply the same speed changes to both.

The backup `runs/mun-flies-12-video/cockpit.mp4` was rendered at a fixed five frames
per second, one per telemetry row. Its duration differs from the screen recording,
so one fixed starting offset will not necessarily maintain synchronization. Use the
logged `wall` timestamps to regenerate/resample the insert, or use the cockpit already
captured in the MOV. Confirm sync at launch, a burn cutoff and landing.

Call the raster **“recorded neural activity (sample)”**. It is a selected 1,000-neuron
sample per seat, not a display of all 166,700 neurons. Preserve the distinction between
raw neural command and the augmented control actually received by KSP. Do not retain
an unqualified “every command came from a fly” caption: the flight computer also
provides guidance, rate damping, roll control and safety overrides.

## Sound and pacing

The source has no audio. My first choice is a short human voiceover, burned-in
captions, and restrained music that builds through launch and return. Use a brief
musical pause before touchdown. Any added rocket sounds are sound design, not audio
captured from this flight; don't present fabricated mission-control speech as a real
recording. The edit should remain understandable muted.

Possible voiceover spine:

> “These are three copies of a fruit-fly connectome. I gave each one a cockpit
> instrument. One controls pitch, one yaw, one throttle. A flight computer plans the
> route and stabilizes their commands. Their job is to fly the needles. Orbit.
> Around the Mun. One correction for the trip home. And all three Kerbals landed.”

Keep the humor in the premise and perhaps one line: **“A very small flight crew.”**
Avoid stacking memes over the footage. Remove loading, solver waits, long coasts,
repeated burns and most of the twelve-minute descent. Mark accelerated footage and
preserve the complete recording as the evidence companion.

## Deliverables and export

1. Primary ~75-second mobile edit, with readable captions and thumbnail.
2. Uncut recording and explanation linked through the repository or a longer-video
   host. A separate technical walkthrough is optional, not required for launch.
3. Post text explaining the computer/connectome division and linking the evidence.

Keep an edit master at the chosen delivery resolution; export an MP4 using H.264,
YUV 4:2:0 and AAC if audio is added. Thirty fps is enough for this cut. Check a private
upload/draft on a real phone before finalizing resolution and bitrate, especially
small neural graphics and dark space scenes. This is an editorial recommendation,
not a promise about feed ranking.

X currently documents non-Premium uploads up to 140 seconds and 512 MB. The proposed
cut fits comfortably inside those limits.
[Source: X video help](https://help.x.com/en/using-x/x-videos).

The edit was rendered on 2026-09-12. Deliverables are in `video/exports/`: a 75-second scored MP4, an identical silent MP4, a cover image and an edit decision list. The reproducible build is `scripts/edit_twitter_video.py`. The source video is unchanged. The delivered cut uses burned-in captions and an original synthesized instrumental score rather than voiceover.

## Revision 2

Delivered under `video/exports/v2/`. The film now leads with **the fly-ght computer**
and separately demonstrates steering and neural throttle control. A slower ambient
score replaces the arpeggio, with a -25 LUFS target (about 7 dB quieter).

SAS was used during both solver searches and time warp, then re-enabled after mission
completion. The selected active-flight footage now avoids those intervals. The final
live shot ends at ground contact with SAS off; a graphical results card replaces the
post-mission SAS-on footage. The HUD has not been hidden or altered. The explanation
retains the computer's guidance, gyro and safety roles and explicitly notes SAS's
solver/warp use. See the v2 README for the selected-frame audit and late-descent battery
stand-down context.


## Landscape revision (v3)

Delivered `video/exports/v3/fly-ght-computer-16x9-v3.mp4`: 75 seconds at
1920 × 1080, 30 fps. Gameplay dominates the landscape layout; recorded fly
activity and full steering/throttle panels sit beside it. Identical v2 source
intervals retain the SAS-off selection and synchronized cockpit evidence.
Original 108 BPM war drums replace the ambient score, with a re-entry build
and a pullback for touchdown. Final audio measures -21.5 LUFS, -2.0 dBFS
true peak. Both earlier edits are preserved. Rebuild using
`scripts/edit_twitter_video_landscape.py`. All 2,250 frames decoded cleanly,
and a contact sheet of every scene was reviewed.


## Black-and-amber mission revision (v4)

Delivered `video/exports/v4/fly-ght-computer-16x9-v4.mp4`: same 75-second
SAS-off selection in 16:9. Pure black, white headlines, amber accent. FLY
is highlighted in the FLY-BY-WIRE wordmark and quoted in the opening
“FLY”-ght computer headline. One informative headline per segment replaces
the previous title/subtitle pairs. Sidebar text is reduced to data labels.
The original score now has minor-key ostinato, changing harmony, rising
textures, faster re-entry percussion, and a near-silent pause before
ground contact. Measured audio: -22.0 LUFS, 9.0 LU range, -2.0 dBFS true
peak. All frames decoded cleanly; all 15 scene midpoint frames reviewed.
Rebuild with `scripts/edit_twitter_video_mission.py`. Prior versions preserved.


## Continuous-score and cyan revision (v5)

Delivered `video/exports/v5/fly-ght-computer-16x9-v5.mp4`. Retains the
75-second edit, SAS-off selections, synchronized control panels, black
background and single white headlines. Cyan (#40D9FF) replaces amber;
the wordmark reads “Fly”ght Computer with “Fly”-by-Wire without a box.
The score now has one uninterrupted rhythmic grid, a smooth 112–128 BPM
buildup, overlapping harmonic voices, and shared reverb across cuts.
The results card continues the drums without a closing chord. Gentle
peak shaping and one fixed master gain avoid scene-level gain changes.
Final audio measures -22.0 LUFS, 7.2 LU range, -3.4 dBFS true peak.
All 2,250 frames decode cleanly and all 15 scene midpoint images were
reviewed. Rebuild with `scripts/edit_twitter_video_final.py`. Prior
versions remain intact.


## Recorded-instrument master (v6)

At 40–44 seconds, replaced the ambiguous crew sentence with “After the Mun
flyby, the capsule begins its return to Kerbin.” Result labels now say
“KERBALS HOME”. Kept the approved cyan layout and source timings.

Rebuilt the score with CC0 VSCO 2 CE recordings of bass drum, timpani,
snare, cello/violin and cymbal. Preserved the continuous 112–128 BPM
clock and drum-only ending. Added 24-bit PCM and lossless-ALAC exports,
320 kbps target AAC, and source-direct CRF 16 picture rendering.
Instrument provenance is also tracked in [the sample manifest](../scripts/media/v6-samples.json)
and the [CC0 notice](../licenses/VSCO2-CC0.txt).

To restore the score inputs, run `uv run python scripts/fetch_score_samples.py`.
It downloads the pinned recordings and verifies their hashes. Rebuilding the full
v6 cut with `uv run python scripts/edit_twitter_video_v6.py` additionally requires
FFmpeg, the original `.mov` recording in `video/`, and the macOS Arial fonts used
by the edit scripts. The raw recording remains local. Earlier edit scripts are
preserved as production history; v6 is the final cut.

Outputs: main MP4 32.84 MB; Discord MP4 18.29 MB with bit-identical AAC;
MOV with lossless audio 43.37 MB. Both MP4s decode all 2,250 frames.
Audio: -21.9 LUFS, -6.3 dBFS true peak, mono-compatible stereo. The MOV
audio matches the PCM master exactly. All scene midpoint images reviewed.
Scripts: edit_twitter_video_v6.py and score_mission_v6.py. All earlier
versions remain intact.
