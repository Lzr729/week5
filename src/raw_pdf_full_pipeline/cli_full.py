from __future__ import annotations
import argparse,json
from .finalize import verify_bundle

def main():
 p=argparse.ArgumentParser(); p.add_argument("--bundle",required=True); a=p.parse_args(); print(json.dumps(verify_bundle(a.bundle),ensure_ascii=False,indent=2))
if __name__=="__main__": main()
