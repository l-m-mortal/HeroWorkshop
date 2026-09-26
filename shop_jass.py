"""JASS block that draws a Dota 2-style shop window (Warcraft III 1.31+).

Injected into war3map.j by `map_fix.py shop-ui`. Pure JASS, no vJASS/Lua (variant
A of docs/SHOP_UI_PLAN.md). Modelled on cooldown_jass.py: a GLOBALS block, a
FUNCTIONS block spliced in front of `main`, and one call appended to the end of
`main`. Coexists with the HW_COOLDOWN_* block cooldown_jass.py injects (distinct
marker comments, distinct globals/functions, both spliced the same way).

Layout (this is the second, right-docked revision -- see docs/SHOP_UI_NOTES.md
for the earlier "tabs" and "two pages" prototypes it replaces, and why): a
column docked to the RIGHT screen edge, between the score bar and the command
card (PANEL_* constants below), showing ALL base shops at once as small blocks
(ASCII text header + a 4x3 icon grid in the SAME cell positions the map's own
shop UI uses, from each sold dummy unit's `Buttonpos`) -- no tabs, no pages, no
scrolling: two columns of up to SHOPS_PER_COL blocks each, sized to fit the
whole 14-shop catalog in the panel's fixed height (which is why ICON below is
noticeably smaller than the ~0.018-0.024 first suggested -- see the note next
to it). Every geometry knob is a module-level constant so the layout can be
retuned without touching the JASS template strings.

* One hidden panel (BACKDROP) is built once, 1s after map start. Opening just
  flips visibility (no slide animation, per the task).
* The clickable "Shop" toggle is an invisible BUTTON placed exactly over the
  existing HUD "SHOP" command-card label (TOGGLE_* constants), not a new
  visible button -- the previous prototype's own "Shop" button sat on top of
  the command card, which the second in-game test flagged. The "-shop" chat
  command (registered for every player slot) still works the same way.
* Both toggles flip visibility of the SAME shared panel, but only on the
  clicking player's own client (`if GetLocalPlayer() == p then ... endif`
  around BlzFrameSetVisible only -- no handle is created there, so this
  cannot desync). This gives each player their own open/closed state.
* All shop content (icons, tooltips, the frame->item hashtable) is written
  ONCE at build time and never rewritten afterwards -- there is no page/tab
  state shared between players any more, since there is no page/tab.
* Buying does not replay the map's native Sellunits/order-id purchase path
  (unverified without a live client, see docs/SHOP_UI_PLAN.md §6) -- it uses
  the safe fallback the task allows: check gold, GetPlayerState/SetPlayerState
  to pay, UnitAddItemById on the player's first hero (GroupEnumUnitsOfPlayer +
  IsUnitType UNIT_TYPE_HERO). No courier/fountain-drop fallback is implemented
  (documented limitation, unchanged from earlier prototypes).
* Panel/button textures: the first live-client test after the previous
  revision showed the panel as a solid green rectangle -- IN QUEUE
  ``human-options-menu-background.blp`` looked fine in the very first
  prototype's playtest (docs/SHOP_UI_NOTES.md) but apparently isn't reliably
  present as a standalone texture in this client's CASC/MPQ search order for
  a plain BACKDROP with no TOC-declared control class. Switched to
  ``UI\\Widgets\\ToolTips\\Human\\human-tooltip-background.blp`` for the panel
  and block-header backdrops and ``UI\\Widgets\\Console\\Human\\human-console-
  button-background.blp`` for the close button -- both are plain, commonly
  reused chrome textures (tooltip frames and the escape-menu console already
  render them in 1.31), so they are the safer bet than the EscMenu ones this
  file used before. Not verified with a live client from this environment
  either (no game client here) -- if it is still wrong, the fallback the task
  names (``BlzFrameSetAlpha`` solid-color backdrop, or a
  ``ReplaceableTextures\\CommandButtons\\...`` icon) is the next thing to try,
  see docs/SHOP_UI_NOTES.md.
"""

import workshop

