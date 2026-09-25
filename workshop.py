#!/usr/bin/env python3
"""Map-local icon and model-scale workshop for Dota HQ V5."""
from __future__ import annotations
import argparse, json, os, re, shutil, struct, subprocess, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def _config():
    data={}
    for path in (ROOT/'workshop.json',ROOT/'workshop.local.json'):
        if path.is_file(): data.update(json.loads(path.read_text()))
    return data
CONFIG=_config()
def _path_setting(env, key, base):
    raw=os.environ.get(env) or CONFIG.get(key)
    if not raw:return None
    path=Path(raw).expanduser()
    return path if path.is_absolute() else base/path
def _find_game():
    configured=_path_setting('HERO_WORKSHOP_GAME_ROOT','game_root',ROOT)
    if configured:return configured
    relative=Path(CONFIG.get('map_relative_to_game','Maps/Downloads/D85 06 DotaHQv5.w3x'))
    for candidate in (ROOT,*ROOT.parents):
        if (candidate/relative).is_file():return candidate
    return ROOT.parents[2] if len(ROOT.parents)>2 else ROOT
GAME=_find_game()
PROJECT=next((p for p in (ROOT,*ROOT.parents) if p.name=='Dota Mod Project'),ROOT.parent)
MAP=_path_setting('HERO_WORKSHOP_MAP','map',ROOT) or GAME/CONFIG.get('map_relative_to_game','Maps/Downloads/D85 06 DotaHQv5.w3x')
TOOLS=ROOT/'tools'
WORK=ROOT/'.work'
HEROES=ROOT/'heroes'
UNITS=ROOT/'units'
ITEMS=ROOT/'items'
BACKUPS=ROOT/'Backups/HeroWorkshop'
ICON_ROOT=_path_setting('HERO_WORKSHOP_ICON_ROOT','icon_root',ROOT) or ROOT/'assets/icons'
WORKSPACE=_path_setting('HERO_WORKSHOP_WORKSPACE','workspace',ROOT) or PROJECT/'Workspaces/Dota2'
SKINS=_path_setting('HERO_WORKSHOP_SKINS','skins',ROOT) or ROOT/'data/SKINS_TEST_INFO.json'
SELECTION=_path_setting('HERO_WORKSHOP_SELECTION','selection',ROOT) or ROOT/'data/MODEL_SELECTION.json'
ICON_AUDIT=_path_setting('HERO_WORKSHOP_ICON_AUDIT','icon_audit',ROOT) or WORKSPACE/'Icon Audit/Heroes'
BASE_SCALES=ROOT/'base_scales.json'
BASE_SCRIPT_SCALES=ROOT/'base_script_scales.json'

def die(msg): raise SystemExit('ERROR: '+msg)
def run(*args):
    p=subprocess.run(args,text=True,capture_output=True)
    if p.returncode: die(p.stderr.strip() or ' '.join(args))
def q(s): return json.dumps(str(s),ensure_ascii=False)
def asset_folder(config_folder):
    return ICON_ROOT/config_folder.parent.name/config_folder.name
def ability_slot(config_folder,index,rawcode):
    return asset_folder(config_folder)/'slots'/f'{index:02d}_{rawcode}'

def unquote(v):
    return v[2:-1].replace('\\"','"') if v.startswith('K"') else v[1:]
def slk(path):
    x=y=1; cells={}
    for line in path.read_text(errors='replace').splitlines():
        if line == 'E': break
        if not line.startswith('C;'): continue
        mx=re.search(r';X(\d+)',line); my=re.search(r';Y(\d+)',line); mk=re.search(r';(K(?:"(?:[^"\\]|\\.)*"|[^;]*))',line)
        if mx:x=int(mx.group(1))
        if my:y=int(my.group(1))
        if mk:cells[(x,y)]=unquote(mk.group(1))
    headers={v:k[0] for k,v in cells.items() if k[1]==1}
    rows={cells[(1,row)]:row for _,row in cells if (1,row) in cells and row>1}
    return cells,headers,rows
def cell_line(path, x, y, value):
    lines=path.read_text(errors='replace').splitlines()
    # In SYLK, a row number is commonly declared only on its first cell and
    # later cells inherit it. Insert an overriding value within that row;
    # appending after `E` is ignored by Warcraft III.
    start=next((i for i,line in enumerate(lines) if re.match(rf'^C;Y{y};X1;K',line)),None)
    if start is None: raise ValueError(f'SYLK row {y} not found in {path.name}')
    end=next((i for i in range(start+1,len(lines)) if re.match(r'^C;Y\d+;X1;K',lines[i])),len(lines))
    lines.insert(end,f'C;Y{y};X{x};K'+q(value))
    path.write_text('\n'.join(lines)+'\n')
