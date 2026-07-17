#!/usr/bin/env python3
"""Stage 06 compact pipeline: validate bundle or generate CSVs on demand."""
from __future__ import annotations
import argparse,csv,json
from collections import Counter,defaultdict
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
BUNDLE=ROOT/'data/stage06_bundle.json'; SCHEMA=ROOT/'schemas/stage06.schema.json'
COUNTS={'parties':36,'increase_events':9,'subscriptions':28,'transfer_events':6,'transfer_lots':20,'snapshots':15,'snapshot_holdings':201,'calculations':21,'evidence_reviews':39,'acceptance_checks':13,'audit_log':6}
PK={'parties':'party_id','increase_events':'increase_id','subscriptions':'subscription_id','transfer_events':'transfer_event_id','transfer_lots':'transfer_lot_id','snapshots':'snapshot_id','snapshot_holdings':'snapshot_holding_id','calculations':'calculation_id','evidence_reviews':'record_id','acceptance_checks':'check_id','audit_log':'issue_id'}
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def add(c,i,d,p,x=None):c.append({'check_id':i,'description':d,'status':'passed' if p else 'failed','details':x})
def schema_check(b,s):
 try:
  from jsonschema import Draft202012Validator
 except ImportError:return {'status':'skipped','message':'jsonschema未安装'}
 e=sorted(Draft202012Validator(load(s)).iter_errors(b),key=lambda x:list(x.absolute_path))
 return {'status':'passed' if not e else 'failed','errors':[{'path':'/'.join(map(str,x.absolute_path)),'message':x.message} for x in e[:50]]}
def business(b):
 d=b['tables'];c=[];n=1
 for k,v in COUNTS.items():add(c,f'S06-{n:03d}',f'{k}记录数',len(d[k])==v,{'expected':v,'actual':len(d[k])});n+=1
 for t,k in PK.items():
  vals=[r.get(k) for r in d[t]];dup=[x for x,y in Counter(vals).items() if y>1]
  add(c,f'S06-{n:03d}',f'{t}.{k}唯一且非空',None not in vals and not dup,dup);n+=1
 parties={r['party_id'] for r in d['parties']};incs={r['increase_id'] for r in d['increase_events']};tes={r['transfer_event_id'] for r in d['transfer_events']};snaps={r['snapshot_id'] for r in d['snapshots']}
 fks=[('subscriptions.increase_id',[(r['subscription_id'],r.get('increase_id')) for r in d['subscriptions'] if r.get('increase_id') not in incs]),('subscriptions.party_id',[(r['subscription_id'],r.get('party_id')) for r in d['subscriptions'] if r.get('party_id') and r.get('party_id') not in parties]),('transfer_lots.transfer_event_id',[(r['transfer_lot_id'],r.get('transfer_event_id')) for r in d['transfer_lots'] if r.get('transfer_event_id') not in tes]),('transfer_lots.transferor_party_id',[(r['transfer_lot_id'],r.get('transferor_party_id')) for r in d['transfer_lots'] if r.get('transferor_party_id') and r.get('transferor_party_id') not in parties]),('transfer_lots.transferee_party_id',[(r['transfer_lot_id'],r.get('transferee_party_id')) for r in d['transfer_lots'] if r.get('transferee_party_id') and r.get('transferee_party_id') not in parties]),('snapshots.previous_snapshot_id',[(r['snapshot_id'],r.get('previous_snapshot_id')) for r in d['snapshots'] if r.get('previous_snapshot_id') and r.get('previous_snapshot_id') not in snaps]),('snapshot_holdings.snapshot_id',[(r['snapshot_holding_id'],r.get('snapshot_id')) for r in d['snapshot_holdings'] if r.get('snapshot_id') not in snaps]),('snapshot_holdings.party_id',[(r['snapshot_holding_id'],r.get('party_id')) for r in d['snapshot_holdings'] if r.get('party_id') and r.get('party_id') not in parties])]
 for name,bad in fks:add(c,f'S06-{n:03d}',f'外键完整：{name}',not bad,bad);n+=1
 bt=['parties','increase_events','subscriptions','transfer_events','transfer_lots','snapshots','snapshot_holdings','evidence_reviews','acceptance_checks'];bad={t:sum(r.get('review_status')!='已验收通过' for r in d[t]) for t in bt};bad={k:v for k,v in bad.items() if v};add(c,f'S06-{n:03d}','全部业务记录已验收通过',not bad,bad);n+=1
 by=defaultdict(list)
 for r in d['transfer_lots']:by[r['transfer_event_id']].append(r)
 exp={'TR-EVT-002':{'percentage':22.6},'TR-EVT-004':{'shares':1158750,'consideration':3375.0054},'TR-EVT-005':{'shares':800000,'consideration':80.0},'TR-EVT-006':{'shares':1659535,'consideration':8563.19}};ok=True;det={}
 for eid,e in exp.items():
  rows=by[eid];a={'shares':sum(float(r.get('transferred_shares_original') or 0) for r in rows),'percentage':sum(float(r.get('transferred_percentage_original') or 0) for r in rows),'consideration':sum(float(r.get('consideration_original') or 0) for r in rows)};det[eid]={'expected':e,'actual':a};ok=ok and all(abs(a[k]-v)<=1e-8 for k,v in e.items())
 add(c,f'S06-{n:03d}','转让事件与原子明细合计一致',ok,det);n+=1
 sm={r['snapshot_id']:r for r in d['snapshots']};hb=defaultdict(list)
 for r in d['snapshot_holdings']:hb[r['snapshot_id']].append(r)
 fail=[]
 for sid,s in sm.items():
  if s.get('completeness_status')!='complete':continue
  rows=hb[sid];amount=sum(float(r.get('holding_after_calculated') or 0) for r in rows);pct=sum(float(r.get('holding_percentage_calculated') or 0) for r in rows);total=s.get('capital_total_original') if s.get('capital_total_original') is not None else s.get('capital_total_calculated')
  if abs(amount-float(total))>1e-6 or abs(pct-100)>1e-6:fail.append({'snapshot_id':sid,'expected':total,'actual':amount,'percentage':pct})
 add(c,f'S06-{n:03d}','完整快照持股合计与比例勾稽',not fail,fail);n+=1
 hm=lambda sid:{r['party_id']:float(r.get('holding_after_calculated') or 0) for r in hb[sid]};eq=hm('SNP-014')==hm('SNP-015');add(c,f'S06-{n:03d}','SNP-014与C8终点SNP-015逐股东一致',eq,{'snp014_total':sum(hm('SNP-014').values()),'snp015_total':sum(hm('SNP-015').values())});n+=1
 x=next((r for r in d['calculations'] if r.get('calculation_id')=='S6-CAL-004'),None);add(c,f'S06-{n:03d}','CE-005差异0.00574万元保留至阶段七',x is not None and str(x.get('unrounded_result'))=='0.00574' and '阶段七' in str(x.get('status')),x);n+=1
 ids={str(r.get('event_id')) for t in ['increase_events','transfer_events'] for r in d[t]};add(c,f'S06-{n:03d}','CE-014未纳入资本交易',all(not x.startswith('CE-014') for x in ids),sorted(ids));n+=1
 trace=[(t,r) for t in ['increase_events','transfer_events','snapshots'] for r in d[t] if not r.get('evidence_ids') or not r.get('pdf_pages') or not r.get('printed_pages')];add(c,f'S06-{n:03d}','核心事件和快照保留证据及双页码',not trace,trace);n+=1
 x=next((r for r in d['calculations'] if r.get('calculation_id')=='S6-CAL-016'),None);add(c,f'S06-{n:03d}','S6-CAL-016为8,563.19万元',x is not None and abs(float(x.get('unrounded_result'))-8563.19)<1e-9,x);n+=1
 bad=[r for r in d['acceptance_checks'] if r.get('check_result')!='通过' or r.get('review_status')!='已验收通过'];add(c,f'S06-{n:03d}','验收清单13项全部通过',not bad,bad)
 return c
