#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Ingest raw FAST data from FLWO observer account.

Usage:
    python ingest.py <date>            e.g.  python ingest.py 2026.0320
    python ingest.py <date> --dry-run  print the rsync command without running it
"""

import os
import sys
import subprocess

FAST_DIR  = os.path.abspath(os.path.dirname(__file__) or '.')
REMOTE    = 'observer@flwo60.sao.arizona.edu'
REMOTE_BASE = '/rdata/fast'

def ingest(date, dry_run=False):
    night_dir = os.path.join(FAST_DIR, date)
    raw_dir   = os.path.join(night_dir, 'raw')

    if not os.path.exists(raw_dir):
        os.makedirs(raw_dir)
        print('Created: ' + raw_dir)

    src = '%s:%s/%s/' % (REMOTE, REMOTE_BASE, date)
    cmd = ['rsync', '-avz', '--progress', src, raw_dir + '/']

    print('Running: ' + ' '.join(cmd))
    if dry_run:
        print('(dry run — not executing)')
        return

    ret = subprocess.call(cmd)
    if ret != 0:
        raise SystemExit('rsync failed with exit code %d' % ret)

    files = sorted(os.listdir(raw_dir))
    print('\nIngested %d files into %s:' % (len(files), raw_dir))
    for f in files:
        print('  ' + f)

if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    dry_run = '--dry-run' in sys.argv

    if not args:
        raise SystemExit('Usage: python ingest.py <date> [--dry-run]  (e.g. 2026.0320)')

    ingest(args[0], dry_run=dry_run)
