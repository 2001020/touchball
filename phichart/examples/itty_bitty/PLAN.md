# Chart plan: Itty Bitty 8 Bit (cut)

Target difficulty: IN Lv.11
BPM 109.0, offset -1050 ms, 45 bars (bar 0 = lead-in, music starts ~beat 1.9). Grid verified in step 2
(test taps on strong kicks/snares sat on onsets, sync 100%).

Music: chiptune, very busy (hat 8ths everywhere, 16th arps). Groove = syncopated kick/bass on
x.0 / x.75 / x.5 + snare/lead on beats. Lead has a few long notes (14+1/4, 28+1/4, 30+1/4, 74+1/4, 78+1/3).
Bars 32-40 are "stab" bars: all layers hit together on 8ths -> loudest accents of the clip (true climax
even though RMS is lower). Ending 41-44 thins out, final hit at 177.

## 1. Sections
| section | beats | character | layer(s) to follow | density (notes/bar) | speed v (lineY -270) | line motion |
|---|---|---|---|---|---|---|
| intro | 0-4 | pickup into song | strongest 4 hits | 4 | 6.3 (T 0.95 s) | alpha fade-in 0->255 over beats 0-2 |
| A verse | 4-32 | groove | kick/bass (left) + snare/lead (right) | 8 | 6.3 | static |
| B | 32-64 | kick-led variation | kick syncopation, snare on beats | 8 (+drag pairs) | 6.8 (T 0.88) | static |
| C verse 2 | 64-128 | groove, stronger | as A, add 16th pairs on strongest | 8-10 | 6.8 | static |
| D stabs | 128-164 | climax | all-layer stabs on 8ths | 9-10, doubles on biggest stabs | 7.3 (T 0.82) | lift to y -240 over 2 beats at 128 (outQuad) |
| end | 164-178 | thinning, final hit | only stabs with score >= 3 | 3-5 | 6.0 | back to -270 at 164, fade out after 177 |

## 2. Sampling decisions
- NOT charted: hat 8ths (constant, no information), most 16th arpeggio onsets (only strongest pairs as drags).
- A/C mapping: positions where K/B dominate -> left hand zone (x -380..-120); S/M/H dominated -> right zone (120..380).
  Gives natural hand alternation. Doubles only at phrase starts (every 4 bars: beats 4, 20, 36, 52, 68, 84, 100, 116).
- Holds on the lead's long notes: 14+1/4->15, 28+1/4->29+1/2, 30+1/4->31+1/4, 74+1/4->75+1/4, 78+1/3->79+1/2 (hold on
  one side, other notes on the other side).
- B: snare beats as taps, kick syncopations as taps, weaker 16th pickups as drags leading into the next tap.
- D: 8th stabs alternate L/R stairs; biggest stabs (score >= 3.8) doubled; flick on the last stab of each 4-bar phrase.

## 3. Motifs
- "groove cell" (A/C): K(left) . . K(left) S(right) | ... repeats every bar, mirrored every 2nd phrase.
- "stab stairs" (D): -360,-120,120,360 rising stairs, mirrored next bar.

## 4. Progress log
- [x] intro + A (0-32): 64 notes, sync 100%. Reviewed timeline 0-32 + snap around 14+1/4 (hold + right-hand taps): readable,
      max ~5 notes on screen, no overlaps. Lint clean.
- [x] B (32-64): first version mirrored A too closely -> remapped to edge/center inward-outward motif with strict hand
      alternation; compared with `snap --compare @prev` around 41.
- [x] C (64-128): A-motif returns (verse repeat), holds on lead long notes 74+1/4 and 78+1/3 (triplet) reviewed with snap.
- [x] D (128-164) stab stairs + doubles every 2 bars, ending 164-178. Found & fixed: 129+1/4 stab had become a drag
      -> tap at -360, re-alternated hands (compare snap around 129+1/4).
- [x] events: alpha fade-in 0-2, fade-out after 177; speed 6.3 -> 6.8 (32) -> 7.3 (128) -> 6.0 (164); line lift -270->-240 at
      128-130 and back at 164. Snapped all transitions. Lead times 0.80-1.00 s.
- [x] final lint: 0 errors, 0 warnings, sync 100%. Density avg 3.4 nps / peak 6 -> labelled HD Lv.9 (not IN as planned).