def extract():
    if not MAP.is_file():
        die(f'Карта не найдена: {MAP}. Задайте HERO_WORKSHOP_MAP или workshop.local.json.')
    WORK.mkdir(exist_ok=True); ext=TOOLS/'mpqextractone'
    if not ext.exists(): die('Не найден tools/mpqextractone. Запустите bootstrap после установки конвейера.')
    for member,name in [('Units\\UnitAbilities.slk','UnitAbilities.slk'),('units\\unitUI.slk','unitUI.slk'),('war3map.w3a','war3map.w3a'),('war3map.j','war3map.j')]:
        run(str(ext),str(MAP),member,str(WORK/name))
def hero_name(unit, comments):
    v=comments.get(unit,'').replace('Hero','').strip()
    return v or unit
def safe(s): return re.sub(r'[^A-Za-z0-9_]+','_',s).strip('_')
def all_abilities(cfg): return list(cfg.get('abilities',[]))+list(cfg.get('extra_abilities',[]))
KNOWN_ABILITY_NAMES={
    ('Abaddon','A0NS'):'Death Coil',('Abaddon','A0MG'):'Aphotic Shield',('Abaddon','A0I3'):'Curse of Avernus',('Abaddon','A0MF'):'Borrowed Time',
    ('Anti-Mage','A0NR'):'Attribute Bonus',('Anti-Mage','A0KY'):'Blink',('Anti-Mage','A022'):'Spell Shield',('Anti-Mage','AEbl'):'Counterspell',('Anti-Mage','A2WE'):'Mana Void',
    ('Dragon Knight','A03G'):'Breathe Fire',('Dragon Knight','A03F'):'Dragon Tail',('Dragon Knight','A0NR'):'Attribute Bonus',('Dragon Knight','A2AI'):'Elder Dragon Form',('Dragon Knight','A0CL'):'Dragon Blood',('Dragon Knight','A3FF'):'Dragon Form',
    ('Omniknight','A08N'):'Purification',('Omniknight','A08V'):'Repel',('Omniknight','A0ER'):'Degen Aura',('Omniknight','A06A'):'Guardian Angel',('Omniknight','A0NR'):'Attribute Bonus',
}
def _audit_dir(hero):
    key=re.sub(r'[^a-z0-9]','',hero.lower())
    return next((p for p in ICON_AUDIT.iterdir() if re.sub(r'[^a-z0-9]','',p.name.lower())==key),None) if ICON_AUDIT.exists() else None
def _pretty_icon_name(stem, hero):
    s=re.sub(r'^(BTN|DISBTN)','',stem)
    s=re.sub(r'^(Hero|INV|Passive|Ability)[-_]','',s)
    s=re.sub(r'[^A-Za-z0-9]+',' ',s)
    s=re.sub(r'([a-z])([A-Z])',r'\1 \2',s).strip()
    return s or 'Способность'
def ability_label(hero, code, index, icon_names):
    if (hero,code) in KNOWN_ABILITY_NAMES: return KNOWN_ABILITY_NAMES[(hero,code)]
    if code=='AInv': return 'Inventory'
    if code=='A0NR': return 'Attribute Bonus'
    return _pretty_icon_name(icon_names[index],hero) if index < len(icon_names) else f'Ability {index+1}'
def ability_icon_names(hero):
    d=_audit_dir(hero)
    if not d:return []
    out=[]
    for p in sorted(d.glob('**/ReplaceableTextures/CommandButtons/BTN*.png')):
        n=p.stem[3:]
        if n.lower().startswith(('hero','upgrade','inv_')): continue
        if n not in out: out.append(n)
    return out
def add_ability_labels(cfg):
    names=ability_icon_names(cfg['hero']); active=0
    for a in all_abilities(cfg):
        if a.get('base_ability')=='A0NR': a['label']='Attribute Bonus'
        elif not a.get('label') or a['label'].startswith(('Ability ','Способность ')):
            a['label']=ability_label(cfg['hero'],a['base_ability'],active,names); active+=1
