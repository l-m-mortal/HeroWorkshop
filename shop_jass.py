"""JASS block that draws a single Dota 2-style shop window (Warcraft III 1.31+).

Injected into war3map.j by `map_fix.py shop-ui`. Pure JASS, no vJASS/Lua (variant
A of docs/SHOP_UI_PLAN.md). Modelled on cooldown_jass.py: a GLOBALS block, a
FUNCTIONS block spliced in front of `main`, and one call appended to the end of
`main`. Coexists with the HW_COOLDOWN_* block cooldown_jass.py injects (distinct
marker comments, distinct globals/functions, both spliced the same way).

Design (see docs/SHOP_UI_PLAN.md §3, variant A, and docs/SHOP_UI_NOTES.md):
* One hidden panel (BACKDROP) is built once, 1s after map start, with up to
  HW_SHOP_SLOTS=24 reusable icon slots (BACKDROP with BlzFrameSetTexture +
  a BUTTON on top for clicks + a TEXT price label) and one GLUEBUTTON tab per
  shop category.
* "-shop" chat command (registered for every player slot) and a small toggle
  button both flip visibility of the SAME shared panel, but only on the
  clicking player's own client (`if GetLocalPlayer() == p then ... endif`
  around BlzFrameSetVisible only -- no handle is created there, so this
  cannot desync). This gives each player their own open/closed state.
* Switching category rewrites the shared slot textures/prices/tooltips and the
  frame->item hashtable UNCONDITIONALLY (no GetLocalPlayer guard), because the
  buy handler reads that hashtable and must resolve to the same item on every
  client. Trade-off: the category page is shared by everyone currently
  looking at the window (documented in SHOP_UI_NOTES.md) -- open/closed is
  personal, the page shown is not.
* Buying does not replay the map's native Sellunits/order-id purchase path
  (unverified without a live client, see docs/SHOP_UI_PLAN.md §6) -- it uses
  the safe fallback the task allows: check gold, GetPlayerState/SetPlayerState
  to pay, UnitAddItemById on the player's first hero (GroupEnumUnitsOfPlayer +
  IsUnitType UNIT_TYPE_HERO). No courier/fountain-drop fallback is implemented
  (documented limitation).
"""

import workshop

HW_SHOP_SLOTS = 24
HW_SHOP_COLS = 6

GLOBALS = """// HW_SHOP_GLOBALS_BEGIN
constant integer HW_SHOP_SLOTS=24
constant integer HW_SHOP_COLS=6
integer array HW_shopUnitId
integer array HW_shopItemId
integer array HW_shopCost
string array HW_shopIcon
string array HW_shopName
string array HW_shopCatName
integer array HW_shopCatSize
integer HW_shopCatCount=0
integer HW_shopCurCat=0
boolean HW_shopLocalOpen=false
framehandle HW_shopPanel=null
framehandle HW_shopTitle=null
framehandle HW_shopToggleBtn=null
framehandle HW_shopCloseBtn=null
framehandle array HW_shopTabBtn
framehandle array HW_shopSlotBtn
framehandle array HW_shopSlotIcon
framehandle array HW_shopSlotPrice
framehandle array HW_shopSlotTip
hashtable HW_shopSlotHT=null
hashtable HW_shopTabHT=null
trigger HW_shopSlotTrig=null
trigger HW_shopTabTrig=null
trigger HW_shopToggleTrig=null
trigger HW_shopCloseTrig=null
trigger HW_shopChatTrig=null
timer HW_shopTimer=null
// HW_SHOP_GLOBALS_END"""