def validate(args):
 b=load(args.bundle);s=schema_check(b,args.schema);c=business(b);f=[x for x in c if x['status']=='failed'];r={'stage':6,'status':'passed' if not f and s['status']!='failed' else 'failed','schema_validation':s,'business_validation':{'checks_total':len(c),'checks_passed':len(c)-len(f),'checks_failed':len(f),'checks':c}}
 if args.report:args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'status':r['status'],'schema_validation':s['status'],'checks_total':len(c),'checks_passed':len(c)-len(f),'checks_failed':len(f)},ensure_ascii=False));return 0 if r['status']=='passed' else 1
def cv(v):return json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v
def export(args):
 d=load(args.bundle)['tables'];args.output.mkdir(parents=True,exist_ok=True)
 for name,rows in d.items():
  p=args.output/f'{name}.csv'
  if not rows:p.write_text('',encoding='utf-8-sig');continue
  fields=list(rows[0]);h=p.open('w',newline='',encoding='utf-8-sig');w=csv.DictWriter(h,fieldnames=fields);w.writeheader();[w.writerow({k:cv(r.get(k)) for k in fields}) for r in rows];h.close()
 print(f'exported {len(d)} CSV files to {args.output}');return 0
def main():
 p=argparse.ArgumentParser();sp=p.add_subparsers(dest='cmd',required=True);v=sp.add_parser('validate');v.add_argument('--bundle',type=Path,default=BUNDLE);v.add_argument('--schema',type=Path,default=SCHEMA);v.add_argument('--report',type=Path);v.set_defaults(fn=validate);e=sp.add_parser('export-csv');e.add_argument('--bundle',type=Path,default=BUNDLE);e.add_argument('--output',type=Path,required=True);e.set_defaults(fn=export);a=p.parse_args();return a.fn(a)
if __name__=='__main__':raise SystemExit(main())