def bootstrap():
    extract(); ab,h,r=slk(WORK/'UnitAbilities.slk')
    skins=json.loads(SKINS.read_text()) if SKINS.exists() else {'primary_models':{}}
    ids=set(skins.get('primary_models',{}))
    names={}
    if SELECTION.exists():
        for entry in json.loads(SELECTION.read_text()):
            if entry.get('rawcode'):
                ids.add(entry['rawcode']); names[entry['rawcode']]=entry.get('hero',entry['rawcode'])
    # Include any map unit whose comment labels it a hero.
    for uid,row in r.items():
        if 'hero' in str(ab.get((h.get('comment(s)',0),row),'')).lower(): ids.add(uid)
    HEROES.mkdir(exist_ok=True)
    bases=json.loads(BASE_SCALES.read_text()) if BASE_SCALES.exists() else {}
    ui,uih,uirows=slk(WORK/'unitUI.slk')
    for uid in sorted(ids):
        row=r.get(uid)
        name=names.get(uid) or (hero_name(uid,{k:ab.get((h.get('comment(s)',0),v),'') for k,v in r.items()}) if row else uid)
        abilities=[]
        lists=[(kind,ab.get((h.get(kind,0),row),'')) for kind in ('heroAbilList','abilList')] if row else []
        for kind,raw in lists:
            for code in filter(None,(a.strip() for a in raw.split(','))):
                if code not in [z['base_ability'] for z in abilities]: abilities.append({'base_ability':code,'source':kind})
        folder=HEROES/f'{safe(name)}__{uid}'; folder.mkdir(exist_ok=True)
        cfg=folder/'hero.json'
        if cfg.exists():
            old=json.loads(cfg.read_text()); old['hero']=name; old['unit_rawcode']=uid
            old.setdefault('primary_model_scale',1.0); old.setdefault('alternative_model_scale',1.0)
            known={x['base_ability'] for x in old.get('abilities',[])}
            old['abilities'].extend(x for x in abilities if x['base_ability'] not in known)
            old.setdefault('extra_abilities',[])
            old['base_scale']=bases.get(uid,old.get('base_scale',float(ui.get((uih.get('scale',0),uirows.get(uid,0)),'1'))))
            cfg.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n')
        else: cfg.write_text(json.dumps({'hero':name,'unit_rawcode':uid,'primary_model_scale':1.0,'alternative_model_scale':1.0,'base_scale':bases.get(uid,float(ui.get((uih.get('scale',0),uirows.get(uid,0)),'1'))),'abilities':abilities,'extra_abilities':[]},ensure_ascii=False,indent=2)+'\n')
        active=json.loads(cfg.read_text())
        add_ability_labels(active)
        cfg.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n')
        for n,a in enumerate(all_abilities(active),1):
            ability_slot(folder,n,a['base_ability']).mkdir(parents=True,exist_ok=True)
    print(f'Created/updated {len(ids)} hero folders in {HEROES}')
def items_bootstrap():
    WORK.mkdir(exist_ok=True); run(str(TOOLS/'mpqextractone'),str(MAP),'units\\ItemData.slk',str(WORK/'ItemData.slk'))
    data,h,rows=slk(WORK/'ItemData.slk'); ITEMS.mkdir(exist_ok=True); made=0
    for raw,row in rows.items():
        abilities=[x.strip() for x in data.get((h.get('abilList',0),row),'').split(',') if x.strip()]
        if not abilities: continue
        name=data.get((h.get('comment',0),row),raw)
        folder=ITEMS/f'{safe(name)}__{raw}'; folder.mkdir(exist_ok=True); cfg=folder/'item.json'
        if not cfg.exists(): cfg.write_text(json.dumps({'item':name,'item_rawcode':raw,'abilities':[{'base_ability':a,'source':'item'} for a in abilities]},ensure_ascii=False,indent=2)+'\n')
        item=json.loads(cfg.read_text())
        for n,a in enumerate(item['abilities'],1):
            ability_slot(folder,n,a['base_ability']).mkdir(parents=True,exist_ok=True)
        made+=1
    print(f'Created/updated {made} item folders in {ITEMS}')
def configs(name):
    found=[]
    for root in (HEROES,UNITS):
      for p in root.glob('*/hero.json'):
        d=json.loads(p.read_text())
        if name.lower() in (d['hero'].lower(),d['unit_rawcode'].lower()) or name.lower()==p.parent.name.lower(): found.append((p,d))
    return found