# ---- tunable geometry (see the layout note in the module docstring) --------
# Panel: a column docked to the right screen edge, between the score bar and
# the command card.
PANEL_RIGHT_X = 0.80     # FRAMEPOINT_TOPRIGHT anchor x
PANEL_TOP_Y = 0.53        # FRAMEPOINT_TOPRIGHT anchor y (just below the score bar)
PANEL_BOTTOM_Y = 0.20     # must not go lower than this (top of the command card)
PANEL_W = 0.26
PANEL_H = PANEL_TOP_Y - PANEL_BOTTOM_Y

CLOSE_SIZE = 0.016
TOP_MARGIN = 0.006 + CLOSE_SIZE + 0.004   # room left at the panel's top for the close button

# Two columns of shop blocks, SHOPS_PER_COL rows each -- no tabs/pages.
BLOCK_COLS = 2
SHOPS_PER_COL = 7
HW_SHOP_MAX_SHOPS = BLOCK_COLS * SHOPS_PER_COL   # 14: exactly the map's base-shop count
MARGIN_X = 0.008
COL_W = PANEL_W / 2.0

HEADER_H = 0.007
HEADER_GAP = 0.0008
BLOCK_GAP = 0.0015
BODY_H = PANEL_H - TOP_MARGIN
BLOCK_PITCH = BODY_H / SHOPS_PER_COL
BLOCK_H = BLOCK_PITCH - BLOCK_GAP
GRID_H = BLOCK_H - HEADER_H - HEADER_GAP

HW_SHOP_CELL_COLS = 4
HW_SHOP_CELLS = 12          # 4x3 grid per shop block, same as the map's own shop button grid
ICON_GAP = 0.001
ICON_PITCH = GRID_H / 3.0
ICON = ICON_PITCH - ICON_GAP   # ~0.0104: shrunk from the ~0.018-0.024 first suggested so that
                               # SHOPS_PER_COL=7 blocks of 3 rows actually fit in PANEL_H without
                               # any paging/scrolling (the task's later, stricter panel bounds and
                               # "no tabs/pages" both take priority over the icon-size hint) --
                               # see docs/SHOP_UI_NOTES.md.
HEADER_W = COL_W - 0.016

# Invisible toggle button placed exactly over the HUD's own "SHOP" command-card
# label (approximate 4:3 frame coords the task gave; retune here if it is off
# on a live client).
TOGGLE_X0 = 0.56
TOGGLE_Y0 = 0.16
TOGGLE_X1 = 0.62
TOGGLE_Y1 = 0.19
TOGGLE_W = TOGGLE_X1 - TOGGLE_X0
TOGGLE_H = TOGGLE_Y1 - TOGGLE_Y0

PANEL_TEXTURE = 'UI\\\\Widgets\\\\ToolTips\\\\Human\\\\human-tooltip-background.blp'
BUTTON_TEXTURE = 'UI\\\\Widgets\\\\Console\\\\Human\\\\human-console-button-background.blp'


def _is_ascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)

GLOBALS = f"""// HW_SHOP_GLOBALS_BEGIN
constant integer HW_SHOP_MAX_SHOPS={HW_SHOP_MAX_SHOPS}
constant integer HW_SHOP_CELLS={HW_SHOP_CELLS}
constant integer HW_SHOP_CELL_COLS={HW_SHOP_CELL_COLS}
constant integer HW_SHOP_BLOCK_COLS={BLOCK_COLS}
constant integer HW_SHOP_SHOPS_PER_COL={SHOPS_PER_COL}
integer array HW_shopUnitId
integer array HW_shopItemId
integer array HW_shopCost
string array HW_shopIcon
string array HW_shopName
string array HW_shopShopName
integer HW_shopCount=0
boolean HW_shopLocalOpen=false
framehandle HW_shopPanel=null
framehandle HW_shopCloseBg=null
framehandle HW_shopCloseText=null
framehandle HW_shopCloseBtn=null
framehandle HW_shopToggleBtn=null
framehandle array HW_shopBlockHeader
framehandle array HW_shopCellBg
framehandle array HW_shopCellBtn
framehandle array HW_shopCellTip
hashtable HW_shopSlotHT=null
trigger HW_shopSlotTrig=null
trigger HW_shopToggleTrig=null
trigger HW_shopCloseTrig=null
trigger HW_shopChatTrig=null
timer HW_shopTimer=null
// HW_SHOP_GLOBALS_END"""

