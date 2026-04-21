#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Cosmic ray cleaning using LACosmic (astroscrappy).
Run this AFTER step 3 of reduction.py (CCD processing) but BEFORE extraction.

Usage:
    python clean_cr.py                  # cleans all nights
    python clean_cr.py 2026.0318        # clean a specific night
"""

import os
import sys
import glob
import numpy as np
import astroscrappy
from astropy.io import fits
from scipy.ndimage import median_filter

FAST_DIR = os.path.abspath(os.path.dirname(__file__))
GAIN     = 0.8    # e-/ADU
RDNOISE  = 4.4    # e-

# Conservative-but-active settings for faint SN spectra.
CR_SIGCLIP = 4.5
CR_SIGFRAC = 0.3
CR_OBJLIM  = 3.5
CR_NITER   = 3
TRACE_PROTECT_HALF_WIDTH = 4
TRACE_PROTECT_FRACTION = 0.40


def clean_night(night_dir):
    reduced = os.path.join(night_dir, 'reduced')
    if not os.path.exists(reduced):
        print('  No reduced/ dir in ' + night_dir + ', skipping.')
        return

    # Find 2D science frames only (exclude calibration and extracted frames)
    sci_files = [f for f in sorted(glob.glob(os.path.join(reduced, '*.fits')))
                 if not any(tag in os.path.basename(f) for tag in
                     ['.0001.', '.w.', '.wf.', '.stack.', '.sky.',
                      'master_', 'arc_template', 'sens', 'std',
                      'FLAT', 'BIAS', 'DARK', 'COMP'])]

    print('Night: ' + os.path.basename(night_dir) +
          ' -- %d 2D frames to clean' % len(sci_files))
    print('  LACosmic params: sigclip=%.1f sigfrac=%.1f objlim=%.1f niter=%d'
          % (CR_SIGCLIP, CR_SIGFRAC, CR_OBJLIM, CR_NITER))

    for fn in sci_files:
        with fits.open(fn, output_verify='ignore') as hdul:
            data = hdul[0].data
            if data is None or data.ndim != 2:
                continue
            if str(hdul[0].header.get('CRCLEAN', 'no')).strip().lower() == 'yes':
                print('  Already CR-cleaned, skipping: ' + os.path.basename(fn))
                continue

            # Build a smooth 1D spectral model along dispersion, then run
            # LACosmic on the residual so broad spectral structure is less
            # likely to be flagged as CRs.
            data64 = data.astype(np.float64)
            model = median_filter(data64, size=(1, 201))

            _kwargs = dict(
                gain=GAIN,
                readnoise=RDNOISE,
                sigclip=CR_SIGCLIP,
                sigfrac=CR_SIGFRAC,
                objlim=CR_OBJLIM,
                niter=CR_NITER,
                cleantype='medmask',
                verbose=False,
            )
            try:
                crmask, clean = astroscrappy.detect_cosmics(
                    data64, bkg=model, **_kwargs
                )
            except TypeError:
                try:
                    crmask, clean = astroscrappy.detect_cosmics(
                        data64, inbkg=model, **_kwargs
                    )
                except TypeError:
                    resid = data64 - model
                    crmask, clean_resid = astroscrappy.detect_cosmics(
                        resid, **_kwargs
                    )
                    clean = clean_resid + model

            # Protect compact object traces from over-cleaning.
            rows = np.arange(data64.shape[0])
            profile = np.median(data64, axis=1)
            peak_row = int(np.argmax(profile))
            pos_flux = np.clip(data64, 0.0, None)
            total_flux = float(pos_flux.sum())
            if total_flux > 0.0:
                core_rows = np.abs(rows - peak_row) <= TRACE_PROTECT_HALF_WIDTH
                core_fraction = float(pos_flux[core_rows, :].sum() / total_flux)
            else:
                core_fraction = 0.0
            if core_fraction >= TRACE_PROTECT_FRACTION:
                protect_rows = np.abs(rows - peak_row) <= TRACE_PROTECT_HALF_WIDTH
                crmask[protect_rows, :] = False
                clean[protect_rows, :] = data64[protect_rows, :]

            n_cr = int(crmask.sum())
            if n_cr > 0:
                hdul[0].data = clean.astype(data.dtype)
            hdul[0].header['CRCLEAN'] = ('yes', 'LACosmic CR cleaning applied')
            hdul.writeto(fn, overwrite=True, output_verify='ignore')
            if n_cr > 0:
                print('  Cleaned %4d CR pixels: %s' % (n_cr, os.path.basename(fn)))
            else:
                print('  No CRs found:           ' + os.path.basename(fn))
            if total_flux > 0.0:
                print('    Trace core frac=%.3f peak_row=%d'
                      % (core_fraction, peak_row))


if __name__ == '__main__':
    if len(sys.argv) > 1:
        nights = [os.path.join(FAST_DIR, sys.argv[1])]
    else:
        nights = sorted(glob.glob(os.path.join(FAST_DIR, '202*.*')))

    for night in nights:
        if os.path.isdir(night):
            clean_night(night)
