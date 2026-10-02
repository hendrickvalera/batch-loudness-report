# BLR — Batch Loudness Report

Measures audio files and writes a loudness report, so I don't have to open tracks one at a time in RX.

Per file: integrated LUFS, loudness range, sample peak, and true peak.

## Requirements

- Python 3.14
- `soundfile`, `pyloudnorm`, `numpy`, `scipy`

```
pip install -r requirements.txt
```

Those four are the direct dependencies — the ones I chose. `requirements.txt` has seven entries because it's a `pip freeze` dump, which also pins the **transitive** dependencies: `cffi` and `pycparser` (soundfile is a wrapper around the C library libsndfile and calls into it through cffi, which needs pycparser to parse C headers) and `typing_extensions`. Nothing installs them by hand; pip pulls them in. Pinning them too means a rebuild in six months gets byte-identical versions rather than whatever is current.

Use `pip show <package>` to trace any of them — the `Requires:` and `Required-by:` lines show who depends on what.

Standard-library modules (`sys`, `pathlib`, `datetime`, `math`, `importlib`) ship with Python and never appear in requirements.

No ffmpeg. Everything is measured in Python.

(`soundfile` rather than the stdlib `wave`/`aifc` because `aifc` was removed from Python 3.13 by PEP 594.)

## Usage

Two ways to point it at audio.

**A whole folder:**

```
python BLR.py "/path/to/album folder"
```

**A list of files**, which in practice means letting the shell expand a glob:

```
python BLR.py ~/album/*.wav
python BLR.py ~/album/0[1-3]*.wav
python BLR.py ~/album/v1/track.wav ~/album/v2/track.wav
```

The shell expands the pattern before Python ever runs, so the program just receives a list of paths. The last example is the useful one — an old master and a new one side by side in the same report.

Reads `.wav`, `.aif` and `.aiff`; everything else is listed as skipped.

### Mixing the two doesn't work

```
python BLR.py album extra.wav      # extra.wav is ignored
```

The first argument decides the mode. If it's a directory, the folder is scanned and **every other argument is dropped silently**. If it's a file, all the arguments are treated as the file list. Pick one style per run.

## Output

Two things:

1. A summary in the terminal, printed as each track finishes.
2. A text report named `batch loudness report DD-MM-YY_HHMMSS.txt`.

Where the report lands depends on the mode:

- **Folder mode** — inside the album folder.
- **File-list mode** — in the current working directory, since there's no single folder the files belong to.

The timestamp means every run creates a new file — nothing is ever overwritten, so old reports stay around for comparison. They will accumulate; delete them yourself.

The report contains a header (when it was generated, source, tool versions), one row per track, a loudest/quietest summary, a list of everything that was skipped and why, and counts.

## What gets skipped

| Case | Why |
|---|---|
| Dotfiles | `.DS_Store` and friends, silently |
| Not WAV/AIFF | listed in the report |
| Mono | mono and stereo LUFS aren't comparable, and bounces are stereo |
| Shorter than 1s | not enough signal for a meaningful integrated reading |
| Digital silence | peak is `-inf` and LRA is `nan`; reported as no audio |
| Unreadable / corrupt | libsndfile's own error is recorded; the run continues |

A bad file never stops the run.

## How the measurements are made

**Integrated LUFS and LRA** come from `pyloudnorm` (BS.1770-4).

**Sample peak** is the maximum absolute sample value, in dBFS.

**True peak** is measured by oversampling 8× with `scipy.signal.resample_poly`, taking the maximum absolute value of the result, and converting to dB. This is my own code, not a library helper — several loudness libraries expose a "peak" function that is sample-peak normalisation, and labelling that as dBTP would put a wrong number in a mastering report.

Peaks are reported as the worse of the two channels.

### Why 8× and not 4×

4× is the BS.1770-4 minimum and what ffmpeg uses. On my material it under-reads true peak by up to 0.17 dB. 8× and 16× agree to four decimal places on every track tested, so 8× is enough and 16× is wasted work.

### Validation against RX

Three mastered tracks measured by hand in iZotope RX first, then with this tool.

Integrated LUFS — target was within 0.2 LU:

| Track | RX | BLR.py |
|---|---|---|
| 2. ufffff.wav | −6.5 | −6.55 |
| 3. Oldbets_3.wav | −8.0 | −8.00 |
| 4. what really happened was.wav | −7.9 | −7.98 |

True peak — target was within 0.3 dB:

| Track | RX | BLR.py |
|---|---|---|
| 2. ufffff.wav | −0.27 | −0.31 |
| 3. Oldbets_3.wav | −0.41 | −0.45 |
| 4. what really happened was.wav | −0.21 | −0.38 |

LRA is informational — there is no agreed tolerance. RX reads roughly 0.4–0.7 LU higher than pyloudnorm, ffmpeg `ebur128` and ffmpeg `loudnorm`, which all agree with each other.

## Things that look like bugs and aren't

**Sample peak changes with sample rate.** The 44.1k/16 bounce of a track reads −0.40 where the 48k versions read −0.50. True peak, LUFS and LRA are unchanged. Sample-rate conversion moves where the samples land relative to the waveform, so the sample peak legitimately differs. Don't "fix" this.

## Known limitations

- **Truncated files are not detected.** libsndfile clamps the header's frame count to the data actually present, so a 3:06 file cut short at 2:00 reports a healthy 2:00 and measures cleanly. Catching it would mean parsing RIFF chunk headers by hand — out of scope.
- **A folder and files can't be mixed** in one command; see above.
- **Duration is rounded to whole seconds**, so the "under 400 ms" case can't be expressed yet.
- **Two files with the same name** from different folders produce two rows with the same label, since only the filename is stored, not the full path.
- **No delivery targets.** This is a measurement sheet, not a compliance checker — platform numbers are arbitrary and change constantly. Every row shows its own numbers; judgement is mine.

## Speed

Roughly 3.4 seconds per 3-minute track, dominated by the 8× upsample. About 3 minutes for a 50-track album.