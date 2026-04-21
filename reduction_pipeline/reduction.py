#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FAST Spectrograph Data Reduction Pipeline
FLWO 1.5m / FAST spectrograph

Usage:
    python reduction.py <night>                           e.g.  python reduction.py 2026.0318
    python reduction.py <night> -f                        force rerun (cleans reduced/ and ascii/ first)
    python reduction.py <night> --std feige34             pre-select standard star
    python reduction.py <night> --redo 2026fvx            delete and redo one target
    python reduction.py <night> --redo 2026fvx --interactive
                                                         redo one target with interactive apall
    python reduction.py <night> --no-apall-clean          disable apall cleaning for science/std extraction
    python reduction.py <night> --no-cr-clean             disable 2D LACosmic cleaning for science frames
Environment:
    FAST_CR_PYTHON=/path/to/python        optional override for clean_cr.py interpreter
Default FAST_CR_PYTHON:
    current interpreter (sys.executable)

Pipeline steps:
  1. Master bias (zerocombine)
  2. Master dark (darkcombine)
  3. CCD processing: overscan, trim, bias/dark subtract (ccdproc)
  4. Flat processing:
     4a. Master flat (flatcombine)
     4b. Flat response / normalization (response)
     4c. Apply flat field (ccdproc)
     4d. Cosmic ray cleaning for science frames (clean_cr.py / astroscrappy)
  5. Aperture extraction (apall)
  6. Wavelength calibration (identify / reidentify / dispcor)
  7. Flux calibration (standard / sensfunc / calibrate)
  8. Stack spectra by target
  9. Export stacked spectra to ASCII
 10. Plot stacked spectra to PDF
 11. Copy stacked spectra to final/
