# Roadmap to a public release

Updated 2026-09-11. This is the plan for finishing the current project, not a new
research programme. Implementation detail and flight history live in
[the handoff](handoff-2026-09-11.md); controller behaviour is in [ksp.md](ksp.md).

**The finish line:** a versioned, reproducible demonstration of three fruit-fly
connectome models providing pitch, yaw and throttle commands for a computer-guided
Mun flyby and return, with a recorded uninterrupted mission, public evidence, clear
credits and a repository another KSP owner can use.

The core demonstration already exists. Fly missions 4 and 8 flew from pad to water;
mission 8 is the existing 33-minute reference. The latest ascent changes have passed
31 tests and a 99 × 96 km orbit validation, but have not flown a complete Mun mission.
They remain uncommitted. Do not substitute the older success for validation of new code.

## 1. Close the flight work

| Order | Work | Completion evidence | Release priority |
| --- | --- | --- | --- |
| 1 | Review and commit the ascent change with its tests and handoff. Preserve the reference runs and saves. | Named commit; 31 tests pass; measured max-Q departure reduced from 13.77° to 3.01°; orbit and fuel results recorded. | Required |
| 2 | Fix the entry trim refusal and add a final corridor check. | A deliberately high return periapsis is corrected toward 40 km, including a case requiring more than the old 30 m/s cap; actual post-burn periapsis is checked. | Required |
| 3 | Exercise the low-Mun emergency correction, and correct any failure it exposes. | A recorded sub-30 km predicted periapsis triggers the emergency path and is raised above the floor before closest approach. | Required for claiming this protection works |
| 4 | Diagnose the first-pass filter with a small instrumented reproduction. | Log candidate encounter times, periods, validity and rejection reasons; either fix an identified error or retain a tested later-pass fallback. | Diagnosis required; first-pass optimization can wait |
| 5 | Freeze a release candidate and fly it from pad to touchdown while recording. | Complete run on that exact revision, all three aboard, no operator intervention, evidence saved. | Required |

**Entry work needs more than raising a number.** When the return periapsis is above
about 42 km, permit a trim above 30 m/s within available fuel and time. Add the second
look after the previous correction has actually finished. A check near 200 km must
account for the solver, alignment and burn lead: blindly adding the current node
120 seconds ahead could leave too little time before separation at 90 km. Check the
executed orbit rather than trusting the planned node. Detect a skip explicitly so it
cannot silently sit in entry until the battery runs down. Test the decision logic
offline first, then use one saved-orbit return to exercise it.

**The emergency test should be bounded.** Use the handoff's first-tick correction
driver to arrange a low flyby early, restore the normal 30 km floor on SOI entry, and
record the correction and actual flyby. Keep this driver separate from production
configuration. If it finds no safe correction, report that failure clearly; a branch
existing in the code is not evidence that it works.

**First-pass investigation has a stopping rule.** Give the original worker one
bounded diagnostic session, roughly 20–30 minutes, before deciding whether the issue
is a small fix or follow-up research. Test finite/NaN timing and identify the correct
time origin and orbital period for candidate nodes. Do not add a blind +12 m/s
prograde bias: mission 8 ended with about 1 m/s along-track remaining and 12 m/s total,
so most of that residual was lateral. If a later-pass encounter remains the practical
route, document it and validate its missing-conic/blind-coast fallback. A reliable
later pass is sufficient for the release; a stalled or silently unsafe coast is not.

**Scope boundary:** no neural learning work, new vehicle design, Mun landing, new
destinations, large parameter sweeps or general-purpose autonomous mission planner.
The ascent is now much better controlled; further efficiency tuning is optional
unless the final mission demonstrates inadequate fuel. The validated orbit retained
about 1483 m/s upper-stage vacuum delta-v, approximately 630 after a typical TMI.

## 2. Spend live runs on evidence

Aim for two planned long runs after the fixes, using shorter offline checks first:

1. A diagnostic run from a saved orbit, exercising the low-flyby correction and the
   high-return trim if both can be arranged safely in the same driver. If combining
   them obscures either result, use separate saved states rather than another launch.
2. One uninterrupted, recorded pad-to-touchdown run on the final release candidate.

Any flight-affecting change after the final run requires revalidation of the affected
behaviour. If the final mission fails, fix that specific failure and repeat; do not
start a broad tuning campaign. These two runs are a workload target, not a guarantee
that all defects will fit in two attempts.

The final run must record: revision and configuration, source/array hashes, KSP and
kRPC versions, vehicle and mod setup, event log, telemetry, summary, flyby altitude,
actual entry conditions, final crew/situation and seat fallback events. Distinguish
KSP time warp, video playback speed and wall-clock duration. Preserve the entire
recording even if only an edited clip is posted.

Publication evidence should include a compact checked-in results summary and plots,
plus a versioned downloadable archive of selected telemetry. `runs/` is ignored, so
local paths alone do not let a reader inspect the claim. Exclude the contaminated
`mun-flies-3b` run from successful-run evidence. Preserve the old reference results;
label which revision produced each run and report the validation attempts honestly.

## 3. Make the repository reproducible

This can proceed while the difficult flight issues are assigned to the original worker.
No separate tasks have been created or delegated by this roadmap.

