"""JASS block that draws a Dota 2-style shop window (Warcraft III 1.31+).

Injected into war3map.j by `map_fix.py shop-ui`. Pure JASS, no vJASS/Lua (variant
A of docs/SHOP_UI_PLAN.md). Modelled on cooldown_jass.py: a GLOBALS block, a
FUNCTIONS block spliced in front of `main`, and one call appended to the end of
`main`. Coexists with the HW_COOLDOWN_* block cooldown_jass.py injects (distinct
marker comments, distinct globals/functions, both spliced the same way).

Layout (this is the third revision -- see docs/SHOP_UI_NOTES.md for v1 "tabs",
v2 "two pages" and why both were dropped): a column docked to the right screen
edge with a small margin (PANEL_* constants below), between the score bar and
the command card, showing ALL base shops at once as small blocks (ASCII text
header directly above its own 4x3 icon grid, same x, at each item's in-game
Buttonpos cell) -- no tabs, no pages, no scrolling: three columns of up to
SHOPS_PER_COL blocks each. Every geometry knob is a module-level constant so
the layout can be retuned without touching the JASS template strings.

* One hidden panel (BACKDROP) is built once, 1s after map start. Opening just
  flips visibility (no slide animation, per the task).
* The clickable "Shop" toggle sits over the existing HUD "SHOP" command-card
  label (TOGGLE_* constants): a BACKDROP (existing chrome texture, low alpha
  so it can actually be seen and the offset tuned -- fully-invisible buttons
  did not register clicks reliably in the previous revision's playtest) with
  a BUTTON child on top, same construction as every other button in this file
  (BACKDROP + BUTTON, sometimes + TEXT). The "-shop" chat command (registered
  for every player slot) still works the same way.
* Both toggles flip visibility of the SAME shared panel, but only on the
  clicking player's own client (`if GetLocalPlayer() == p then ... endif`
  around BlzFrameSetVisible only -- no handle is created there, so this
  cannot desync). This gives each player their own open/closed state.
* All shop content (icons, tooltips, the frame->item hashtable) is written
  ONCE at build time and never rewritten afterwards.
* PURCHASE (this revision's main functional change): clicking an icon no
  longer fakes a purchase with UnitAddItemById/SetPlayerState. It now issues
  the map's own real shop-sell order -- exactly what clicking the item in the
  in-game base shop does -- so gold cost, "Item Made"/Sellunits item
  creation and the "hero not near the shop" fallback are all the live map's
  own native logic, not this file's:
    - Every base shop building on this map (both the Radiant and the Dire
      copy, for shops that have one) is owned by Player(PLAYER_NEUTRAL_
      PASSIVE) -- confirmed by reading the decompiled war3map.j's own
      shop-placement code (`CreateUnit(ra,'n00W',...)` etc, with
      `ra=Player(PLAYER_NEUTRAL_PASSIVE)`; see docs/SHOP_UI_NOTES.md for the
      exact grep). Sellunits order id == the sold unit type id (native
      Warcraft III convention: 'h076' etc, already what HW_shopUnitId
      stores).
    - HW_ShopBuy therefore looks up the buyer's hero, finds the physically
      nearest live neutral-passive unit whose type matches one of this
      category's building codes (HW_shopBuildingCode[], collected from
      workshop.shops()'s own unit-type codes -- 1 per shop, 2 for "Black
      Market" whose Radiant/Dire copies are two distinct unit types) and
      calls IssueNeutralImmediateOrderById(buyer, thatUnit, soldUnitTypeId).
      "Nearest to the hero" stands in for "the buyer's team's copy" without
      hardcoding a team/player-slot convention this map's obfuscated script
      does not expose cleanly -- for a hero anywhere near their own base
      (the normal case) it resolves to the same building the in-game shop
      panel itself would use.
    - What happens if the hero is NOT near any copy of the shop: this file
      does not implement a fountain/courier drop of its own, and a careful
      grep of the decompiled war3map.j for `GetSoldUnit()`/`EVENT_PLAYER_
      UNIT_SELL` found no generic handler for ordinary item purchases either
      (every hit belongs to the hero-draft/ban screen or to the courier/
      buyback/revive special units) -- meaning the "goes to the fountain/
      courier stash" behaviour, if this map has any, is the Warcraft III
      engine's own default Sellunits-with-no-unit-in-range behaviour, not
      custom script this file can call into. Documented, not invented.
    - Secret shop (uC74) and side shop (u010) stay excluded from
      collect_catalog exactly as before, so their items are not purchasable
      from this panel.
* Panel/button textures: the first live-client test showed the panel as a
  solid green rectangle with `human-options-menu-background.blp`; switched to
  `UI\\Widgets\\ToolTips\\Human\\human-tooltip-background.blp` for the panel
  and block-header backdrops and `UI\\Widgets\\Console\\Human\\human-console-
  button-background.blp` for the close/toggle buttons -- not re-verified with
  a live client from this environment (no game client here); if still wrong,
  a solid-alpha BACKDROP with no texture is the next thing to try.
"""

