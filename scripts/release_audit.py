"""Compare runtime sources without reading credentials, data or local artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOTS = ('ai_chat','telegram_bot','core','db','ingestion','normalized','snapshots','metrics','tests')
def digest(data):
    return hashlib.sha256(data).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-root',required=True,type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    differences=[]
    for root in ROOTS:
        local={str(f.relative_to(repo)) for f in (repo/root).rglob('*.py') if '__pycache__' not in f.parts}
        test={str(f.relative_to(args.test_root)) for f in (args.test_root/root).rglob('*.py') if '__pycache__' not in f.parts}
        for name in sorted(local|test):
            a=repo/name;b=args.test_root/name
            left=digest(a.read_bytes()) if a.exists() else None
            right=digest(b.read_bytes()) if b.exists() else None
            if left!=right:differences.append({'path':name,'release_sha256':left,'test_sha256':right})
    result={'production_checkout_commit':commit,'differences':differences,
            'notice':'Differences include production-only fixes. Review against the last common release; do not overwrite blindly. Database rules are versioned separately in releases/<id>/rules.json.'}
    value=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:args.output.write_text(value+'\n')
    else:print(value)
if __name__=='__main__':main()
