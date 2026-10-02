# import os # get access to computer
import sys # get instructions from terminal
from pathlib import Path # calls specific paths
import soundfile as sf
import pyloudnorm as pyln
import numpy as np
from scipy.signal import resample_poly
from datetime import datetime
import importlib.metadata
import math

SUPPORTED_FORMATS = {".wav", ".aif", ".aiff"}

def convert_seconds_to_mm_ss(seconds: int) -> str:
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"

def read_metadata(path):
    info = sf.info(path)
    sample_rate = info.samplerate
    channels = info.channels
    bit_depth = info.subtype
    duration = round(info.duration)
    file_format = info.format
    return sample_rate, channels, bit_depth, duration, file_format

def measure(path):
    sr, ch, subtype, dur, fo = read_metadata(path)
    if ch != 2: # skips if less than 2 channels aka mono, bounces can only be stereo files
        return None, "mono — this tool measures stereo bounces"
    if dur <= 1: # skips if less than 1s long aka too short
        return None, "shorter than 1s"
    data, rate = sf.read(path)
    sample_peak, true_peak = peaks(data)
    if not math.isfinite(sample_peak):
        return None, "File has no audio in it"
    lufs, lra = how_loud(data, rate)
    result = {
        "name": path.name,
        "sample_rate": sr,
        "channels": ch,
        "subtype": subtype,
        "duration": dur,
        "format": fo,
        "lufs": lufs,
        "lra": lra,
        "sample_peak": sample_peak,
        "true_peak": true_peak,
    }
    return result, None

def how_loud(data, rate):
    meter = pyln.Meter(rate)
    lufs = meter.integrated_loudness(data)
    lra = meter.loudness_range(data)
    return lufs, lra

def to_db(linear):
    return 20 * np.log10(linear)

def peaks(data):
    sample_peak = np.abs(data).max()
    upsampled   = resample_poly(data, 8, 1)
    true_peak   = np.abs(upsampled).max()
    return to_db(sample_peak), to_db(true_peak)

# this function will create the file with the report, using all the processed data
def write_report(path, measured, skipped):
    tool = importlib.metadata.version("pyloudnorm")
    now = datetime.now()
    report_format = now.strftime("%d-%m-%y %H:%M:%S")
    filedate_format = now.strftime("%d-%m-%y_%H%M%S")
    folder_name = path / "batch loudness report"
    with open(f"{folder_name} {filedate_format}.txt", "w") as file:
        file.write(f"""
LOUDNESS REPORT
Generated:   {report_format}
Source:      {path}
Tool:        Pyloudnorm {tool}, Hendrick Valera

{'TRACK':<32}{'DUR':>7}{'LUFS-I':>9}{'TP dBTP':>10}{'SP':>5}{'LRA':>10}{'SR/BD':>10}{'Channels':>10}
                """)
        for item in sorted(measured, key=lambda item: item["name"]):
            sr_bits = f"{item['sample_rate']}/{item['subtype']}"
            real_time = f"{convert_seconds_to_mm_ss(item['duration'])}"
            file.write(f"""
{item['name']:<32.32}{real_time:>8}{item['lufs']:>8.2f}{item['true_peak']:8.2f}{item['sample_peak']:8.2f}{item['lra']:8.2f}{sr_bits:>14}{item['channels']:>4}""")

        loudest = max(measured, key=lambda item: item["lufs"])
        quietest = min(measured, key=lambda item: item["lufs"])
        file.write(f"""\n
ALBUM\n
{loudest['name']:<32.32}{loudest['lufs']:>8.2f} Loudest Track\n{quietest['name']:<32.32}{quietest['lufs']:>8.2f} Quietest Track""")
        
        if skipped:
            file.write("""\n
SKIPPED/ERRORS:\n""")
            for name, reason in sorted(skipped):
                file.write(f"""
  -{name}\nReason: {reason}""")
        file.write(f"""\n
SUMMARY:

Songs measured: {len(measured)}
Items skipped: {len(skipped)}""")

def main():

    if len(sys.argv) < 2:
        sys.exit("I need a folder name or a list of files")

    f_name = Path(sys.argv[1])

    if not f_name.exists():
        sys.exit(f"can't find {f_name}")

    if f_name.is_dir():
        candidates = sorted(f_name.iterdir())
        report_folder = f_name
    else:
        candidates = [Path(arg) for arg in sys.argv[1:]]
        report_folder = Path.cwd()

    measured = []
    skipped = []
    song_counter = 0

    # will remove hidden files and non supported formats
    for song in candidates:
        filename = song.name
        extension = song.suffix
        try:
            if filename.startswith("."):
                continue
            elif extension.lower() not in SUPPORTED_FORMATS:
                print(f"{filename} not a WAV or AIFF file")
                skipped.append((filename, "not a WAV or AIFF file"))
                continue
            result, reason = measure(song)
            if reason:
                print(f"{filename} not counted, check summary after results")
                skipped.append((filename, reason))
            elif result:
                song_counter += 1
                print(f"track number {song_counter} measured")
                measured.append(result)
        except sf.LibsndfileError as e:
            skipped.append((filename, str(e)))
            continue

    # will print the files
    if measured:
        print("PROCESSED SONGS:")
        for item in sorted(measured, key=lambda item: item["name"]):
            sr = item["sample_rate"]
            ch = item["channels"]
            subtype = item["subtype"]
            dur = item["duration"]
            fo = item["format"]
            loudness = item["lufs"]
            lra = item["lra"]
            sample_peak = item["sample_peak"]
            true_peak = item["true_peak"]
            print(item["name"])
            print(f"-Sample rate: {sr}\n-Channels: {ch}\n-Bit depth: {subtype}\n-Duration: {convert_seconds_to_mm_ss(dur)}\n-Format: {fo}")
            print(f"-Loudness: {loudness:.2f} LUFS Integrated BS.1770 loudness")
            print(f"-Loudness Range: {lra:.2f}\n-Sample peak: {sample_peak:.2f}\n-True peak: {true_peak:.2f}\n")
    else:
        sys.exit("No measurable file(s)")

    if skipped:
        print("\nNOT PROCESSED:")
        for name, reason in sorted(skipped):
            print(f"-{name}\nReason: {reason}")

    print(f"\nSUMMARY:\nSongs measured: {len(measured)} \nItems skipped: {len(skipped)}")

    write_report(report_folder, measured, skipped)

if __name__ == "__main__":
    main()