import workshop

# ---- tunable geometry (see the layout note in the module docstring) --------
# Panel: a column docked to the right screen edge with a small margin, between
# the score bar and the command card.
SCREEN_RIGHT_X = 0.80     # approximate hard right edge of the 4:3 frame area
PANEL_MARGIN_RIGHT = 0.02
PANEL_RIGHT_X = SCREEN_RIGHT_X - PANEL_MARGIN_RIGHT   # FRAMEPOINT_TOPRIGHT anchor x
PANEL_TOP_Y = 0.53         # FRAMEPOINT_TOPRIGHT anchor y (just below the score bar)
PANEL_BOTTOM_Y = 0.20      # must not go lower than this (top of the command card)
PANEL_W = 0.28
PANEL_H = PANEL_TOP_Y - PANEL_BOTTOM_Y

CLOSE_SIZE = 0.016
TOP_MARGIN = 0.006 + CLOSE_SIZE + 0.004   # room left at the panel's top for the close button

# Three columns of shop blocks, SHOPS_PER_COL rows each -- no tabs/pages.
BLOCK_COLS = 3
SHOPS_PER_COL = 5
HW_SHOP_MAX_SHOPS = BLOCK_COLS * SHOPS_PER_COL   # 15: >= the map's 14 base shops
MARGIN_X = 0.007
COL_W = PANEL_W / BLOCK_COLS

HEADER_H = 0.007
HEADER_GAP = 0.0008
BLOCK_GAP = 0.002
BODY_H = PANEL_H - TOP_MARGIN
BLOCK_PITCH = BODY_H / SHOPS_PER_COL
BLOCK_H = BLOCK_PITCH - BLOCK_GAP
GRID_H = BLOCK_H - HEADER_H - HEADER_GAP

HW_SHOP_CELL_COLS = 4
HW_SHOP_CELLS = 12          # 4x3 grid per shop block, same as the map's own shop button grid
ICON_GAP = 0.0008
ICON_PITCH = GRID_H / 3.0
ICON = ICON_PITCH - ICON_GAP   # ~0.016, in the requested ~0.017-0.02 ballpark: as big as
                               # SHOPS_PER_COL=5 blocks of header+3 rows can be and still
                               # fit PANEL_H with no paging/scrolling -- see docs/SHOP_UI_NOTES.md.
HEADER_W = COL_W - 0.014

# Up to this many physical shop-building unit types per category (workshop.py
# shops()'s own unit-type codes -- 1 for almost every base shop, 2 for "Black
# Market" whose Radiant/Dire copies are distinct unit types).
HW_SHOP_BUILDING_CODES = 3

# Toggle button placed over the HUD's own "SHOP" command-card label
# (approximate 4:3 frame coords the task gave; retune here if it is off on a
# live client -- kept partially visible (TOGGLE_ALPHA) so the offset can be
# read/reported, per the task; a fully invisible button did not register
# clicks reliably in the previous revision).
TOGGLE_X0 = 0.56
TOGGLE_Y0 = 0.16
TOGGLE_X1 = 0.62
TOGGLE_Y1 = 0.19
TOGGLE_W = TOGGLE_X1 - TOGGLE_X0
TOGGLE_H = TOGGLE_Y1 - TOGGLE_Y0
TOGGLE_ALPHA = 40   # 0-255; 0 once the offset above is confirmed correct in-game

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
constant integer HW_SHOP_BUILDING_CODES={HW_SHOP_BUILDING_CODES}
integer array HW_shopUnitId
integer array HW_shopItemId
integer array HW_shopCost
string array HW_shopIcon
string array HW_shopName
string array HW_shopShopName
integer array HW_shopBuildingCode
integer HW_shopCount=0
boolean HW_shopLocalOpen=false
player HW_shopOwner=null
framehandle HW_shopPanel=null
framehandle HW_shopCloseBg=null
framehandle HW_shopCloseText=null
framehandle HW_shopCloseBtn=null
framehandle HW_shopToggleBg=null
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
function HW_ShopBuildingMatches takes integer shopIdx, integer typeId returns boolean
    local integer k=0
    loop
        exitwhen k>=HW_SHOP_BUILDING_CODES
        if HW_shopBuildingCode[shopIdx*HW_SHOP_BUILDING_CODES+k]==typeId then
            return true
        endif
        set k=k+1
    endloop
    return false