def show(name):
    found=configs(name)
    if not found: die('Герой не найден. Сначала: python3 workshop.py bootstrap')
    for p,d in found:
        print(f"{d['hero']} [{d['unit_rawcode']}]  primary={d.get('primary_model_scale',1)}  alternative={d.get('alternative_model_scale',1)}\n{p.parent}")
        for n,a in enumerate(all_abilities(d),1): print(f"  {n:02}: {a['base_ability']} ({a['source']})")
def four(s): return struct.unpack('<I',s.encode('latin1'))[0]
def fourstr(n): return struct.pack('<I',n).decode('latin1')
def parse_w3a(p):
    b=p.read_bytes()
    # A small parser keeps the binary object-data format explicit and reliable.
    class R:
        def __init__(self): self.o=0
        def u(self): v=struct.unpack_from('<I',b,self.o)[0];self.o+=4;return v
        def st(self): j=b.index(b'\0',self.o);v=b[self.o:j].decode('latin1');self.o=j+1;return v
        def rec(self):
            old,new,n=self.u(),self.u(),self.u();m=[]
            for _ in range(n):
                field,typ,lev,ptr=self.u(),self.u(),self.u(),self.u()
                if typ==3: val=self.st()
                elif typ in (1,2): val=struct.unpack_from('<f',b,self.o)[0];self.o+=4
                else: val=self.u()
                m.append([field,typ,lev,ptr,val,self.u()])
            return [old,new,m]
    z=R();ver=z.u(); original=[z.rec() for _ in range(z.u())]; custom=[z.rec() for _ in range(z.u())]
    return ver,original,custom
def write_w3a(p,data):
    ver,orig,custom=data; out=bytearray(struct.pack('<II',ver,len(orig)))
    for group in (orig,custom):
        if group is custom: out.extend(struct.pack('<I',len(custom)))
        for old,new,mods in group:
            out.extend(struct.pack('<III',old,new,len(mods)))
            for f,t,l,ptr,v,end in mods:
                out.extend(struct.pack('<IIII',f,t,l,ptr));out.extend((str(v).encode('latin1')+b'\0') if t==3 else (struct.pack('<f',v) if t in (1,2) else struct.pack('<I',v)));out.extend(struct.pack('<I',end))
    p.write_bytes(out)
def add(mapfile,disk,member): run(str(TOOLS/'mpqadd_expand'),str(mapfile),str(disk),member)
def prepared_blp(slot, kind):
    """Prefer the editable PNG, convert it locally, otherwise use a supplied BLP."""
    png=slot/(kind+'.png'); blp=slot/(kind+'.blp')
    if png.exists():
        out=WORK/(slot.name+'_'+kind+'.blp')
        run('/usr/bin/env','python3',str(ROOT/'png_to_blp.py'),str(png),str(out))
        return out
    return blp if blp.exists() else None
def clone_code(used):
    alphabet='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    for i in range(36**3):
        n=i; tail=''
        for _ in range(3): tail=alphabet[n%36]+tail;n//=36
        x='W'+tail
        if four(x) not in used:return x
    die('Закончились rawcode для копий способностей')