FUNCTIONS = """// HW_SHOP_BEGIN
function HW_ShopFindHero takes player p returns unit
    local group g=CreateGroup()
    local unit u
    local unit found=null
    call GroupEnumUnitsOfPlayer(g,p,null)
    loop
        set u=FirstOfGroup(g)
        exitwhen u==null
        call GroupRemoveUnit(g,u)
        if found==null and IsUnitType(u,UNIT_TYPE_HERO) then
            set found=u
        endif
    endloop
    call DestroyGroup(g)
    set g=null
    set u=null
    return found
endfunction
function HW_ShopBuy takes player p, integer idx returns nothing
    local integer cost
    local integer itemId
    local unit hero
    local item it
    if idx<0 then
        return
    endif
    set cost=HW_shopCost[idx]
    set itemId=HW_shopItemId[idx]
    if itemId==0 then
        return
    endif
    if GetPlayerState(p,PLAYER_STATE_RESOURCE_GOLD)<cost then
        call DisplayTextToPlayer(p,0,0,"|cffffcc00HW Shop:|r not enough gold ("+I2S(cost)+"): "+HW_shopName[idx])
        return
    endif
    set hero=HW_ShopFindHero(p)
    if hero==null then
        call DisplayTextToPlayer(p,0,0,"|cffffcc00HW Shop:|r no hero found, purchase cancelled")
        return
    endif
    call SetPlayerState(p,PLAYER_STATE_RESOURCE_GOLD,GetPlayerState(p,PLAYER_STATE_RESOURCE_GOLD)-cost)
    set it=UnitAddItemById(hero,itemId)
    if it==null then
        call SetPlayerState(p,PLAYER_STATE_RESOURCE_GOLD,GetPlayerState(p,PLAYER_STATE_RESOURCE_GOLD)+cost)
        call DisplayTextToPlayer(p,0,0,"|cffffcc00HW Shop:|r inventory full, gold refunded: "+HW_shopName[idx])
    else
        call DisplayTextToPlayer(p,0,0,"|cff60ff60HW Shop:|r bought "+HW_shopName[idx]+" ("+I2S(cost)+"g)")
    endif
    set hero=null
    set it=null
endfunction
function HW_ShopShowCat takes integer cat returns nothing
    local integer i=0
    local integer n
    local integer idx
    if cat<0 or cat>=HW_shopCatCount then
        return
    endif
    set HW_shopCurCat=cat
    set n=HW_shopCatSize[cat]
    loop
        exitwhen i>=HW_SHOP_SLOTS
        if i<n then
            set idx=cat*HW_SHOP_SLOTS+i
            call BlzFrameSetTexture(HW_shopSlotIcon[i],HW_shopIcon[idx],0,true)
            call BlzFrameSetText(HW_shopSlotPrice[i],I2S(HW_shopCost[idx]))
            call BlzFrameSetText(HW_shopSlotTip[i],HW_shopName[idx]+"|n|cffffcc00"+I2S(HW_shopCost[idx])+" gold|r")
            call SaveInteger(HW_shopSlotHT,GetHandleId(HW_shopSlotBtn[i]),0,idx)
            call BlzFrameSetVisible(HW_shopSlotBtn[i],true)
            call BlzFrameSetVisible(HW_shopSlotIcon[i],true)
            call BlzFrameSetVisible(HW_shopSlotPrice[i],true)
        else
            call BlzFrameSetVisible(HW_shopSlotBtn[i],false)
            call BlzFrameSetVisible(HW_shopSlotIcon[i],false)
            call BlzFrameSetVisible(HW_shopSlotPrice[i],false)
            call RemoveSavedInteger(HW_shopSlotHT,GetHandleId(HW_shopSlotBtn[i]),0)
        endif
        set i=i+1
    endloop
endfunction
function HW_ShopToggle takes player p returns nothing
    if GetLocalPlayer()==p then
        set HW_shopLocalOpen=not HW_shopLocalOpen
        call BlzFrameSetVisible(HW_shopPanel,HW_shopLocalOpen)
    endif
endfunction
function HW_ShopClose takes player p returns nothing
    if GetLocalPlayer()==p then
        set HW_shopLocalOpen=false
        call BlzFrameSetVisible(HW_shopPanel,false)
    endif
endfunction
function HW_ShopSlotClick takes nothing returns nothing
    local framehandle f=BlzGetTriggerFrame()
    local player p=GetTriggerPlayer()
    local integer idx
    if HaveSavedInteger(HW_shopSlotHT,GetHandleId(f),0) then
        set idx=LoadInteger(HW_shopSlotHT,GetHandleId(f),0)
        call HW_ShopBuy(p,idx)
    endif
    call BlzFrameSetEnable(f,false)
    call BlzFrameSetEnable(f,true)
    set f=null
endfunction
function HW_ShopTabClick takes nothing returns nothing
    local framehandle f=BlzGetTriggerFrame()
    local integer cat=LoadInteger(HW_shopTabHT,GetHandleId(f),0)
    call HW_ShopShowCat(cat)
    call BlzFrameSetEnable(f,false)
    call BlzFrameSetEnable(f,true)
    set f=null
endfunction
function HW_ShopToggleClick takes nothing returns nothing
    local framehandle f=BlzGetTriggerFrame()
    call HW_ShopToggle(GetTriggerPlayer())
    call BlzFrameSetEnable(f,false)
    call BlzFrameSetEnable(f,true)
    set f=null
endfunction
function HW_ShopCloseClick takes nothing returns nothing
    local framehandle f=BlzGetTriggerFrame()
    call HW_ShopClose(GetTriggerPlayer())
    call BlzFrameSetEnable(f,false)
    call BlzFrameSetEnable(f,true)
    set f=null
endfunction
function HW_ShopChat takes nothing returns nothing
    call HW_ShopToggle(GetTriggerPlayer())
endfunction
function HW_ShopBuild takes nothing returns nothing
    local framehandle ui=BlzGetOriginFrame(ORIGIN_FRAME_GAME_UI,0)
    local integer i=0
    local integer col
    local integer row
    local real tabw
    call HW_ShopDataInit()
    set HW_shopSlotHT=InitHashtable()
    set HW_shopTabHT=InitHashtable()
    set HW_shopPanel=BlzCreateFrameByType("BACKDROP","HWShopPanel",ui,"",0)
    call BlzFrameSetAbsPoint(HW_shopPanel,FRAMEPOINT_TOPLEFT,0.15,0.56)
    call BlzFrameSetSize(HW_shopPanel,0.50,0.42)
    call BlzFrameSetVisible(HW_shopPanel,false)
    set HW_shopTitle=BlzCreateFrameByType("TEXT","HWShopTitle",HW_shopPanel,"",0)
    call BlzFrameSetPoint(HW_shopTitle,FRAMEPOINT_TOP,HW_shopPanel,FRAMEPOINT_TOP,0,-0.012)
    call BlzFrameSetSize(HW_shopTitle,0.46,0.02)
    call BlzFrameSetTextAlignment(HW_shopTitle,TEXT_JUSTIFY_MIDDLE,TEXT_JUSTIFY_CENTER)
    call BlzFrameSetText(HW_shopTitle,"HW Shop (прототип)")
    set HW_shopCloseBtn=BlzCreateFrameByType("GLUEBUTTON","HWShopClose",HW_shopPanel,"",0)
    call BlzFrameSetPoint(HW_shopCloseBtn,FRAMEPOINT_TOPRIGHT,HW_shopPanel,FRAMEPOINT_TOPRIGHT,-0.008,-0.008)
    call BlzFrameSetSize(HW_shopCloseBtn,0.022,0.022)
    call BlzFrameSetText(HW_shopCloseBtn,"X")
    set HW_shopCloseTrig=CreateTrigger()
    call BlzTriggerRegisterFrameEvent(HW_shopCloseTrig,HW_shopCloseBtn,FRAMEEVENT_CONTROL_CLICK)
    call TriggerAddAction(HW_shopCloseTrig,function HW_ShopCloseClick)
    set HW_shopToggleBtn=BlzCreateFrameByType("GLUEBUTTON","HWShopToggle",ui,"",0)
    call BlzFrameSetAbsPoint(HW_shopToggleBtn,FRAMEPOINT_BOTTOMRIGHT,0.79,0.030)
    call BlzFrameSetSize(HW_shopToggleBtn,0.05,0.026)
    call BlzFrameSetText(HW_shopToggleBtn,"Shop")
    set HW_shopToggleTrig=CreateTrigger()
    call BlzTriggerRegisterFrameEvent(HW_shopToggleTrig,HW_shopToggleBtn,FRAMEEVENT_CONTROL_CLICK)
    call TriggerAddAction(HW_shopToggleTrig,function HW_ShopToggleClick)
    set HW_shopTabTrig=CreateTrigger()
    if HW_shopCatCount>0 then
        set tabw=0.48/I2R(HW_shopCatCount)
    else
        set tabw=0.48
    endif
    loop
        exitwhen i>=HW_shopCatCount
        set HW_shopTabBtn[i]=BlzCreateFrameByType("GLUEBUTTON","HWShopTab",HW_shopPanel,"",0)
        call BlzFrameSetPoint(HW_shopTabBtn[i],FRAMEPOINT_TOPLEFT,HW_shopPanel,FRAMEPOINT_TOPLEFT,0.01+I2R(i)*tabw,-0.045)
        call BlzFrameSetSize(HW_shopTabBtn[i],tabw-0.002,0.026)
        call BlzFrameSetScale(HW_shopTabBtn[i],0.75)
        call BlzFrameSetText(HW_shopTabBtn[i],HW_shopCatName[i])
        call BlzTriggerRegisterFrameEvent(HW_shopTabTrig,HW_shopTabBtn[i],FRAMEEVENT_CONTROL_CLICK)
        call SaveInteger(HW_shopTabHT,GetHandleId(HW_shopTabBtn[i]),0,i)
        set i=i+1
    endloop
    call TriggerAddAction(HW_shopTabTrig,function HW_ShopTabClick)
    set HW_shopSlotTrig=CreateTrigger()
    set i=0
    loop
        exitwhen i>=HW_SHOP_SLOTS
        set col=i-(i/HW_SHOP_COLS)*HW_SHOP_COLS
        set row=i/HW_SHOP_COLS
        set HW_shopSlotIcon[i]=BlzCreateFrameByType("BACKDROP","HWShopIcon",HW_shopPanel,"",0)
        call BlzFrameSetPoint(HW_shopSlotIcon[i],FRAMEPOINT_TOPLEFT,HW_shopPanel,FRAMEPOINT_TOPLEFT,0.02+I2R(col)*0.076,-0.085-I2R(row)*0.086)
        call BlzFrameSetSize(HW_shopSlotIcon[i],0.058,0.058)
        set HW_shopSlotBtn[i]=BlzCreateFrameByType("BUTTON","HWShopSlot",HW_shopPanel,"",0)
        call BlzFrameSetPoint(HW_shopSlotBtn[i],FRAMEPOINT_TOPLEFT,HW_shopSlotIcon[i],FRAMEPOINT_TOPLEFT,0,0)
        call BlzFrameSetSize(HW_shopSlotBtn[i],0.058,0.058)
        set HW_shopSlotPrice[i]=BlzCreateFrameByType("TEXT","HWShopPrice",HW_shopPanel,"",0)
        call BlzFrameSetPoint(HW_shopSlotPrice[i],FRAMEPOINT_TOP,HW_shopSlotIcon[i],FRAMEPOINT_BOTTOM,0,-0.002)
        call BlzFrameSetSize(HW_shopSlotPrice[i],0.058,0.014)
        call BlzFrameSetScale(HW_shopSlotPrice[i],0.7)
        call BlzFrameSetTextAlignment(HW_shopSlotPrice[i],TEXT_JUSTIFY_TOP,TEXT_JUSTIFY_CENTER)
        set HW_shopSlotTip[i]=BlzCreateFrameByType("TEXT","HWShopTip",ui,"",0)
        call BlzFrameSetSize(HW_shopSlotTip[i],0.16,0.03)
        call BlzFrameSetTooltip(HW_shopSlotBtn[i],HW_shopSlotTip[i])
        call BlzTriggerRegisterFrameEvent(HW_shopSlotTrig,HW_shopSlotBtn[i],FRAMEEVENT_CONTROL_CLICK)
        call BlzFrameSetVisible(HW_shopSlotBtn[i],false)
        call BlzFrameSetVisible(HW_shopSlotIcon[i],false)
        call BlzFrameSetVisible(HW_shopSlotPrice[i],false)
        set i=i+1
    endloop
    call TriggerAddAction(HW_shopSlotTrig,function HW_ShopSlotClick)
    call HW_ShopShowCat(0)
    set HW_shopChatTrig=CreateTrigger()
    set i=0
    loop
        exitwhen i>=bj_MAX_PLAYER_SLOTS
        call TriggerRegisterPlayerChatEvent(HW_shopChatTrig,Player(i),"-shop",true)
        set i=i+1
    endloop
    call TriggerAddAction(HW_shopChatTrig,function HW_ShopChat)
    set ui=null
endfunction
function HW_ShopStart takes nothing returns nothing
    call DestroyTimer(GetExpiredTimer())
    call HW_ShopBuild()
endfunction
// HW_SHOP_END"""