endfunction
function HW_ShopFindShopUnit takes integer shopIdx, real hx, real hy returns unit
    local group g=CreateGroup()
    local unit u
    local unit best=null
    local real bestDist=-1.0
    local real dx
    local real dy
    local real dist
    call GroupEnumUnitsOfPlayer(g,HW_shopOwner,null)
    loop
        set u=FirstOfGroup(g)
        exitwhen u==null
        call GroupRemoveUnit(g,u)
        if HW_ShopBuildingMatches(shopIdx,GetUnitTypeId(u)) then
            set dx=GetUnitX(u)-hx
            set dy=GetUnitY(u)-hy
            set dist=dx*dx+dy*dy
            if bestDist<0 or dist<bestDist then
                set best=u
                set bestDist=dist
            endif
        endif
    endloop
    call DestroyGroup(g)
    set g=null
    set u=null
    return best
endfunction
function HW_ShopBuy takes player p, integer idx returns nothing
    local integer shopIdx
    local integer soldId
    local unit hero
    local unit shopUnit
    if idx<0 then
        return
    endif
    set soldId=HW_shopUnitId[idx]
    if soldId==0 then
        return
    endif
    set hero=HW_ShopFindHero(p)
    if hero==null then
        call DisplayTextToPlayer(p,0,0,"|cffffcc00HW Shop:|r no hero found, purchase cancelled")
        return
    endif
    set shopIdx=idx/HW_SHOP_CELLS
    set shopUnit=HW_ShopFindShopUnit(shopIdx,GetUnitX(hero),GetUnitY(hero))
    if shopUnit==null then
        call DisplayTextToPlayer(p,0,0,"|cffffcc00HW Shop:|r shop building not found, purchase cancelled")
        set hero=null
        return
    endif
    call IssueNeutralImmediateOrderById(p,shopUnit,soldId)
    call DisplayTextToPlayer(p,0,0,"|cff60ff60HW Shop:|r requested "+HW_shopName[idx]+" ("+I2S(HW_shopCost[idx])+"g)")
    set hero=null
    set shopUnit=null
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
    set HW_shopOwner=Player(PLAYER_NEUTRAL_PASSIVE)
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
    set HW_shopToggleBg=BlzCreateFrameByType("BACKDROP","HWShopToggleBg",ui,"",0)
    call BlzFrameSetAbsPoint(HW_shopToggleBg,FRAMEPOINT_BOTTOMLEFT,{TOGGLE_X0:.6f},{TOGGLE_Y0:.6f})
    call BlzFrameSetSize(HW_shopToggleBg,{TOGGLE_W:.6f},{TOGGLE_H:.6f})
    call BlzFrameSetTexture(HW_shopToggleBg,"{BUTTON_TEXTURE}",0,true)
    call BlzFrameSetAlpha(HW_shopToggleBg,{TOGGLE_ALPHA})
    set HW_shopToggleBtn=BlzCreateFrameByType("BUTTON","HWShopToggle",HW_shopToggleBg,"",0)
    call BlzFrameSetAllPoints(HW_shopToggleBtn,HW_shopToggleBg)
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
    clickable buildings, per docs/SHOP_UI_PLAN.md §4 step 7) -- so they are not
    purchasable from this panel either. Shops that share a name (Radiant/Dire
    "Black Market") are folded into one category, but their (possibly distinct)
    building unit-type codes are all kept (cat['shop_codes']) -- the purchase
    handler needs every physical building type that can sell this catalog to
    find the correct live unit to issue the sell order on (see the module
    docstring)."""
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
        if len(cat['shop_codes']) > HW_SHOP_BUILDING_CODES:
            raise ValueError(f"shop {cat['name']!r} has {len(cat['shop_codes'])} building codes, "
                              f'HW_SHOP_BUILDING_CODES={HW_SHOP_BUILDING_CODES} is too small')
        cat['cells'] = _place_cells(cat['items'])
    return result


def catalog_function(categories: list[dict]) -> str:
    """JASS function filling the HW_shop* arrays from a Python-built catalog
    (list of {'name', 'shop_codes', 'items', 'cells': [12 x (item-dict or None)]})."""
    lines = ['function HW_ShopDataInit takes nothing returns nothing']
    for ci, cat in enumerate(categories):
        lines.append(f'    set HW_shopShopName[{ci}]="{_jass_string(cat["name"])}"')
        for ki, code in enumerate(cat['shop_codes']):
            lines.append(f"    set HW_shopBuildingCode[{ci * HW_SHOP_BUILDING_CODES + ki}]='{code}'")
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