"""

import os
import sys
import glob
import shutil
import numpy as np

# ── Resolve all paths BEFORE importing pyraf (it changes the CWD on init) ────
FAST_DIR = os.path.abspath(os.path.dirname(__file__) or ".")

_args = [a for a in sys.argv[1:] if not a.startswith("-")]
FORCE = "-f" in sys.argv
INTERACTIVE = "--interactive" in sys.argv  # apall interactive mode
AP_INTERACTIVE = "yes" if INTERACTIVE else "no"
AP_CLEAN = "no" if "--no-apall-clean" in sys.argv else "yes"
RUN_CR_CLEAN = "--no-cr-clean" not in sys.argv

# --std <name>: pre-select standard star (iraf name, e.g. feige34)
STD_OVERRIDE = None
# --redo <target>: delete and redo all intermediate files for one object
REDO_TARGET = None
for _i, _a in enumerate(sys.argv[1:]):
    if _a == "--std" and _i + 2 < len(sys.argv):
        STD_OVERRIDE = sys.argv[_i + 2].lower()
    if _a == "--redo" and _i + 2 < len(sys.argv):
        REDO_TARGET = sys.argv[_i + 2]

if INTERACTIVE and not REDO_TARGET:
    raise SystemExit(
        "--interactive requires --redo <target>.\n"
        "Example: python reduction.py 2026.0318 --redo NGC3526 --interactive"
    )

if not _args:
    raise SystemExit(
        "Usage: python reduction.py <night> [-f] [--std <name>] [--redo <target>] [--interactive] [--no-apall-clean] [--no-cr-clean]\n"
        "  --redo <target>       delete and reprocess all files matching <target> (e.g. 2026fvx)\n"
        "  --redo <target> --interactive   same, but run apall interactively for that target\n"
        "  --no-apall-clean      disable apall profile cleaning during extraction\n"
        "  --no-cr-clean         disable 2D LACosmic cleaning for science frames"
    )
NIGHT_DIR = os.path.join(FAST_DIR, _args[0])
if not os.path.isdir(NIGHT_DIR):
    raise SystemExit("Night directory not found: " + NIGHT_DIR)

# Keep SCRIPT_DIR pointing at the night so all downstream code is unchanged
SCRIPT_DIR = NIGHT_DIR
RAW_DIR = os.path.join(NIGHT_DIR, "raw")
WORK_DIR = os.path.join(NIGHT_DIR, "reduced")
ASCII_DIR = os.path.join(NIGHT_DIR, "ascii")
FINAL_DIR = os.path.join(NIGHT_DIR, "final")
DEBUG_DIR = os.path.join(WORK_DIR, "debug")
DB_DIR = os.path.join(WORK_DIR, "database")


def _remove_matching(paths):
    for _f in sorted(paths):
        if os.path.exists(_f):
            os.remove(_f)
            print("  Removed: " + _f)


def _redo_cleanup(target, interactive=False):
    if interactive:
        # Keep the processed 2D frame, but remove all extraction products.
        _suffixes = (".0001.fits", ".w.0001.fits", ".wf.0001.fits", ".stack.fits")
        _matches = [
            _f
            for _f in glob.glob(os.path.join(WORK_DIR, "*" + target + "*"))
            if any(_f.endswith(_s) for _s in _suffixes)
        ]
        _remove_matching(_matches)
    else:
        _matches = glob.glob(os.path.join(WORK_DIR, "*" + target + "*"))
        _remove_matching(_matches)

    _remove_matching(glob.glob(os.path.join(ASCII_DIR, "*" + target + "*")))
    _remove_matching(glob.glob(os.path.join(FINAL_DIR, "*" + target + "*")))
    _remove_matching(glob.glob(os.path.join(DEBUG_DIR, "*" + target + "*")))
    # Delete target aperture DB entries so apall does not silently reuse or
    # append stale apertures for the same science target.
    _remove_matching(glob.glob(os.path.join(DB_DIR, "ap*" + target + "*")))


if REDO_TARGET:
    if INTERACTIVE:
        print(
            "Redo mode (interactive): removing extraction outputs for '%s' ..."
            % REDO_TARGET
        )
        _redo_cleanup(REDO_TARGET, interactive=True)
    else:
        print("Redo mode: removing all intermediate files for '%s' ..." % REDO_TARGET)
        _redo_cleanup(REDO_TARGET, interactive=False)
    print("")


if FORCE:
    print("Force mode: cleaning reduced/ and ascii/ ...")
    for _d in [WORK_DIR, ASCII_DIR]:
        if os.path.exists(_d):
            shutil.rmtree(_d)
            print("  Removed: " + _d)
    print("")

if not os.path.exists(WORK_DIR):
    os.makedirs(WORK_DIR)
    print("Created: " + WORK_DIR)


def raw(pattern):
    return sorted(glob.glob(os.path.join(RAW_DIR, pattern)))


def work(basename):
    """Return an absolute path inside WORK_DIR."""
    return os.path.join(WORK_DIR, basename)


def target_name_from_path(path):
    _parts = os.path.basename(path).split(".")
    return _parts[1] if len(_parts) > 2 else ""


def is_redo_target_path(path):
    return (not REDO_TARGET) or (REDO_TARGET in target_name_from_path(path))


def iraf_list(files, tag="list"):
    """Write absolute paths to a named @list file and return '@filename'."""
    listfile = work("_" + tag + ".txt")
    with open(listfile, "w") as fh:
        fh.write("\n".join(files) + "\n")
    return "@" + listfile


bias_raw = raw("*.BIAS.fits")
dark_raw = raw("*.DARK.fits")
flat_raw = raw("*.FLAT.fits")
comp_raw = raw("*.COMP.fits")
# Known FAST standard stars: filename fragment -> IRAF star_name
KNOWN_STDS = {
    "Hiltner600": "hiltner600",
    "hiltner600": "hiltner600",
    "G191B2B": "g191b2b",
    "g191b2b": "g191b2b",
    "Feige110": "feige110",
    "feige110": "feige110",
    "Feige34": "feige34",
    "feige34": "feige34",
    "BDp284211": "bd284211",
    "BD284211": "bd284211",
    "BDp262606": "bd262606",
    "BDp332642": "bd332642",
    "Feige66": "feige66",
    "feige66": "feige66",
    "HZ44": "hz44",
    "HD84937": "hd84937",
    "hd84937": "hd84937",
}
# IRAF caldir for iraf.standard() -- different stars live in different directories
STD_CALDIR = {
    "hiltner600": "onedstds$spechayescal/",
    "g191b2b": "onedstds$spechayescal/",
    "feige110": "onedstds$spechayescal/",
    "feige34": "onedstds$spechayescal/",
    "feige66": "onedstds$spechayescal/",
    "hz44": "onedstds$spechayescal/",
    "bd284211": "onedstds$spechayescal/",
    "bd262606": "onedstds$irscal/",
    "bd332642": "onedstds$irscal/",
    "hd84937": "onedstds$irscal/",
}
std_raw = []
std_name = None
_found_stds = []
for _frag, _name in KNOWN_STDS.items():
    _matches = raw("*." + _frag + ".fits")
    if _matches:
        _found_stds.append((_frag, _name, _matches))

if not _found_stds:
    raise SystemExit("No standard star frames found in " + RAW_DIR)
elif len(_found_stds) == 1:
    _, std_name, std_raw = _found_stds[0]
    print("Standard star: " + std_name)
else:
    # Deduplicate by iraf name (multiple filename fragments may match the same star)
    _seen = {}
    for _frag, _name, _matches in _found_stds:
        if _name not in _seen:
            _seen[_name] = (_frag, _matches)
    _unique = list(_seen.items())  # [(iraf_name, (frag, matches)), ...]
    print("Multiple standard stars found:")
    for i, (_name, (_frag, _matches)) in enumerate(_unique):
        print("  [%d] %s (%d frame(s))" % (i, _name, len(_matches)))
    if STD_OVERRIDE:
        _match = [x for x in _unique if x[0] == STD_OVERRIDE]
        if not _match:
            raise SystemExit(
                "--std '%s' not found. Available: %s"
                % (STD_OVERRIDE, [x[0] for x in _unique])
            )
        std_name, (_frag, std_raw) = _match[0]
    else:
        while True:
            _choice = raw_input(
                "Select standard to use [0-%d]: " % (len(_unique) - 1)
            ).strip()
            if _choice.isdigit() and 0 <= int(_choice) < len(_unique):
                std_name, (_frag, std_raw) = _unique[int(_choice)]
                break
            print("  Invalid choice, try again.")
    print("Using: " + std_name)
# Auto-detect science frames: any OBJECT frame that is not a standard star
_non_sci = set(bias_raw + dark_raw + flat_raw + comp_raw + std_raw)
sci_raw = [
    f
    for f in sorted(glob.glob(os.path.join(RAW_DIR, "*.fits")))
    if f not in _non_sci and "fastlog" not in f
]
selected_sci_raw = [f for f in sci_raw if is_redo_target_path(f)]

print(
    "Found %d bias, %d dark, %d flat, %d comp, %d std, %d sci frames"
    % (
        len(bias_raw),
        len(dark_raw),
        len(flat_raw),
        len(comp_raw),
        len(std_raw),
        len(sci_raw),
    )
)
if REDO_TARGET:
    print(
        "Redo target selection: %d science frame(s) match '%s'"
        % (len(selected_sci_raw), REDO_TARGET)
    )

# ── Load IRAF packages (changes CWD -- all paths already resolved above) ─────
from pyraf import iraf

iraf.noao(_doprint=0)
iraf.imred(_doprint=0)
iraf.ccdred(_doprint=0)
iraf.images(_doprint=0)
iraf.imutil(_doprint=0)
iraf.twodspec(_doprint=0)
iraf.longslit(_doprint=0)
iraf.apextract(_doprint=0)
iraf.onedspec(_doprint=0)

iraf.ccdred.instrument = ""
iraf.ccdred.verbose = "no"

# ── CCD parameters (from FITS headers) ───────────────────────────────────────
GAIN = 0.8  # e-/ADU  (used by imcombine)
RDNOISE = 4.4  # e-      (used by imcombine)
BIASSEC = "[2:30,1:161]"
TRIMSEC = "[35:2715,1:161]"

# =============================================================================
# STEP 1: Master Bias
# =============================================================================
print("\n=== Step 1: Master Bias ===")
master_bias = work("master_bias.fits")

if not os.path.exists(master_bias):
    iraf.imcombine(
        input=iraf_list(bias_raw, "bias"),
        output=master_bias,
        combine="average",
        reject="minmax",
        rdnoise=RDNOISE,
        gain=GAIN,
    )
    print("  Created: " + master_bias)
else:
    print("  Exists, skipping: " + master_bias)

# =============================================================================
# STEP 2: Master Dark
# =============================================================================
print("\n=== Step 2: Master Dark ===")
master_dark = work("master_dark.fits")

if not os.path.exists(master_dark):
    iraf.imcombine(
        input=iraf_list(dark_raw, "dark"),
        output=master_dark,
        combine="average",
        reject="minmax",
        scale="exposure",
        rdnoise=RDNOISE,
        gain=GAIN,
    )
    print("  Created: " + master_dark)
else:
    print("  Exists, skipping: " + master_dark)

# =============================================================================
# STEP 3: CCD Processing -- overscan, trim, bias & dark subtract
#         Applied to: flats, comps, standard, science frames
# =============================================================================
print("\n=== Step 3: CCD Processing ===")
to_process = (
    flat_raw + comp_raw + std_raw + (selected_sci_raw if REDO_TARGET else sci_raw)
)

for raw_file in to_process:
    out = work(os.path.basename(raw_file))
    if not os.path.exists(out):
        iraf.ccdproc(
            images=raw_file,
            output=out,
            ccdtype="",
            fixpix="no",
            overscan="yes",
            trim="yes",
            zerocor="yes",
            darkcor="yes",
            flatcor="no",
            biassec=BIASSEC,
            trimsec=TRIMSEC,
            zero=master_bias,
            dark=master_dark,
            interactive="no",
        )
        print("  Processed: " + os.path.basename(raw_file))

# --- Debug snapshot after Step 3 ---
_debug_dir = work("debug")
if not os.path.exists(_debug_dir):
    os.makedirs(_debug_dir)
_shutil = shutil

for _f in std_raw + (selected_sci_raw if REDO_TARGET else sci_raw):
    _src = work(os.path.basename(_f))
    _dst = os.path.join(
        _debug_dir, os.path.splitext(os.path.basename(_f))[0] + ".after_step3.fits"
    )
    if os.path.exists(_src) and not os.path.exists(_dst):
        _shutil.copy2(_src, _dst)
        print("  Debug snap (step3): " + os.path.basename(_dst))

# =============================================================================
# STEP 4a: Master Flat
# =============================================================================
print("\n=== Step 4a: Master Flat ===")
proc_flats = [work(os.path.basename(f)) for f in flat_raw]
master_flat = work("master_flat.fits")

if not os.path.exists(master_flat):
    iraf.imcombine(
        input=iraf_list(proc_flats, "flat"),
        output=master_flat,
        combine="median",
        reject="avsigclip",
        rdnoise=RDNOISE,
        gain=GAIN,
    )
    print("  Created: " + master_flat)
else:
    print("  Exists, skipping: " + master_flat)

# =============================================================================
# STEP 4b: Normalize flat with longslit.response
#   Interactive: fit the continuum along the dispersion axis.
#   Suggested: spline3, order~20, reject outliers.
# =============================================================================
print("\n=== Step 4b: Flat Response ===")
master_flat_norm = work("master_flat_norm.fits")

if not os.path.exists(master_flat_norm):
    iraf.response(
        calibration=master_flat,
        normalization=master_flat,
        response=master_flat_norm,
        interactive="no",
        threshold="INDEF",
        sample="*",
        naverage=-5,
        function="spline3",
        order=20,
        low_reject=2.0,
        high_reject=2.0,
        niterate=3,
        grow=0,
    )
    print("  Created: " + master_flat_norm)
else:
    print("  Exists, skipping: " + master_flat_norm)

# =============================================================================
# STEP 4c: Apply flat-field to comps, standard, science frames
# =============================================================================
print("\n=== Step 4c: Apply Flat Field ===")
to_flatfield = comp_raw + std_raw + (selected_sci_raw if REDO_TARGET else sci_raw)

from astropy.io import fits as _fits

for raw_file in to_flatfield:
    fn = work(os.path.basename(raw_file))
    if os.path.exists(fn):
        _hdr = _fits.getheader(fn)
        if str(_hdr.get("FLATCOR", "no")).strip().lower() == "yes":
            print("  Already flat-fielded, skipping: " + os.path.basename(fn))
            continue
        iraf.ccdproc(
            images=fn,
            output="",  # in-place
            ccdtype="",
            fixpix="no",
            overscan="no",
            trim="no",
            zerocor="no",
            darkcor="no",
            flatcor="yes",
            flat=master_flat_norm,
            interactive="no",
        )
        print("  Flat-fielded: " + os.path.basename(fn))

# --- Debug snapshot after Step 4c ---
for _f in std_raw + (selected_sci_raw if REDO_TARGET else sci_raw):
    _src = work(os.path.basename(_f))
    _dst = os.path.join(
        _debug_dir, os.path.splitext(os.path.basename(_f))[0] + ".after_flat.fits"
    )
    if os.path.exists(_src) and not os.path.exists(_dst):
        _shutil.copy2(_src, _dst)
        print("  Debug snap (flat): " + os.path.basename(_dst))

# =============================================================================
# STEP 4d: Cosmic Ray Cleaning (LACosmic via astroscrappy)
#   Runs clean_cr.py using the current interpreter by default.
#   Cleans science frames in-place before aperture extraction.
# =============================================================================
print("\n=== Step 4d: Cosmic Ray Cleaning ===")
import subprocess as _subprocess

_clean_script = os.path.join(FAST_DIR, "clean_cr.py")
_default_cr_python = sys.executable
_clean_python = os.environ.get("FAST_CR_PYTHON", _default_cr_python)
_ran_cr = False
if not RUN_CR_CLEAN:
    print("  Skipping science-frame LACosmic (--no-cr-clean).")
    _ran_cr = True
elif os.path.exists(_clean_script):
    if not os.path.exists(_clean_python):
        raise SystemExit(
            "CR-cleaning Python not found: %s\n"
            "Set FAST_CR_PYTHON to a valid interpreter with astroscrappy installed."
            % _clean_python
        )
    print("  Running clean_cr.py with: " + _clean_python)
    _ret = _subprocess.call(
        [_clean_python, _clean_script, os.path.basename(SCRIPT_DIR)]
    )
    _ran_cr = _ret == 0
if not _ran_cr:
    print("  WARNING: could not run clean_cr.py (astroscrappy not found). Skipping.")

# --- Debug snapshot after Step 4d ---
for _f in std_raw + (selected_sci_raw if REDO_TARGET else sci_raw):
    _src = work(os.path.basename(_f))
    _dst = os.path.join(
        _debug_dir, os.path.splitext(os.path.basename(_f))[0] + ".after_cr.fits"
    )
    if os.path.exists(_src) and not os.path.exists(_dst):
        _shutil.copy2(_src, _dst)
        print("  Debug snap (CR): " + os.path.basename(_dst))

# =============================================================================
# STEP 4e: Sky subtraction (handled inside apall via background='fit')
# =============================================================================
iraf.chdir(WORK_DIR)


# =============================================================================
# STEP 5: Aperture Extraction (apall)
#
#   - Run interactively on the standard star to define aperture and trace.
#   - Reuse that aperture (reference=) for all other frames.
#   - Output format: onedspec  ->  filename.0001.fits
# =============================================================================
print("\n=== Step 5: Aperture Extraction ===")
iraf.unlearn("apall")

# Auto-detect standard star (first file matching *.Hiltner600.fits)
if not std_raw:
    raise SystemExit("No standard star frames found in " + RAW_DIR)
std_proc = work(os.path.basename(std_raw[0]))
std_base = os.path.splitext(os.path.basename(std_raw[0]))[0]
std_1d = work(std_base + ".0001.fits")

if not os.path.exists(std_1d):
    # Verify the spatial peak is near the center, not at the chip edge.
    # FAST CCD: 161 rows; acceptable range = central 70% (rows ~24-136).
    import numpy as _np2
    from astropy.io import fits as _fits2

    with _fits2.open(std_proc) as _hdul:
        _data2d = _hdul[0].data  # shape: (nrows, ncols)
    _profile = _np2.median(_data2d, axis=1)
    _nrows = len(_profile)
    _margin = int(_nrows * 0.15)  # 15% margin on each side
    _peak_all = int(_np2.argmax(_profile))
    _peak_cen = int(_margin + _np2.argmax(_profile[_margin : _nrows - _margin]))
    if abs(_peak_all - _peak_cen) > 3:
        raise SystemExit(
            "Spatial peak of std star is at row %d (too close to edge).\n"
            "Expected near row %d (central 70%%, rows %d-%d).\n"
            "Check the standard star frame: %s"
            % (_peak_all, _nrows // 2, _margin, _nrows - _margin, std_proc)
        )
    print("  Spatial peak at row %d (center=%d) -- OK" % (_peak_all, _nrows // 2))

    print("  Extracting standard star:")
    iraf.apall(
        input=os.path.basename(std_proc),
        output=std_base,
        format="onedspec",
        interactive=AP_INTERACTIVE,
        nfind=1,
        find="yes",
        recenter="yes",
        resize="no",
        edit=AP_INTERACTIVE,
        trace="yes",
        fittrace="yes",
        extract="yes",
        extras="yes",
        review="no",
        background="fit",
        b_function="legendre",
        b_sample="-40:-20,20:40",
        lower=-10,
        upper=10,
        weights="variance",
        pfit="fit1d",
        clean=AP_CLEAN,
        readnoise=RDNOISE,
        gain=GAIN,
        lsigma=4.0,
        usigma=4.0,
        nsum=10,
        t_nsum=10,
        t_step=10,
        t_function="spline3",
        t_order=4,
        t_niterate=3,
        t_low=3.0,
        t_high=3.0,
    )
    print("  Created: " + std_1d)
else:
    print("  Exists, skipping: " + std_1d)


# Extract science frames independently -- each object finds its own trace
# since different targets may land at different slit positions.
def framenum(name):
    return int(os.path.basename(name).split(".")[0])


for fn in [
    work(os.path.basename(f)) for f in (selected_sci_raw if REDO_TARGET else sci_raw)
]:
    base = os.path.splitext(os.path.basename(fn))[0]
    out_1d = work(base + ".0001.fits")
    fn_extract = fn
    _this_target = (
        os.path.basename(fn).split(".")[1] if "." in os.path.basename(fn) else ""
    )
    _redo_this = INTERACTIVE and REDO_TARGET and REDO_TARGET in _this_target
    if _redo_this and os.path.exists(out_1d):
        os.remove(out_1d)
        print("  Removed for interactive redo: " + os.path.basename(out_1d))
    if not os.path.exists(out_1d):
        print("  Extracting science from: " + os.path.basename(fn_extract))
        if INTERACTIVE:
            print("")
            print("  ── apall interactive keys ─────────────────────────────")
            print("  Aperture editor:  m=mark new ap  d=delete  l/u=set limits")
            print("                    z=zoom  r=redraw  ?=help  q=done")
            print("  Background:       b=enter bkg mode")
            print("    in bkg mode:    s=mark region endpoints (start+end)")
            print("                    f=fit  d=delete region  q=exit bkg mode")
            print("  Trace fit:        (enters automatically)  d=delete pt")
            print("                    f=fit  u=undelete  q=accept fit")
            print("  ───────────────────────────────────────────────────────")
            print("")
        _apall_kw = dict(
            input=os.path.basename(fn_extract),
            output=base,
            format="onedspec",
            interactive=AP_INTERACTIVE,
            nfind=1,
            find="yes",
            recenter="yes",
            resize="yes",
            edit=AP_INTERACTIVE,
            trace="yes",
            fittrace="yes",
            extract="yes",
            extras="yes",
            review="no",
            background="fit",
            b_function="chebyshev",
            b_order=3,
            b_sample="-21:-6,6:21",
            lower=-2,
            upper=2,
            weights="variance",
            pfit="fit1d",
            clean=AP_CLEAN,
            readnoise=RDNOISE,
            gain=GAIN,
            lsigma=4.0,
            usigma=4.0,
            nsum=10,
            t_nsum=20,
            t_step=10,
            t_function="spline3",
            t_order=4,
            t_niterate=3,
            t_low=3.0,
            t_high=3.0,
        )
        iraf.apall(**_apall_kw)
        print("  Created: " + out_1d)
    else:
        print("  Exists, skipping: " + out_1d)

# Extract COMP frames with NO background subtraction.
# Each COMP uses the trace of the nearest science/std frame
# (lamp fills slit so aperture position matters less, but we keep
#  it geometrically consistent with the frame it calibrates).
all_ref_procs = [(framenum(f), work(os.path.basename(f))) for f in std_raw] + [
    (framenum(f), work(os.path.basename(f))) for f in sci_raw
]


def nearest_ref_work(comp_fn):
    """Return the processed 2D frame closest in frame number to comp_fn."""
    cnum = framenum(comp_fn)
    return min(all_ref_procs, key=lambda x: abs(x[0] - cnum))[1]


for fn in [work(os.path.basename(f)) for f in comp_raw]:
    base = os.path.splitext(os.path.basename(fn))[0]
    out_1d = work(base + ".0001.fits")
    if os.path.exists(out_1d):
        print("  Exists, skipping: " + os.path.basename(out_1d))
        continue
    ref = nearest_ref_work(fn)
    print(
        "  Extracting COMP (ref: %s): %s"
        % (os.path.basename(ref), os.path.basename(fn))
    )
    iraf.apall(
        input=os.path.basename(fn),
        output="",
        format="onedspec",
        interactive="no",
        find="no",
        recenter="yes",
        resize="no",
        edit="no",
        trace="yes",
        fittrace="no",
        extract="yes",
        extras="yes",
        review="no",
        reference=os.path.basename(ref),
        background="none",
        weights="none",
        readnoise=RDNOISE,
        gain=GAIN,
        nsum=10,
    )
    print("  Created: " + out_1d)

# =============================================================================
# STEP 6: Wavelength Calibration
#
#   FAST uses a HeNeAr comparison lamp.
#   Arc frames adjacent to each science exposure:
#     0044 Hiltner600  ->  COMP 0045
#     0046 2026bpu     ->  COMP 0045  (before)
#     0047 2026bpu     ->  COMP 0048  (after)
#     0049 Wasp85Ab    ->  COMP 0050  (after)
#     0051 hostsZTF    ->  COMP 0052  (after)
# =============================================================================
print("\n=== Step 6: Wavelength Calibration ===")

# Change to reduced/ so IRAF database paths stay short
iraf.chdir(WORK_DIR)

# Ensure database directory exists
db_dir = os.path.join(WORK_DIR, "database")
if not os.path.exists(db_dir):
    os.makedirs(db_dir)

# Use bare filenames (no path) since we are now in WORK_DIR
comp_1d_names = [
    os.path.splitext(os.path.basename(f))[0] + ".0001.fits" for f in comp_raw
]


# 6a: Choose reference COMP -- prefer one that already has an identify solution in the DB.
def _pick_ref_comp(comp_raw, db_dir):
    """Return the 1D name of the COMP with an existing DB solution (most features),
    falling back to the last COMP if none have been identified yet."""
    best, best_n = None, 0
    for f in comp_raw:
        name1d = os.path.splitext(os.path.basename(f))[0] + ".0001.fits"
        dbf = os.path.join(db_dir, "id" + os.path.splitext(name1d)[0])
        if not os.path.exists(dbf):
            continue
        with open(dbf) as _fh:
            for line in _fh:
                if line.strip().startswith("features"):
                    n = int(line.split()[1])
                    if n > best_n:
                        best, best_n = name1d, n
                    break
    return (
        best
        if best
        else os.path.splitext(os.path.basename(comp_raw[-1]))[0] + ".0001.fits"
    )


ref_comp_1d = _pick_ref_comp(comp_raw, db_dir)
ref_comp_name = ref_comp_1d
ref_comp_db = os.path.join(db_dir, "id" + os.path.splitext(ref_comp_1d)[0])
COORDLIST = os.path.join(FAST_DIR, "ArI_fast.dat")


def db_has_features(db_file):
    """Return True if the identify database file has at least one feature."""
    if not os.path.exists(db_file):
        return False
    with open(db_file) as f:
        for line in f:
            if line.strip().startswith("features") and int(line.split()[1]) > 0:
                return True
    return False


# Master template stored in FAST/templates/ for cross-night reuse
TEMPLATE_DIR = os.path.join(FAST_DIR, "templates")
template_db = os.path.join(TEMPLATE_DIR, "idarc_template")
template_fits = os.path.join(TEMPLATE_DIR, "arc_template.fits")
ref_comp_path = os.path.join(WORK_DIR, ref_comp_name)

print("  Step 6a: wavelength solution for " + ref_comp_name + ":")
if db_has_features(ref_comp_db):
    print("  Database found, skipping.")
elif db_has_features(template_db) and os.path.exists(template_fits):
    import shutil as _shutil, re as _re

    print("  No solution yet -- auto-fitting from master template...")
    _shutil.copy(template_fits, os.path.join(WORK_DIR, "arc_template.fits"))
    _local_db = os.path.join(db_dir, "idarc_template")
    _shutil.copy(template_db, _local_db)
    # Patch whatever internal name was saved to 'arc_template' so IRAF can find it
    with open(_local_db) as _f:
        _content = _f.read()
    _content = _re.sub(
        r"(begin\s+identify\s+)\S+(\s+-\s+Ap)", r"\1arc_template\2", _content
    )
    _content = _re.sub(r"((?:^|\n)\tid\s+)\S+", r"\1arc_template", _content)
    _content = _re.sub(r"(image\s+)\S+(\s+-\s+Ap)", r"\1arc_template\2", _content)
    with open(_local_db, "w") as _f:
        _f.write(_content)
    iraf.reidentify(
        reference="arc_template.fits",
        images=ref_comp_name,
        coordlist=COORDLIST,
        interactive="no",
        refit="yes",
        shift=0,
        search=100,
        nlost=36,
        threshold=3,
        database="database",
        verbose="yes",
    )
    if db_has_features(ref_comp_db):
        print("  Auto-fit succeeded.")
        _shutil.copy(ref_comp_path, template_fits)
        # Save template DB with internal name normalised to 'arc_template'
        with open(ref_comp_db) as _f:
            _tcontent = _f.read()
        _stem = os.path.splitext(ref_comp_name)[0]
        _tcontent = _tcontent.replace(_stem, "arc_template")
        with open(template_db, "w") as _f:
            _f.write(_tcontent)
        print("  Master template updated.")
    else:
        print("")
        print("  *** Auto-fit failed -- run identify manually: ***")
        print("      cd " + WORK_DIR + " && pyraf")
        print("      --> iraf.noao(); iraf.onedspec()")
        print(
            '      --> iraf.identify("'
            + ref_comp_name
            + '", coordlist="'
            + COORDLIST
            + '", units="Angstroms")'
        )
        print("          (mark Ar lines, chebyshev order 4-5, niterate=3, then :q)")
        print("")
        raise SystemExit("Re-run reduction.py after identify is complete.")
else:
    print("")
    print("  *** No template found -- run identify manually (first time only): ***")
    print("      cd " + WORK_DIR + " && pyraf")
    print("      --> iraf.noao(); iraf.onedspec()")
    print(
        '      --> iraf.identify("'
        + ref_comp_name
        + '", coordlist="'
        + COORDLIST
        + '", units="Angstroms")'
    )
    print("          (mark Ar lines, chebyshev order 4-5, niterate=3, then :q)")
    print("")
    raise SystemExit("Re-run reduction.py after identify is complete.")

# 6b: Reidentify each COMP using arc_sky_combined as reference.
# search=0 prevents cross-correlation shift (sky lines in reference would
# cause wrong shift in pure-arc COMPs if search != 0).
remaining_comps = [
    c
    for c in comp_1d_names
    if not db_has_features(os.path.join(db_dir, "id" + os.path.splitext(c)[0]))
]
if remaining_comps and db_has_features(ref_comp_db):
    print("  Step 6b: reidentify (search=0, no cross-correlation shift):")
    iraf.reidentify(
        reference=ref_comp_name,
        images=iraf_list(remaining_comps, "comp1d"),
        coordlist=COORDLIST,
        interactive="no",
        refit="yes",
        shift=0,
        search=0,
        nlost=5,
        threshold=5,
        database="database",
        verbose="yes",
    )
else:
    print("  Step 6b: all COMPs already identified, skipping.")

# 6c: Assign nearest COMP to each science/std frame, apply dispcor
print("  Step 6c: dispcor -- apply wavelength solutions:")


def nearest_comp(sci_base, comp_1d_names):
    """Return the COMP taken right after the science frame (arc is always
    taken after the exposure). Falls back to the previous COMP if no
    later one exists (e.g. last frame of the night)."""
    sci_num = framenum(sci_base)
    after = [c for c in comp_1d_names if framenum(c) > sci_num]
    before = [c for c in comp_1d_names if framenum(c) < sci_num]
    if after:
        closest = min(after, key=lambda c: framenum(c))
    else:
        closest = max(before, key=lambda c: framenum(c))
    return os.path.splitext(closest)[0]


all_sci_1d = [
    os.path.splitext(os.path.basename(f))[0] + ".0001.fits" for f in std_raw
] + [
    os.path.splitext(os.path.basename(f))[0] + ".0001.fits"
    for f in (selected_sci_raw if REDO_TARGET else sci_raw)
]

# Print arc assignment table upfront
print("  Arc assignment:")
for sci_base in all_sci_1d:
    comp_ref = nearest_comp(sci_base, comp_1d_names)
    print("    %-35s -> %s" % (sci_base, comp_ref + ".fits"))

for sci_base in all_sci_1d:
    out_base = sci_base.replace(".0001.fits", ".w.0001.fits")
    if not os.path.exists(out_base) and os.path.exists(sci_base):
        comp_ref = nearest_comp(sci_base, comp_1d_names)
        iraf.hedit(
            images=sci_base,
            fields="REFSPEC1",
            value=comp_ref,
            add="yes",
            verify="no",
            show="no",
            update="yes",
        )
        iraf.dispcor(
            input=sci_base,
            output=out_base,
            database="database",
            w1="INDEF",
            w2="INDEF",
            dw="INDEF",
            nw="INDEF",
            log="no",
            flux="no",
        )
        print("  Wavelength calibrated: " + out_base + " (ref: " + comp_ref + ")")
    else:
        print("  Exists or missing input, skipping: " + sci_base)

# =============================================================================
# STEP 7: Flux Calibration
#
#   Standard star: Hiltner 600  (onedstds$spec50cal/)
#   Extinction:    kpnoextinct.dat (KPNO/Arizona -- closest available to FLWO)
# =============================================================================
print("\n=== Step 7: Flux Calibration ===")

# Still in WORK_DIR from step 6 -- use bare filenames for intermediate files

# Remove stale outputs so sensfunc/standard don't ask for new names
# Skip if redoing only one target -- the sensitivity function is still valid
if not REDO_TARGET:
    for stale in glob.glob(work("sens*.fits")) + [work("std")]:
        if os.path.exists(stale):
            os.remove(stale)

# 7a: Compute airmass for standard and science frames from RA/Dec/UT
print("  Step 7a: setairmass:")
all_wav_frames = [
    os.path.splitext(os.path.basename(f))[0] + ".w.0001.fits" for f in std_raw
] + [
    os.path.splitext(os.path.basename(f))[0] + ".w.0001.fits"
    for f in (selected_sci_raw if REDO_TARGET else sci_raw)
]
for fn in all_wav_frames:
    if os.path.exists(fn):
        iraf.setairmass(
            images=fn,
            observatory="flwo",
            intype="beginning",
            outtype="middle",
            ra="ra",
            dec="dec",
            equinox="epoch",
            ut="ut",
            date="date-obs",
            exposure="exptime",
            airmass="airmass",
            utmiddle="utmiddle",
            show="no",
            update="yes",
        )

# 7b+7c: standard + sensfunc -- skip if redoing a single target and sens already exists
print("  Step 7b: standard:")
std_w = os.path.splitext(os.path.basename(std_raw[0]))[0] + ".w.0001.fits"
if REDO_TARGET and os.path.exists(work("std")) and glob.glob(work("sens*.fits")):
    print("  Skipping standard+sensfunc -- reusing existing sensitivity function.")
else:
    iraf.standard(
        input=std_w,
        output="std",
        samestar="yes",
        beam_switch="no",
        apertures="",
        bandwidth="INDEF",
        bandsep="INDEF",
        fnuzero=3.68e-20,
        extinction="onedstds$kpnoextinct.dat",
        caldir=STD_CALDIR.get(std_name, "onedstds$spechayescal/"),
        observatory="flwo",
        interact="no",
        star_name=std_name,
    )

    print("  Step 7c: sensfunc:")
    iraf.sensfunc(
        standards="std",
        sensitivity="sens",
        extinction="onedstds$kpnoextinct.dat",
        newextinction="extinct.dat",
        observatory="flwo",
        function="spline3",
        order=6,
        interactive="no",
        graphs="sr",
        marks="plus cross box",
        colors="2 1 3 4",
    )

# 7d: Apply flux calibration to science spectra
print("  Step 7d: calibrate:")
sci_wav_basenames = [
    os.path.splitext(os.path.basename(f))[0] + ".w.0001.fits"
    for f in (selected_sci_raw if REDO_TARGET else sci_raw)
]

for fn in sci_wav_basenames:
    _base = fn.replace(".w.0001.fits", "")
    out = work(_base + ".wf.0001.fits")
    if not os.path.exists(out) and os.path.exists(fn):
        iraf.calibrate(
            input=fn,
            output=out,
            sensitivity="sens",
            extinction="onedstds$kpnoextinct.dat",
            observatory="flwo",
            ignoreaps="no",
            flux="yes",
            fnu="no",
        )
        iraf.unlearn("calibrate")
        print("  Flux calibrated: " + out)
    else:
        print("  Exists or missing input, skipping: " + fn)

# =============================================================================
# Done
# =============================================================================
# STEP 8: Stack 1D spectra by target
# =============================================================================
print("\n=== Step 8: Stacking spectra by target ===")

# Group flux-calibrated spectra by object name (second dot-separated field)
from collections import defaultdict

# chdir to WORK_DIR so scombine uses bare filenames -- avoids IRAF path-length limit
iraf.chdir(WORK_DIR)

groups = defaultdict(list)
for fn in sorted(glob.glob("*.wf.0001.fits")):  # bare names, CWD is WORK_DIR
    target = os.path.basename(fn).split(".")[1]
    if REDO_TARGET and REDO_TARGET not in target:
        continue
    groups[target].append(fn)

for target, frames in groups.items():
    out = target + ".stack.fits"  # bare name, written to WORK_DIR
    _out_full = work(target + ".stack.fits")
    if os.path.exists(_out_full) and not (REDO_TARGET and REDO_TARGET in target):
        print("  Exists, skipping: " + out)
        continue
    if os.path.exists(_out_full):
        os.remove(_out_full)
    if len(frames) == 1:
        import shutil

        shutil.copy(frames[0], out)
        print("  Only 1 frame for " + target + ", copied to " + out)
    else:
        print("  Stacking " + str(len(frames)) + " frames for " + target + " -> " + out)
        _listfile = "_stack_" + target + ".txt"
        with open(_listfile, "w") as _lf:
            _lf.write("\n".join(frames) + "\n")
        iraf.scombine(
            input="@" + _listfile,
            output=out,
            combine="average",
            reject="avsigclip",
            lsigma=3.0,
            hsigma=3.0,
            scale="exposure",
            weight="exposure",
            logfile="",
        )

# =============================================================================
# STEP 9: Export stacked spectra to ASCII
# =============================================================================
print("\n=== Step 9: Export to ASCII ===")
import numpy as np
from astropy.io import fits as astrofits

ascii_dir = os.path.join(NIGHT_DIR, "ascii")
if not os.path.exists(ascii_dir):
    os.makedirs(ascii_dir)

from astropy.time import Time

for stack_file in sorted(glob.glob(os.path.join(WORK_DIR, "*.stack.fits"))):
    with astrofits.open(stack_file) as hdul:
        data = hdul[0].data
        hdr = hdul[0].header
    crval = hdr["CRVAL1"]
    cdelt = hdr.get("CD1_1") or hdr.get("CDELT1")
    if data.ndim == 3:
        flux = data[0, 0, :]
        flux_err = data[3, 0, :] if data.shape[0] > 3 else np.zeros_like(flux)
    elif data.ndim == 2:
        flux = data[0, :]
        flux_err = data[3, :] if data.shape[0] > 3 else np.zeros_like(flux)
    else:
        flux = data
        flux_err = np.zeros_like(flux)
    wave = crval + cdelt * np.arange(len(flux))
    target = os.path.basename(stack_file).replace(".stack.fits", "")
    if REDO_TARGET and REDO_TARGET not in target:
        continue

    # Compute average mid-exposure time from contributing frames
    _frames = sorted(glob.glob(os.path.join(WORK_DIR, "*." + target + ".wf.0001.fits")))
    _times = []
    for _fr in _frames:
        _h = astrofits.getheader(_fr)
        _ut = _h.get("UTMIDDLE") or _h.get("DATE-OBS")
        if _ut:
            try:
                _times.append(Time(_ut).mjd)
            except Exception:
                pass
    if _times:
        _avg_time = Time(np.mean(_times), format="mjd")
        _time_str = _avg_time.isot
        _mjd_str = "%.6f" % _avg_time.mjd
    else:
        _time_str = hdr.get("UTMIDDLE") or hdr.get("DATE-OBS") or "unknown"
        _mjd_str = "unknown"

    out_file = os.path.join(ascii_dir, target + ".ascii")
    np.savetxt(
        out_file,
        np.column_stack([wave, flux, flux_err]),
        header="target: %s\nobs_time_utc (mid-exp avg): %s\nobs_mjd (mid-exp avg): %s\nwavelength_A  flux_erg_s-1_cm-2_A-1  flux_err"
        % (target, _time_str, _mjd_str),
        fmt="%.4f  %.6e  %.6e",
    )
    print("  Saved: " + out_file + "  (MJD=" + _mjd_str + ")")

# =============================================================================
# Plot stacked spectra and save to PDF
# =============================================================================
print("\n=== Step 10: Plotting stacked spectra ===")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _load_spec(path):
    with astrofits.open(path) as _h:
        _d = _h[0].data
        _hdr = _h[0].header
    if _d.ndim == 3:
        _fl = _d[0, 0, :]
    elif _d.ndim == 2:
        _fl = _d[0, :]
    else:
        _fl = _d
    _crval = _hdr["CRVAL1"]
    _cdelt = _hdr.get("CD1_1") or _hdr.get("CDELT1")
    return _crval + _cdelt * np.arange(len(_fl)), _fl


_stack_files = sorted(glob.glob(os.path.join(WORK_DIR, "*.stack.fits")))
if _stack_files:
    _plot_params = {
        "legend.fontsize": 18,
        "figure.figsize": (15, 5),
        "axes.labelsize": 15,
        "axes.titlesize": 19,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "ytick.major.size": 5.5,
        "axes.linewidth": 2,
    }
    with plt.rc_context(_plot_params):
        _fig, _axes = plt.subplots(
            len(_stack_files),
            1,
            figsize=(15, max(7, 4.2 * len(_stack_files))),
            sharex=False,
        )
        if len(_stack_files) == 1:
            _axes = [_axes]
        for _ax, _fn in zip(_axes, _stack_files):
            _tgt = os.path.basename(_fn).replace(".stack.fits", "")
            _wave, _flux = _load_spec(_fn)
            _ax.plot(_wave, _flux, lw=1.0, color="firebrick")
            _ax.set_xlim(_wave[0], _wave[-1])
            _ax.set_ylim(np.nanpercentile(_flux, 1), np.nanpercentile(_flux, 99))
            _ax.set_ylabel(r"Flux", size=20)
            _ax.set_title(_tgt, size=20)
            _ax.minorticks_on()
            _ax.tick_params(axis="both", which="major", labelsize=14, length=8, width=2)
            _ax.tick_params(axis="both", which="minor", labelsize=12, length=4, width=1)
        _axes[-1].set_xlabel(r"Wavelength ($\AA$)", size=20)
        plt.tight_layout()
        _plot_out = os.path.join(
            os.path.dirname(NIGHT_DIR),
            "spectra_" + os.path.basename(NIGHT_DIR) + ".pdf",
        )
        plt.savefig(_plot_out, dpi=150)
        plt.close()
        print("  Saved: " + _plot_out)
else:
    print("  No stacked spectra found, skipping.")

# =============================================================================
# Copy stacked spectra to final/
# =============================================================================
print("\n=== Step 11: Copying stacked spectra to final/ ===")
import shutil as _shutil2

final_dir = os.path.join(NIGHT_DIR, "final")
if not os.path.exists(final_dir):
    os.makedirs(final_dir)
for _sf in sorted(glob.glob(os.path.join(WORK_DIR, "*.stack.fits"))):
    _dst = os.path.join(final_dir, os.path.basename(_sf))
    _shutil2.copy(_sf, _dst)
    print("  Copied: " + os.path.basename(_sf))

# =============================================================================
print("\n=== Reduction complete! ===")
print("Final flux-calibrated spectra:")
for fn in sorted(glob.glob(os.path.join(WORK_DIR, "*.wf.0001.fits"))):
    print("  " + fn)
print("Stacked spectra:")
for fn in sorted(glob.glob(os.path.join(WORK_DIR, "*.stack.fits"))):
    print("  " + fn)