MAIN_CALL = "call TimerStart(CreateTimer(),1.0,false,function HW_ShopStart) // HW_SHOP_CALL"


def _jass_string(s: str) -> str:
    """Escape a Python string for use inside a JASS double-quoted string literal."""
    s = s.replace('\\', '\\\\').replace('"', "'")
    return s


def collect_catalog(w) -> list[dict]:
    """Base shop categories -> items to sell, built from workshop.py's own reading
    of the map (shops()/item_list()/icon_info(), and ItemData/UnitBalance goldcost).

    Secret shop (uC74) and side shop (u010) are excluded on purpose (they stay
    clickable buildings, per docs/SHOP_UI_PLAN.md §4 step 7). Shops that share a
    name (Radiant/Dire "Black Market") are folded into one category: the
    catalog only needs what is shown and what it costs, not which building
    instance sold it."""
    excluded = {'uC74', 'u010'}
    fams = w.item_list()
    unit_to_fam = {}
    for g in fams:
        for su in g['shop_units']:
            unit_to_fam.setdefault(su['code'], g)
    ub_data, ub_h, ub_rows = workshop.slk(w.mpq.read('Units\\UnitBalance.slk').decode('latin1', 'replace'))
    id_data, id_h, id_rows = w.items
    categories = []
    seen_names = {}
    for shop in w.shops():
        if shop['code'] in excluded:
            continue
        cat = seen_names.get(shop['name'])
        if cat is None:
            cat = {'name': shop['name'], 'shop_codes': [], 'items': []}
            seen_names[shop['name']] = cat
            categories.append(cat)
        cat['shop_codes'].append(shop['code'])
        if cat['items']:
            continue  # same catalog on both sides, keep the first side's order
        for u in shop['units']:
            fam = unit_to_fam.get(u)
            item_code = fam['codes'][0] if fam and fam['codes'] else None
            if not item_code:
                continue
            info = w.icon_info('unit:' + u)
            art = info.get('art')
            if not art:
                continue
            cost = None
            r = ub_rows.get(u)
            if r:
                v = ub_data.get((ub_h['goldcost'], r))
                if v not in (None, ''):
                    try: cost = int(float(v))
                    except ValueError: cost = None
            if cost is None:
                for ic in fam['codes']:
                    rr = id_rows.get(ic)
                    if rr:
                        v = id_data.get((id_h['goldcost'], rr))
                        if v not in (None, '', '0'):
                            try:
                                cost = int(float(v)); break
                            except ValueError: pass
            cat['items'].append({'unit': u, 'item': item_code, 'cost': cost or 0,
                                  'icon': art, 'name': w.name(u, 'UnitFunc')})
    return [c for c in categories if c['items']]


