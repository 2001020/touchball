# Chart plan: Pixel Peeker Polka (cut)

Target difficulty: IN Lv.11
BPM 145.0, offset -782 ms, 22 bars (88 beats, ~36 s). Grid verified at step 2: test taps on 4,8,9,10,11.5,12,13,14,16 -> 100 % sync, downbeats are real accents.

## 1. Sections
| section | bars | beats | character | layer(s) to follow | density target (nps) | flow speed | line motion |
|---|---|---|---|---|---|---|---|
| Intro | 0-1 | 0-8 | pickup (2-3.5) + big hit on 4 + snare 16th fill on 5 | melody pickup, snare fill | ~2 | 5.6 (T≈1.07 s), ramp to 6.3 over 6-8 | alpha fade-in 0-1.5 |
| A (theme) | 2-9 | 8-40 | bright polka theme, melody hits on quarters, 2-bar phrases | melody (+ snare offbeats in melody gaps) | ~3 | 6.3 (T≈0.95 s) | static |
| B (drum groove) | 10-15 | 40-64 | melody drops back, oom-pah drums carry; accent on x+3.5 every 2 bars | kick (beats) + snare (offbeats) | ~3.8 | 6.3 | static |
| C (climax) | 16-20 | 64-84 | densest; energy peaks bars 17/19 | kick+snare skeleton + 16th pickups | ~4.8 | ramp 6.3->7.0 over 60-64 (T≈0.86 s) | static (y-lift idea dropped: readability first, speed-up already marks the climax) |
| Outro | 21 | 84-88 | decay | kick hits | sparse | 7.0 | alpha fade-out after last note |

## 2. Sampling decisions
- Hat layer is never charted (constant 8ths of after-beat chords). Weak snare ghost 16ths (strength <=4) ignored except in fills.
- A: follow melody rhythm (quarters + "4&" pickups); fill melody rests (beats 15, 21, 23, 29, 31) with strong snare (>=8) so the pulse never dies.
- B: kick on each beat = left hand zone, snare offbeats = right hand zone (fixed mapping for the section). Strong melody stab at 43.5 / 51.5 / 59.5 -> flick.
- C: alternating 8th stream, 16th pairs where the kick/snare show x.75 pickups (66.75, 74.75, 82.75), flicks on 67.5 / 75.5 / 83.5 (melody stab).
- Drags only for the 16th snare fills (5-5.75, 62.5-62.75, 82.5-82.75).
- Doubles: section/phrase starts with crash: 4, 8, 24, 40, 64, 72, 76, 84 (~6-8 %).
- No holds in the body: the analysis found 0 sustained notes (staccato polka). One ending hold on the final ring-out.

## 3. Motifs
- A "theme" motif: 1-2-3 quarters walking outward (L->R stairs), "4&" pickup on the far side; phrase 3 = mirror of phrase 1.
- B "oom-pah": left-zone kick taps on beats, right-zone snare offbeats; flick on the 2-bar stab.
- Fills into section starts = 4-note stairs left->right ending into a symmetric double.

## 4. Progress log
- Grid check: 9 test taps, timeline 0-24 -> all on onsets, sync 100 %. Test notes removed.
- Intro + A (0-40): written, timeline 0-40 + snaps around 5 and 38 OK (drag fill reads as clean diagonal). Then added snare taps 11/19/27/35 to lift A density; snap 27 --compare @prev OK.
- B + C + outro (40-88): written, timeline 40-88 all on onsets; flicks on the 2-bar stabs 43.5/51.5/59.5/67.5/75.5/83.5 (+31.5 in A).
- Hold note: the planned ending hold was dropped (the final bar decays with discrete kicks, no sustained tone). Final double on 86 instead.
- Speed/alpha events: 5.6 -> 6.3 (6-8), 6.3 -> 7.0 (60-64), alpha fade-in 0-1.5, fade-out 87-88.5. Snaps around 7, 62, 82 and 0/1/2/85/86/87.5 OK.
- C density ≈ B density because the audio itself is not busier there (energy 0.6-0.84 vs 0.5-0.65); the climax gets more doubles (64/72/76/84) and the faster flow instead of extra filler.
- lint: 0 errors, 0 warnings, sync 144/144.