| Deliverable | Current gap | Acceptance check |
| --- | --- | --- |
| Actual Mun vehicle | `craft/Fly By Wire.craft` is the old one-seat Kerbal 1 experiment. The flown Mun stack is in a local save. | Export/package the flown vessel or a reproducible construction procedure, including crew, staging, action groups, chutes and required mods. Test what is actually shipped. |
| Clean setup guide | Instructions mix the early one-axis experiment with the three-seat mission and assume a locally named quicksave. | A fresh checkout and fresh sandbox save reach the correct crewed pad state without guessing. Clearly separate the two experiments. |
| Code license and credits | Upstream MIT text and data attribution exist; a root project `LICENSE` does not. | Owner selects the project license; add it and metadata, retain third-party notices, verify vendored-file provenance and dataset citation. Document rather than bundle game binaries or raw connectome data. |
| Accurate README | Some language implies every control output comes from a fly; the code also has gyros, roll control, safety overrides and temporary SAS. | Explain the actual division of responsibility, identify the final reference run, show the demo first and link the detailed evidence. |
| Small automated checks | Tests exist; no CI configuration is present in the inspected tree. | Offline tests and basic package/import checks run in CI without KSP or downloading the connectome. Document a separate manual KSP smoke test. |
| Public evidence | Most flight evidence is local and ignored. | Versioned results archive, readable summary, selected plots and recording linked from the README. |
| Public readiness | Repository contents and history have not had a publication audit in this work. | Inspect tracked files, history and any workflow logs for credentials, private material, local-machine assumptions and accidental large assets; test every public-facing link. |

A fresh environment test is more valuable than extensive new packaging features.
Use the pinned dependencies and existing `prepare`/verification commands. List the
hardware and operating system actually tested; do not promise untested platforms.
Stock-only KSP would be convenient, but supporting it is not a release requirement
if the demonstrated setup requires mods: disclose and reproduce the real setup.

GitHub notes that making a repository public exposes Actions history/logs and permits
public forks, which is why the content/history review precedes the visibility change.
[GitHub visibility documentation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility).

## 4. Make it understandable and worth watching

The story is already strong: **three copies of a fruit-fly connectome, three cockpit
instruments, one rocket around the Mun and home.** Explain the split immediately:
the flight computer plans; the connectome models respond to instrument panels to
provide pitch, yaw and throttle commands; conventional augmentation and safety logic
support them. The saved vehicle's roll means vessel yaw is doing much of the ascent
pitch-over. Seat labels denote vessel control axes, not fixed compass directions.

Do not claim that a living fly flew the rocket, that the network learned orbital
mechanics, or that this is unassisted biological intelligence. Existing frozen/live
controls do not establish learning. The scientific limits and the engineering are
part of the story, not footnotes to hide.

Produce these assets:

- A 60–90 second captioned video: hook and launch; panels and neural readouts; orbit
  and TMI; recognizable Mun flyby; entry; splashdown and crew result; repository link.
- A full uncut recording linked from the repository/release, with timestamps for the
  major events. Do not use unrelated game footage as proof of the reference mission.
- One architecture image showing telemetry → guidance error → panel pixels →
  connectome → descending-neuron decoder → controls, with computer augmentation
  explicitly shown beside that path.
- A small results table and an ascent comparison plot. Use actual telemetry for
  neural activity/readouts; avoid a decorative animation that implies measured activity.

A permanent live dashboard is optional. A simple recording overlay or telemetry
replay can fulfill the README's “mission control” presentation goal with much less
work. If deferred, mark the dashboard as future work rather than an unfinished
requirement for the demonstrated mission.

A short captioned cut also works without a Premium account: X currently documents
up to 140 seconds and 512 MB for non-Premium video uploads.
[X video documentation](https://help.x.com/en/using-x/x-videos).

Suggested lead post, to finalize against the recorded release:

> I gave three fruit-fly connectome models a rocket. They flew it around the Mun and
> home. 🪰🚀
>
> A flight computer plans the burns; the models read cockpit panels and provide pitch,
> yaw and throttle commands, with control augmentation.
>
> Code + flight evidence: [repo link]

Follow with three short replies: how the panels/brains/decoder work; what the tests
show and do not show; the credits and reproduction instructions. Use the final
recording's numbers. Give the upstream backend and connectome dataset visible credit.
The opening post should be checked for the posting account's character limit after
the real link and final copy are inserted.

## 5. Release, then stop

1. Finish the flight gates and freeze the recorded revision. Commit the release
   documentation/evidence with an explicit pointer to that flight revision.
2. Review the exact public repository, license, evidence archive, video and post copy
   together. Get the owner's final go-ahead for the visibility change and posting.
3. Make the repository public; verify unauthenticated access and the README links.
4. Publish a versioned release (proposed name: `v0.1.0`) containing reproduction notes,
   known limitations and selected evidence. Confirm the release assets are accessible.
5. Post the demo and thread with the verified repository link. Pin/link the demo as
   desired, and fix concrete setup errors reported by early readers.

This request creates the roadmap only; it does not change visibility, create a
release or publish a social post. The launch is complete when the public evidence
matches the claims and a reader can reproduce the supported setup. First-pass
optimization, a richer dashboard and learning experiments become explicitly optional
follow-ups.

**Recommended next assignment:** entry trim + final check, followed by the bounded
emergency/first-pass diagnostics. The original worker is best placed for those
flight-dynamics problems. Repository preparation and the video/story can be handled
separately without spending more connectome flight runs. Keep one flight computer in
control of KSP at a time; never stop a process during warp or operator-warp while a
solver is active.
