# Audio analysis summary

- duration: 97.00 s
- BPM: 109.0  (beat = 0.5505 s; verify by rendering - if notes feel doubled/halved, re-run `phichart analyze --bpm X`)
- offset: -1050 ms  (music time of beat 0 = META.offset; beat 0 is one bar BEFORE the first detected downbeat, giving a lead-in bar. Negative = before the audio starts)
- meter: 4/4, total beats: 178, bars: 45

## Sections (auto-detected - refine them in your plan)

| id | label | role hint | bars | beats | time | energy | onsets/bar |
|---|---|---|---|---|---|---|---|
| 0 | A | main (verse) | 0-7 | 0-32 | -1.1-16.6s | 0.72 | 11.6 |
| 1 | B | climax (chorus/drop) | 8-15 | 32-64 | 16.6-34.2s | 0.74 | 8.0 |
| 2 | C | main (verse) | 16-31 | 64-128 | 34.2-69.4s | 0.74 | 10.1 |
| 3 | D | outro | 32-44 | 128-178 | 69.4-96.9s | 0.58 | 8.8 |

## Layer onset counts (peak-picked, strength>=0.3)

- kick: 352 onsets (14 on triplet grid) - low percussive (<150 Hz): kick drum / low hits
- snare: 483 onsets (27 on triplet grid) - mid percussive (150-4k Hz): snare, claps, toms, percussive attacks
- hat: 563 onsets (73 on triplet grid) - high percussive (>5 kHz): hi-hats, cymbals, shakers
- melody: 390 onsets (29 on triplet grid) - harmonic 250-4k Hz note starts: lead / vocal / chords
- bass: 352 onsets (22 on triplet grid) - harmonic 40-250 Hz note starts: bass line
- all: 484 onsets (13 on triplet grid) - all layers combined
- sustained melody notes (>=1 beat, hold candidates): 3

## Energy per bar (0-1)

```
bars   0- 15: 0.67 0.74 0.72 0.73 0.70 0.73 0.73 0.74 0.69 0.75 0.74 0.75 0.71 0.76 0.76 0.76
bars  16- 31: 0.71 0.74 0.73 0.73 0.69 0.75 0.74 0.75 0.70 0.75 0.75 0.74 0.71 0.76 0.75 0.77
bars  32- 44: 0.68 0.59 0.73 0.58 0.58 0.57 0.63 0.56 0.58 0.54 0.72 0.63 0.15
```

Files: bars.txt (per-bar onset sheet), overview.png (spectrogram/energy/sections), analysis.json.