def apply_one(folder,cfg):
    extract(); ab,h,rows=slk(WORK/'UnitAbilities.slk'); ui,uh,urows=slk(WORK/'unitUI.slk')
    uid=cfg['unit_rawcode']; row=rows.get(uid)
    if not row: die(f'{uid} отсутствует в UnitAbilities.slk')
    ver,orig,custom=parse_w3a(WORK/'war3map.w3a'); used={x[1] for x in orig+custom}; statefile=folder/'state.json'; state=json.loads(statefile.read_text()) if statefile.exists() else {'clones':{}}
    for n,a in enumerate(all_abilities(cfg),1):
        slot=ability_slot(folder,n,a['base_ability']); normal=prepared_blp(slot,'normal')
        if not normal: continue
        key=a['base_ability']; code=state['clones'].get(key)
        art=f'ReplaceableTextures\\CommandButtons\\BTN_HW_{uid}_{n:02d}.blp'
        if a.get('source')=='triggered':
            # A triggered spell is not in the unit list. Override its map-local
            # ability object directly; this is limited to this map.
            found=next((r for r in orig if r[0]==four(key) and r[1]==four(key)),None)
            if not found:
                found=[four(key),four(key),[]]; orig.append(found)
            found[2]=[m for m in found[2] if m[0]!=four('aart')]+[[four('aart'),3,0,0,art,0]]
            code=None
        elif not code:
            code=clone_code(used);used.add(four(code));state['clones'][key]=code
            orig.append([four(key),four(code),[[four('aart'),3,0,0,art,0]]])
        else:
            found=next((r for r in orig+custom if r[1]==four(code)),None)
            if found:
                found[2]=[m for m in found[2] if m[0]!=four('aart')]+[[four('aart'),3,0,0,art,0]]
        if code:
            for field in ('heroAbilList','abilList'):
                old=ab.get((h.get(field,0),row),''); new=','.join(code if x==key else x for x in old.split(','));
                if new!=old: cell_line(WORK/'UnitAbilities.slk',h[field],row,new)
        add(MAP,normal,f'ReplaceableTextures\\CommandButtons\\BTN_HW_{uid}_{n:02d}.blp')
        disabled=prepared_blp(slot,'disabled')
        if disabled: add(MAP,disabled,f'ReplaceableTextures\\CommandButtonsDisabled\\DISBTN_HW_{uid}_{n:02d}.blp')
    # X37 is unitUI.slk:modelScale. X22 (`scale`) and runtime P3/SetUnitScale
    # also resize Warcraft selection UI, so model tuning must not touch them.
    apply_model_scale(cfg, ui, uh, urows)
    if uid=='Hlgr' and restore_dk_legacy_scale(WORK/'war3map.j',ui,uh,urows):
        add(MAP,WORK/'war3map.j','war3map.j')
    (folder/'hero.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n')
    write_w3a(WORK/'war3map.w3a',(ver,orig,custom)); statefile.write_text(json.dumps(state,indent=2)+'\n')
    for disk,member in [(WORK/'UnitAbilities.slk','Units\\UnitAbilities.slk'),(WORK/'unitUI.slk','units\\unitUI.slk'),(WORK/'war3map.w3a','war3map.w3a')]:add(MAP,disk,member)
def model_scale_targets(cfg):
    entries=json.loads(SELECTION.read_text()) if SELECTION.exists() else []
    selected=next((x for x in entries if x.get('rawcode')==cfg['unit_rawcode']),{})
    targets=[(cfg['unit_rawcode'],'primary_model_scale',None),
             (selected.get('alternative_rawcode'),'alternative_model_scale',None)]
    # Summons, transformations and other dependent units are explicit entries
    # in each hero config.  They deliberately use their own persistent bases.
    targets.extend((x.get('rawcode'),'related_model_scale',x) for x in cfg.get('related_models',[]))
    return targets
def apply_model_scale(cfg, cells, headers, rows):
    """Apply absolute model scales to unitUI.slk:modelScale (X37)."""
    col=headers.get('modelScale')
    if not col: die('В unitUI.slk отсутствует колонка modelScale')
    for raw,key,related in model_scale_targets(cfg):
        if not raw: continue
        row=rows.get(raw)
        if not row:
            print(f'WARN: modelScale row missing for {cfg["hero"]} [{raw}]')
            continue
        current=float(cells.get((col,row),'1') or '1')
        base_key=key+'_base'
        if related is not None:
            factor=float(related.get('model_scale',1.0))
        else:
            factor=float(cfg.get(key,1.0))
        if not 0.01 <= factor <= 20.0:
            die(f'{cfg["hero"]}: {key} должен быть в диапазоне 0.01–20')
        # The UI value is absolute: entering 1.20 writes 1.20.  It never
        # multiplies a prior value or an original baseline.
        target=f'{factor:.6f}'
        cell_line(WORK/'unitUI.slk',col,row,target)
        cells[(col,row)]=target
