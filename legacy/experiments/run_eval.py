"""Reproduce the complete bounded experiment in a fresh output directory."""
import argparse
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from experiments import eval_loop,eval_audit,eval_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve()
    if out.exists():parser.error('Output already exists. Choose a fresh directory to preserve earlier results.')
    out.mkdir(parents=True)
    templates=ROOT/'analysis/eval_loop_v3'
    for name in ('plan.json','supplemental_plan.json'):
        shutil.copyfile(templates/name,out/name)
    eval_loop.OUT=out
    eval_audit.OUT=out
    eval_loop.run()
    eval_audit.run()
    eval_report.run(out)

if __name__=='__main__':main()