def catalog_function(categories: list[dict], max_slots: int = HW_SHOP_SLOTS) -> str:
    """JASS function filling the HW_shop* arrays from a Python-built catalog
    (list of {'name', 'items': [{'unit','item','cost','icon','name'}]})."""
    lines = ['function HW_ShopDataInit takes nothing returns nothing']
    for ci, cat in enumerate(categories):
        items = cat['items'][:max_slots]
        lines.append(f'    set HW_shopCatName[{ci}]="{_jass_string(cat["name"])}"')
        lines.append(f'    set HW_shopCatSize[{ci}]={len(items)}')
        for si, it in enumerate(items):
            idx = ci * max_slots + si
            lines.append(f"    set HW_shopUnitId[{idx}]='{it['unit']}'")
            lines.append(f"    set HW_shopItemId[{idx}]='{it['item']}'")
            lines.append(f'    set HW_shopCost[{idx}]={it["cost"]}')
            lines.append(f'    set HW_shopIcon[{idx}]="{_jass_string(it["icon"])}"')
            lines.append(f'    set HW_shopName[{idx}]="{_jass_string(it["name"])}"')
    lines.append(f'    set HW_shopCatCount={len(categories)}')
    lines.append('endfunction')
    return '\n'.join(lines)


def inject(script: str, categories: list[dict]) -> str:
    """Return the script with the shop-window block added (idempotent). Coexists
    with the HW_COOLDOWN_* block; both are spliced the same way (globals appended
    to the first `globals` block, functions right before `main`, one call at the
    end of `main`)."""
    import re
    if not categories:
        raise ValueError('empty shop catalog')
    script = remove(script)
    funcs = FUNCTIONS.replace('// HW_SHOP_BEGIN', '// HW_SHOP_BEGIN\n' + catalog_function(categories))
    g = re.search(r'^globals\r?\n', script, re.M)
    if not g: raise ValueError('globals block not found')
    end = script.index('endglobals', g.end())
    eol = '\r\n' if '\r\n' in script[:2000] else '\n'
    script = script[:end] + GLOBALS.replace('\n', eol) + eol + script[end:]
    m = re.search(r'^function main takes nothing returns nothing\r?\n', script, re.M)
    if not m: raise ValueError('function main not found')
    script = script[:m.start()] + funcs.replace('\n', eol) + eol + script[m.start():]
    m = re.search(r'^function main takes nothing returns nothing\r?\n', script, re.M)
    e = re.search(r'^endfunction', script[m.end():], re.M)
    pos = m.end() + e.start()
    script = script[:pos] + MAIN_CALL + eol + script[pos:]
    return script


def remove(script: str) -> str:
    import re
    script = re.sub(r'// HW_SHOP_GLOBALS_BEGIN.*?// HW_SHOP_GLOBALS_END\r?\n', '', script, flags=re.S)
    script = re.sub(r'// HW_SHOP_BEGIN.*?// HW_SHOP_END\r?\n', '', script, flags=re.S)
    script = re.sub(r'^.*// HW_SHOP_CALL\r?\n', '', script, flags=re.M)
    return script