def restore_dk_legacy_scale(path, cells, headers, rows):
    """Undo Dragon Knight's old multiplier on P3 and unitUI scale X22."""
    if not BASE_SCRIPT_SCALES.exists(): return False
    base=float(json.loads(BASE_SCRIPT_SCALES.read_text()).get('Hlgr',1.0))
    slot_base=float(json.loads(BASE_SCALES.read_text()).get('Hlgr',1.0)) if BASE_SCALES.exists() else 1.5
    cfg=next((json.loads(p.read_text()) for p in HEROES.glob('*/hero.json') if json.loads(p.read_text()).get('unit_rawcode')=='Hlgr'),{})
    legacy=float(cfg.get('model_scale',1.0))
    if abs(legacy-1.0)<1e-6: return False
    source=path.read_text(errors='replace')
    changed=False
    row=rows.get('Hlgr'); col=headers.get('scale')
    if row and col:
        current_unit_scale=float(cells.get((col,row),'1') or '1')
        if abs(current_unit_scale-slot_base*legacy)<1e-4:
            value=f'{slot_base:.6f}'
            cell_line(WORK/'unitUI.slk',col,row,value)
            cells[(col,row)]=value
            changed=True
        elif abs(current_unit_scale-slot_base)>1e-4:
            print(f'WARN: keeping Dragon Knight unit scale {current_unit_scale:g}; it does not match legacy multiplier')
    pattern=r"(call P3\(\d+,'Hlgr','[^']+','[^']+',\"[^\"]*\",)([.0-9]+)(,\d+\))"
    match=re.search(pattern,source)
    if not match:
        print('WARN: Dragon Knight P3 scale entry not found')
        if changed: path.write_text(source)
        return changed
    current=float(match.group(2))
    if abs(current-base*legacy)>1e-4:
        print(f'WARN: keeping Dragon Knight P3 value {current:g}; it no longer matches legacy multiplier')
    else:
        source=source[:match.start(2)]+f'{base:.6f}'+source[match.end(2):]
        changed=True
    if changed: path.write_text(source)
    return changed
def apply(name):
    found=[]
    for root in (HEROES,UNITS):
      for p in root.glob('*/hero.json'):
        d=json.loads(p.read_text())
        if name=='all' or name.lower() in (d['hero'].lower(),d['unit_rawcode'].lower(),p.parent.name.lower()):
            found.append((p.parent,d))
    if not found: die('Нет подходящего героя')
    BACKUPS.mkdir(parents=True,exist_ok=True); backup=BACKUPS/(MAP.stem+' '+time.strftime('%Y%m%d-%H%M%S')+'.w3x');shutil.copy2(MAP,backup)
    for folder,cfg in found: apply_one(folder,cfg); print('Applied:',cfg['hero'])
    # Model scaling is deliberately separate from icon application.  The map's
    # existing P3 table resizes the base Warcraft unit, while the visible Dota
    # model is an independent effect; rewriting that table here is misleading
    # and must not be triggered by an ordinary icon save.
    print('Backup:',backup)

def units_bootstrap():
    """Create editable configs for non-hero units actually created by this map."""
    extract(); ab,h,rows=slk(WORK/'UnitAbilities.slk'); ui,uh,urows=slk(WORK/'unitUI.slk')
    source=(WORK/'war3map.j').read_text(errors='replace')
    # P3 is the map's custom-model table: P3(index, 'unitRawcode', ... scale,...).
    p3=dict(re.findall(r"call P3\([^,]+,'([^']{4})','[^']*','[^']*',\"[^\"]*\",([.0-9]+),",source))
    # This includes lane creeps, neutral creeps, summons and buildings the map
    # instantiates.  It intentionally excludes unused base-game units.
    created=set(re.findall(r"CreateUnit(?:AtLoc)?\([^\n]*?'([^']{4})'",source))
    created.update(p3)
    hero_ids={json.loads(p.read_text()).get('unit_rawcode') for p in HEROES.glob('*/hero.json')}
    UNITS.mkdir(exist_ok=True); made=0
    for uid in sorted(created):
        if uid in hero_ids or uid not in rows: continue
        row=rows[uid]
        comment=ab.get((h.get('comment(s)',0),row),'').strip()
        name=comment or uid
        abilities=[]
        for kind in ('heroAbilList','abilList'):
            for code in filter(None,(x.strip() for x in ab.get((h.get(kind,0),row),'').split(','))):
                if code not in [a['base_ability'] for a in abilities]: abilities.append({'base_ability':code,'source':kind})
        folder=UNITS/f'{safe(name)}__{uid}'; folder.mkdir(exist_ok=True)
        config=folder/'hero.json'
        if config.exists():
            data=json.loads(config.read_text()); data['hero']=name; data['unit_rawcode']=uid; data['is_unit']=True
        else:
            default_scale=float(p3.get(uid,ui.get((uh.get('modelScale',0),urows.get(uid,0)),'1') or '1'))
            data={'hero':name,'unit_rawcode':uid,'is_unit':True,'primary_model_scale':default_scale,'alternative_model_scale':1.0,'abilities':abilities,'extra_abilities':[],'related_models':[]}
        config.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
        for n,a in enumerate(all_abilities(data),1):
            ability_slot(folder,n,a['base_ability']).mkdir(parents=True,exist_ok=True)
        made+=1
    print(f'Created/updated {made} changed unit configs in {UNITS}')
