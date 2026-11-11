#!/usr/bin/env python3
"""Deterministic real-device 10.1.9 match gate. No game injection or source edits."""
import driver as d
import os,time,re,json,sys
out=sys.argv[1];os.makedirs(out,exist_ok=True);seen=set();start=time.time();last='';same=0
sz=d.adb('shell','wm','size');m=re.search(r'(\d+)x(\d+)',sz);W,H=map(int,m.groups()) if m else (1080,1920)
def swipe(direction):
 x,y=int(W*.45),int(H*.45);dx,dy={'right':(int(W*.3),0),'up':(0,-int(H*.2)),'down':(0,int(H*.2))}[direction];d.adb('shell','input','swipe',str(x),str(y),str(x+dx),str(y+dy),'220')
def activate(n,menu):
 if menu:
  d.tap(n['cx'],n['cy'],False);time.sleep(.25);swipe('right');return
 # Match touch cursor is a known product defect. Use standard keyboard focus
 # to complete the separate engine check, without bypassing game event handlers.
 import xml.etree.ElementTree as ET
 target=(n['desc'] or n['text']).strip()
 for attempt in range(45):
  xml=d.dump_ui()
  try: tree=ET.fromstring(xml)
  except ET.ParseError: raise RuntimeError('Invalid UI tree while focusing '+target)
  focused=[x for x in tree.iter('node') if x.get('focused')=='true']
  if any((x.get('content-desc') or x.get('text') or '').strip()==target for x in focused):
   d.adb('shell','input','keyevent','66');return
  d.adb('shell','input','keyevent','61');time.sleep(.15)
 raise RuntimeError('Could not keyboard-focus match control '+target)
def find(ns,rx):
 r=re.compile(rx,re.I)
 return next((n for n in ns if n['package']==d.PKG and n['clickable'] and n['w']>0 and n['h']>0 and any(r.search(v.strip()) for v in [n['desc'],n['text']] if v.strip())),None)
d.adb('shell','pm','clear',d.PKG);d.adb('shell','am','start','-n',d.MAIN);time.sleep(8)
for step in range(220):
 if time.time()-start>1500:raise RuntimeError('25-minute deterministic match timeout')
 fp=d.foreground_pkg()
 if fp!=d.PKG:raise RuntimeError('Test left game: '+fp)
 xml=d.dump_ui();ns=d.nodes(xml);txt=d.screen_text(ns);low=txt.lower();menu=True;rx=None;act=None
 open(out+'/latest.xml','w').write(xml)
 if txt==last:same+=1
 else:same=0
 last=txt
 if same>18:
  d.shot(out,'stalled');raise RuntimeError('Unchanged UI for19steps: '+txt[:1200])
 if not ns:raise RuntimeError('No UI tree, cannot validate')
 if 'offline hindi speech unavailable' in low:raise RuntimeError('Silent speech fallback')
 if 'play again' in low:
  seen.add('result');d.shot(out,'result');json.dump({'status':'complete','seen':sorted(seen),'steps':step},open(out+'/gate.json','w'));print('MATCH_GATE_COMPLETE',sorted(seen),flush=True);sys.exit(0)
 if 'step 1 of 6' in low:rx=r'^.*India$';seen.add('team')
 elif 'step 2 of 6' in low:rx=r'^.*Australia$';seen.add('opponent')
 elif 'step 3 of 6' in low:rx=r'^2 overs$';seen.add('overs')
 elif 'step 4 of 6' in low:
  seen.add('xi');rx=r'continue with 11' if '11 of 11 selected' in low else r'auto select a balanced'
 elif 'step 5 of 6' in low:rx=r'^Sanju Samson$';seen.add('keeper')
 elif 'step 6 of 6' in low:rx=r'^Heads$';seen.add('toss')
 elif 'what do you choose' in low:rx=r'^Bat first$'
 elif 'choose your bowler' in low or any(n['desc'].startswith('Bowler: ') and n['clickable'] for n in ns):
  rx=r'^Bowler: ';menu=False;seen.add('bowler')
 elif find(ns,r'[, ].*yet to bat|, [0-9]+ runs from [0-9]+ balls'):
  rx=r'[, ].*yet to bat|, [0-9]+ runs from [0-9]+ balls';menu=False;seen.add('batter')
 elif 'quick match' in low and 'step ' not in low:rx=r'^Quick Match$'
 elif 'striker:' in low or 'swipe to bat' in low or 'your ball:' in low or 'swipe up variation' in low:
  seen.add('live');menu=False;act='up' if 'swipe to bat' in low else 'right'
 else:
  # Opening and replacement batter rows have a full score label.
  cand=find(ns,r'.*0 runs.*0 balls|.*not out')
  if cand:rx=re.escape(cand['desc'] or cand['text']);menu=False;seen.add('batter')
 if step%10==0:d.shot(out,'step_%03d'%step)
 if rx:
  n=find(ns,rx)
  if n:activate(n,menu);print('STEP',step,rx,(n['desc'] or n['text'])[:70],flush=True)
  elif 'xi' in seen and 'step 4 of 6' in low:swipe('down')
  else:print('WAIT',step,low[:180],flush=True)
 elif act:swipe(act);print('PLAY',step,act,flush=True)
 else:print('WAIT',step,low[:180],flush=True)
 time.sleep(2)
raise RuntimeError('Step limit without result')