FUNCTIONS = f"""// HW_SHOP_BEGIN
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
    local integer j
    local integer col
    local integer row
    local integer cc
    local integer rr
    local integer cellBase
    local integer idx
    local real bx
    local real by
    call HW_ShopDataInit()
    set HW_shopSlotHT=InitHashtable()
    set HW_shopPanel=BlzCreateFrameByType("BACKDROP","HWShopPanel",ui,"",0)
    call BlzFrameSetAbsPoint(HW_shopPanel,FRAMEPOINT_TOPRIGHT,{PANEL_RIGHT_X:.6f},{PANEL_TOP_Y:.6f})
    call BlzFrameSetSize(HW_shopPanel,{PANEL_W:.6f},{PANEL_H:.6f})
    call BlzFrameSetTexture(HW_shopPanel,"{PANEL_TEXTURE}",0,true)
    call BlzFrameSetVisible(HW_shopPanel,false)
    set HW_shopCloseBg=BlzCreateFrameByType("BACKDROP","HWShopCloseBg",HW_shopPanel,"",0)
    call BlzFrameSetPoint(HW_shopCloseBg,FRAMEPOINT_TOPRIGHT,HW_shopPanel,FRAMEPOINT_TOPRIGHT,-0.006,-0.006)
    call BlzFrameSetSize(HW_shopCloseBg,{CLOSE_SIZE:.6f},{CLOSE_SIZE:.6f})
    call BlzFrameSetTexture(HW_shopCloseBg,"{BUTTON_TEXTURE}",0,true)
    set HW_shopCloseText=BlzCreateFrameByType("TEXT","HWShopCloseText",HW_shopCloseBg,"",0)
    call BlzFrameSetAllPoints(HW_shopCloseText,HW_shopCloseBg)
    call BlzFrameSetTextAlignment(HW_shopCloseText,TEXT_JUSTIFY_MIDDLE,TEXT_JUSTIFY_CENTER)
    call BlzFrameSetText(HW_shopCloseText,"X")
    set HW_shopCloseBtn=BlzCreateFrameByType("BUTTON","HWShopClose",HW_shopCloseBg,"",0)
    call BlzFrameSetAllPoints(HW_shopCloseBtn,HW_shopCloseBg)
    set HW_shopCloseTrig=CreateTrigger()
    call BlzTriggerRegisterFrameEvent(HW_shopCloseTrig,HW_shopCloseBtn,FRAMEEVENT_CONTROL_CLICK)
    call TriggerAddAction(HW_shopCloseTrig,function HW_ShopCloseClick)
    set HW_shopToggleBtn=BlzCreateFrameByType("BUTTON","HWShopToggle",ui,"",0)
    call BlzFrameSetAbsPoint(HW_shopToggleBtn,FRAMEPOINT_BOTTOMLEFT,{TOGGLE_X0:.6f},{TOGGLE_Y0:.6f})
    call BlzFrameSetSize(HW_shopToggleBtn,{TOGGLE_W:.6f},{TOGGLE_H:.6f})
    set HW_shopToggleTrig=CreateTrigger()
    call BlzTriggerRegisterFrameEvent(HW_shopToggleTrig,HW_shopToggleBtn,FRAMEEVENT_CONTROL_CLICK)
    call TriggerAddAction(HW_shopToggleTrig,function HW_ShopToggleClick)
    set HW_shopSlotTrig=CreateTrigger()
    set i=0
    loop
        exitwhen i>=HW_shopCount
        set col=i/HW_SHOP_SHOPS_PER_COL
        set row=i-col*HW_SHOP_SHOPS_PER_COL
        set bx={MARGIN_X:.6f}+I2R(col)*{COL_W:.6f}
        set by=-{TOP_MARGIN:.6f}-I2R(row)*{BLOCK_PITCH:.6f}
        set HW_shopBlockHeader[i]=BlzCreateFrameByType("TEXT","HWShopBlockHeader",HW_shopPanel,"",0)
        call BlzFrameSetPoint(HW_shopBlockHeader[i],FRAMEPOINT_TOPLEFT,HW_shopPanel,FRAMEPOINT_TOPLEFT,bx,by)
        call BlzFrameSetSize(HW_shopBlockHeader[i],{HEADER_W:.6f},{HEADER_H:.6f})
        call BlzFrameSetScale(HW_shopBlockHeader[i],0.55)
        call BlzFrameSetTextAlignment(HW_shopBlockHeader[i],TEXT_JUSTIFY_TOP,TEXT_JUSTIFY_LEFT)
        call BlzFrameSetText(HW_shopBlockHeader[i],HW_shopShopName[i])
        set cellBase=i*HW_SHOP_CELLS
        set j=0
        loop
            exitwhen j>=HW_SHOP_CELLS
            set idx=i*HW_SHOP_CELLS+j
            if HW_shopItemId[idx]!=0 then
                set cc=j-(j/HW_SHOP_CELL_COLS)*HW_SHOP_CELL_COLS
                set rr=j/HW_SHOP_CELL_COLS
                set HW_shopCellBg[cellBase+j]=BlzCreateFrameByType("BACKDROP","HWShopCellBg",HW_shopPanel,"",0)
                call BlzFrameSetPoint(HW_shopCellBg[cellBase+j],FRAMEPOINT_TOPLEFT,HW_shopPanel,FRAMEPOINT_TOPLEFT,bx+I2R(cc)*{ICON_PITCH:.6f},by-{HEADER_H:.6f}-{HEADER_GAP:.6f}-I2R(rr)*{ICON_PITCH:.6f})
                call BlzFrameSetSize(HW_shopCellBg[cellBase+j],{ICON:.6f},{ICON:.6f})
                call BlzFrameSetTexture(HW_shopCellBg[cellBase+j],HW_shopIcon[idx],0,true)
                set HW_shopCellBtn[cellBase+j]=BlzCreateFrameByType("BUTTON","HWShopCellBtn",HW_shopPanel,"",0)
                call BlzFrameSetPoint(HW_shopCellBtn[cellBase+j],FRAMEPOINT_TOPLEFT,HW_shopCellBg[cellBase+j],FRAMEPOINT_TOPLEFT,0,0)
                call BlzFrameSetSize(HW_shopCellBtn[cellBase+j],{ICON:.6f},{ICON:.6f})
                set HW_shopCellTip[cellBase+j]=BlzCreateFrameByType("TEXT","HWShopCellTip",ui,"",0)
                call BlzFrameSetSize(HW_shopCellTip[cellBase+j],0.16,0.03)
                call BlzFrameSetText(HW_shopCellTip[cellBase+j],HW_shopName[idx]+"|n|cffffcc00"+I2S(HW_shopCost[idx])+" gold|r")
                call BlzFrameSetTooltip(HW_shopCellBtn[cellBase+j],HW_shopCellTip[cellBase+j])
                call BlzTriggerRegisterFrameEvent(HW_shopSlotTrig,HW_shopCellBtn[cellBase+j],FRAMEEVENT_CONTROL_CLICK)
                call SaveInteger(HW_shopSlotHT,GetHandleId(HW_shopCellBtn[cellBase+j]),0,idx)
            endif
            set j=j+1
        endloop
        set i=i+1
    endloop
    call TriggerAddAction(HW_shopSlotTrig,function HW_ShopSlotClick)
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


def _place_cells(items: list[dict]) -> list[dict | None]:
    """Lay out a shop's items on the same 4x3 (col,row) grid the map's own shop
    button uses (each sold dummy unit's Buttonpos, col 0-3 / row 0-2 -> cell
    row*4+col). Two shop-window quirks make a plain "put it where Buttonpos
    says" not quite enough: a few items have no Buttonpos at all, and several
    recipe components legitimately share a cell with their finished item
    (the map's native shop UI swaps between an item view and a recipe view in
    that same slot; this window shows only one flat grid). Both cases fall
    back to the first free cell (row-major) so nothing sold becomes
    unreachable -- every base shop in the test map has <=12 sellable items, so
    this fallback always finds room. Cells nothing landed on stay empty, as
    the task asks."""
    cells: list[dict | None] = [None] * HW_SHOP_CELLS
    overflow = []
    for it in items:
        bp = it.get('buttonpos')
        cell = None
        if bp and 0 <= bp[0] <= 3 and 0 <= bp[1] <= 2:
            want = bp[1] * 4 + bp[0]
            if cells[want] is None:
                cell = want
        if cell is None:
            overflow.append(it)
        else:
            cells[cell] = it
    for it in overflow:
        for c in range(HW_SHOP_CELLS):
            if cells[c] is None:
                cells[c] = it
                break
        # else: shop has >12 sellable items, dropped (not seen on the test map)
    return cells


def collect_catalog(w) -> list[dict]:
    """Base shop categories -> items to sell, built from workshop.py's own reading
    of the map (shops()/item_list()/icon_info(), and ItemData/UnitBalance goldcost,
    Buttonpos for grid placement).

    Secret shop (uC74) and side shop (u010) are excluded on purpose (they stay
    clickable buildings, per docs/SHOP_UI_PLAN.md §4 step 7). Shops that share a
    name (Radiant/Dire "Black Market") are folded into one category: the
    catalog only needs what is shown and what it costs, not which building
    instance sold it (buying uses UnitAddItemById, not the clicked building, so
    which side's copy supplied the catalog does not matter)."""
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
            name = w.name(u, 'UnitFunc')
            if not _is_ascii(name):
                name = f'Item {item_code}'
            cat['items'].append({'unit': u, 'item': item_code, 'cost': cost or 0,
                                  'icon': art, 'name': name, 'buttonpos': w.xy(u, 'Buttonpos')})
    result = [c for c in categories if c['items']]
    if len(result) > HW_SHOP_MAX_SHOPS:
        raise ValueError(f'{len(result)} shop categories, HW_SHOP_MAX_SHOPS={HW_SHOP_MAX_SHOPS} '
                          f'(BLOCK_COLS={BLOCK_COLS} x SHOPS_PER_COL={SHOPS_PER_COL}) is too small')
    for i, cat in enumerate(result, 1):
        # The map's *.txt files mix latin1/cp1251 encodings; a non-ASCII shop-unit
        # name would render as "????????" in the client's font, so fall back to a
        # plain, always-displayable category label (docs/SHOP_UI_NOTES.md).
        if not _is_ascii(cat['name']):
            cat['name'] = f'Shop {i}'
        cat['cells'] = _place_cells(cat['items'])
    return result


def catalog_function(categories: list[dict]) -> str:
    """JASS function filling the HW_shop* arrays from a Python-built catalog
    (list of {'name', 'items', 'cells': [12 x ({'unit','item','cost','icon','name'} or None)]})."""
    lines = ['function HW_ShopDataInit takes nothing returns nothing']
    for ci, cat in enumerate(categories):
        lines.append(f'    set HW_shopShopName[{ci}]="{_jass_string(cat["name"])}"')
        for si, it in enumerate(cat['cells']):
            if it is None:
                continue
            idx = ci * HW_SHOP_CELLS + si
            lines.append(f"    set HW_shopUnitId[{idx}]='{it['unit']}'")
            lines.append(f"    set HW_shopItemId[{idx}]='{it['item']}'")
            lines.append(f'    set HW_shopCost[{idx}]={it["cost"]}')
            lines.append(f'    set HW_shopIcon[{idx}]="{_jass_string(it["icon"])}"')
            lines.append(f'    set HW_shopName[{idx}]="{_jass_string(it["name"])}"')
    lines.append(f'    set HW_shopCount={len(categories)}')
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
    if len(categories) > HW_SHOP_MAX_SHOPS:
        raise ValueError(f'{len(categories)} shop categories, HW_SHOP_MAX_SHOPS={HW_SHOP_MAX_SHOPS} is too small')
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
