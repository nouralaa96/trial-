"""Verify the frozen deliverable, or reproduce its experiment into a fresh folder."""
from pathlib import Path
import argparse
import subprocess
import sys

ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-only',action='store_true',help='Verify hashes and run tests without fitting.')
    mode.add_argument('--output',type=Path,help='Fresh external folder for the same frozen experiment; never changes selection rules.')
    args=parser.parse_args()
    if args.output:
        output=args.output.resolve()
        if output.exists():parser.error('Output must not already exist')
        if output==ROOT or ROOT in output.parents:
            parser.error('Use an external output folder to preserve this deliverable manifest')
    subprocess.run([sys.executable,'manifest.py','--verify'],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'-m','pytest','tests','-q'],cwd=ROOT,check=True)
    if args.output:
        subprocess.run([sys.executable,'evaluate.py','--run','--output',str(output)],cwd=ROOT,check=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