def apply_item(name):
    matches=[]
    for p in ITEMS.glob('*/item.json'):
        d=json.loads(p.read_text())
        if name=='all' or name.lower() in (d['item'].lower(),d['item_rawcode'].lower(),p.parent.name.lower()): matches.append((p.parent,d))
    if not matches: die('Предмет не найден')
    BACKUPS.mkdir(parents=True,exist_ok=True); backup=BACKUPS/(MAP.stem+' items '+time.strftime('%Y%m%d-%H%M%S')+'.w3x');shutil.copy2(MAP,backup)
    WORK.mkdir(exist_ok=True); run(str(TOOLS/'mpqextractone'),str(MAP),'units\\ItemData.slk',str(WORK/'ItemData.slk')); run(str(TOOLS/'mpqextractone'),str(MAP),'war3map.w3a',str(WORK/'war3map.w3a'))
    data,h,rows=slk(WORK/'ItemData.slk'); ver,orig,custom=parse_w3a(WORK/'war3map.w3a'); used={r[1] for r in orig+custom}
    for folder,cfg in matches:
        row=rows.get(cfg['item_rawcode']);
        if not row: continue
        statefile=folder/'state.json'; state=json.loads(statefile.read_text()) if statefile.exists() else {'clones':{}}
        for n,a in enumerate(cfg['abilities'],1):
            slot=ability_slot(folder,n,a['base_ability']); normal=prepared_blp(slot,'normal')
            if not normal: continue
            key=a['base_ability']; code=state['clones'].get(key); art=f'ReplaceableTextures\\CommandButtons\\BTN_HW_ITEM_{cfg["item_rawcode"]}_{n:02d}.blp'
            if not code:
                code=clone_code(used);used.add(four(code));state['clones'][key]=code;orig.append([four(key),four(code),[[four('aart'),3,0,0,art,0]]])
            old=data.get((h['abilList'],row),''); cell_line(WORK/'ItemData.slk',h['abilList'],row,','.join(code if x==key else x for x in old.split(',')))
            add(MAP,normal,f'ReplaceableTextures\\CommandButtons\\BTN_HW_ITEM_{cfg["item_rawcode"]}_{n:02d}.blp')
            disabled=prepared_blp(slot,'disabled')
            if disabled: add(MAP,disabled,f'ReplaceableTextures\\CommandButtonsDisabled\\DISBTN_HW_ITEM_{cfg["item_rawcode"]}_{n:02d}.blp')
        statefile.write_text(json.dumps(state,indent=2)+'\n')
        print('Applied item:',cfg['item'])
    write_w3a(WORK/'war3map.w3a',(ver,orig,custom));add(MAP,WORK/'ItemData.slk','units\\ItemData.slk');add(MAP,WORK/'war3map.w3a','war3map.w3a');print('Backup:',backup)
def doctor():
    checks={
        'map':MAP.is_file(),
        'mpqextractone':(TOOLS/'mpqextractone').is_file(),
        'mpqadd_expand':(TOOLS/'mpqadd_expand').is_file(),
        'icon_root':ICON_ROOT.is_dir(),
    }
    print('Hero Workshop root:',ROOT)
    print('Warcraft root:',GAME)
    print('Target map:',MAP)
    print('Icon root:',ICON_ROOT)
    print('Workspace (optional):',WORKSPACE)
    for name,ok in checks.items():print(('OK   ' if ok else 'MISS ')+name)
    if not all(checks.values()):raise SystemExit(2)
def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True)
    sub.add_parser('doctor');sub.add_parser('bootstrap');sub.add_parser('items-bootstrap');sub.add_parser('units-bootstrap'); s=sub.add_parser('show');s.add_argument('hero');a=sub.add_parser('apply');a.add_argument('hero'); i=sub.add_parser('apply-item');i.add_argument('item')
    x=ap.parse_args(); {'doctor':doctor,'bootstrap':bootstrap,'items-bootstrap':items_bootstrap,'units-bootstrap':units_bootstrap,'show':lambda:show(x.hero),'apply':lambda:apply(x.hero),'apply-item':lambda:apply_item(x.item)}[x.cmd]()
if __name__=='__main__': main()
