"""JASS block that draws a Dota 2-style shop window (Warcraft III 1.31+).

Injected into war3map.j by `map_fix.py shop-ui`. Pure JASS, no vJASS/Lua (variant
A of docs/SHOP_UI_PLAN.md). Modelled on cooldown_jass.py: a GLOBALS block, a
FUNCTIONS block spliced in front of `main`, and one call appended to the end of
`main`. Coexists with the HW_COOLDOWN_* block cooldown_jass.py injects (distinct
marker comments, distinct globals/functions, both spliced the same way).

v5 (this revision -- see docs/SHOP_UI_NOTES.md for v1-v4 and why they were
dropped): two team-scoped catalogs instead of one flat 14-category list.

* **Why**: v4's single catalog showed every base shop (both teams' copies AND
  the two side-flavoured shops that only exist on one base, e.g. "Cache of the
  Quel'Thelan" on the Radiant side vs "Demonic Artifacts" on the Dire side) to
  every player at once -- items appeared to duplicate, and worse, a composite
  item's recipe expansion (`_build_parts`) matched components against the
  *whole* 14-category union regardless of which base physically has them. A
  hero shopping at their own base could click a recipe whose components only
  matched a shop that exists on the *other* team's base, thousands of units
  away -- `HW_ShopFindShopUnit` still "succeeds" (it has no proximity
  requirement, it just finds the nearest live building of that type anywhere
  on the map) and `IssueNeutralImmediateOrderById` still runs, but the
  Warcraft III engine's own Sellunits logic only hands the created item to an
  ally *near that specific shop building* -- with the hero standing at the
  other end of the map, nothing receives it. That is why a composite bought
  "only the recipe scroll": the recipe's own shop (the one the hero actually
  clicked from, so they were standing near it) succeeded, every component
  resolved to a foreign-team shop and silently produced nothing.
* **Fix**: `collect_catalog` now determines each shop building's side(s) from
  the coordinates of its own `CreateUnit(...,'CODE',x,y)` calls in the
  decompiled war3map.j (x<0,y<0 -> Radiant, x>0,y>0 -> Dire; a code with
  placements on both sides, e.g. nC38/n01K, belongs to both), and builds two
  independent catalogs (`{'radiant': [...], 'dire': [...]}`). Recipe expansion
  (`_build_parts`) now runs once per side, matching a composite's components
  only among items of *that side's own* catalog -- so every part a hero can
  click is guaranteed to resolve, for a hero at their own base, to a building
  on the same side. u00Z (Goblin Laboratory, a side shop) is now excluded
  alongside u010/uC74 (it used to slip through collect_catalog's `excluded`
  set, which only listed uC74/u010 -- a separate bug fixed here).
* **Layout**: two columns instead of three -- one column per side (col 0
  Radiant, col 1 Dire), `SHOPS_PER_COL` derived from `max(len(radiant),
  len(dire))` at inject time (it can no longer be a fixed module constant,
  since it depends on how many shops the map's own script places on each
  side -- see `_geometry`). Each client shows only its own team's column
  (`HW_ShopApplyTeamVisibility`, run once at build time): "Radiant" is simply
  `GetPlayerId(GetLocalPlayer())<=4` (players 1-5 in DotA's own convention;
  7-11 are Dire) -- purely a per-client `BlzFrameSetVisible` call with no
  handle created and no state read that could differ between clients in a way
  that reaches game state, so (like every other visibility toggle in this
  file) it cannot desync.
* **Debug**: `HW_ShopBuy` now prints one `DisplayTextToPlayer` line per part as
  it is ordered ("HW Shop: order <shop> -> <item>"), one line naming the
  reason when a part's shop building cannot be found at all, and one line if a
  composite's parts table is somehow empty. `collect_catalog`/`fix_shop_ui`
  also print a parts-resolution table at inject time (`parts_report`): how
  many items resolved >=2 parts and five examples including Vladmir's
  Offering and Battle Fury, to make the fix verifiable without a live client.
* **Toggle**: moved off the panel-relative anchor (`HW_shopRightX`-derived, so
  it silently followed the panel past the 0.8 client clip and became
  unclickable) to an absolute anchor on `ORIGIN_FRAME_GAME_UI`
  (`TOGGLE_X0/X1/Y0/Y1 = 0.62/0.68/0.132/0.158`, over the HUD's own "SHOP"
  label) with `TOGGLE_ALPHA=60` so it can be seen while this is re-verified
  live; the panel parent (`--parent`) no longer affects it at all.
* Default `PANEL_TOP_Y` lowered to 0.53 (was 0.555) so the panel starts
  strictly below the score tab; `--top/--bottom/--right/--parent` still work.

See docs/SHOP_UI_NOTES.md for v1-v4: tabs, the two-page catalog, the
composite/toggle/three-column revision, and the earlier purchase mechanism
history (real Sellunits order instead of a UnitAddItemById fake, texture
fixes, ASCII-only names).
"""

import copy
import re

import workshop

# ---- tunable geometry (see the layout note in the module docstring) --------
# Panel: a column flush with the right screen edge (no margin), from directly
# under the top score tab down to the top of the bottom command card.
PANEL_RIGHT_X = 0.80       # FRAMEPOINT_TOPRIGHT anchor x -- flush with the screen edge
PANEL_TOP_Y = 0.53         # FRAMEPOINT_TOPRIGHT anchor y -- below the score tab (task default)
PANEL_BOTTOM_Y = 0.20      # must not go lower than this (top of the command card)
PANEL_W = 0.28
PANEL_H = PANEL_TOP_Y - PANEL_BOTTOM_Y

CLOSE_SIZE = 0.016
TOP_MARGIN = 0.006 + CLOSE_SIZE + 0.004   # room left at the panel's top for the close button

# Two columns -- one per team (col 0 Radiant, col 1 Dire), see the module
# docstring. Row count (SHOPS_PER_COL) is not a fixed constant any more: it
# depends on how many shop categories the map's own script places on each
# side, only known once collect_catalog has parsed war3map.j -- see
# _geometry(), called from catalog_function() at inject time.
BLOCK_COLS = 3
HW_SHOP_MAX_SHOPS = 40     # sanity cap on radiant+dire combined, not a layout constraint
MARGIN_X = 0.007
COL_W = PANEL_W / BLOCK_COLS

HEADER_H = 0.007
HEADER_GAP = 0.0008
BLOCK_GAP = 0.002
BODY_H = PANEL_H - TOP_MARGIN

HW_SHOP_CELL_COLS = 4
HW_SHOP_CELLS = 12          # 4x3 grid per shop block, same as the map's own shop button grid
ICON_GAP = 0.0008

# Up to this many physical shop-building unit types per category (workshop.py
# shops()'s own unit-type codes -- 1 for almost every base shop, 2 for "Black
# Market" whose Radiant/Dire copies are distinct unit types).
HW_SHOP_BUILDING_CODES = 3

# Toggle button placed over the HUD's own "SHOP" command-card label. Anchored
# ABSOLUTELY on ORIGIN_FRAME_GAME_UI (not relative to the panel's right edge,
# see the module docstring for why that broke) at the HUD's "SHOP" label.
TOGGLE_X0 = 0.60
TOGGLE_Y0 = 0.215
TOGGLE_X1 = 0.66
TOGGLE_Y1 = 0.235
TOGGLE_W = TOGGLE_X1 - TOGGLE_X0
TOGGLE_H = TOGGLE_Y1 - TOGGLE_Y0
TOGGLE_ALPHA = 255   # 0-255; visible for now, to re-verify the anchor live (task)

PANEL_TEXTURE = 'UI\\\\Widgets\\\\ToolTips\\\\Human\\\\human-tooltip-background.blp'
BUTTON_TEXTURE = 'UI\\\\Widgets\\\\Console\\\\Human\\\\human-console-button-background.blp'


def _is_ascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def _geometry(shops_per_col: int) -> dict:
    """Block/icon sizes for a column that must fit `shops_per_col` blocks in
    BODY_H -- computed at inject time (once both team catalogs are built and
    the larger one's row count is known), not a fixed module constant like in
    v1-v4 (see the module docstring)."""
    shops_per_col = max(shops_per_col, 1)
    block_pitch = BODY_H / shops_per_col
    block_h = block_pitch - BLOCK_GAP
    grid_h = block_h - HEADER_H - HEADER_GAP
    grid_w_budget = COL_W - 2 * MARGIN_X
    icon_pitch = min(grid_h / 3.0, grid_w_budget / HW_SHOP_CELL_COLS)
    icon = icon_pitch - ICON_GAP
    header_w = icon_pitch * HW_SHOP_CELL_COLS
    return {'block_pitch': block_pitch, 'icon_pitch': icon_pitch, 'icon': icon, 'header_w': header_w}


GLOBALS = f"""// HW_SHOP_GLOBALS_BEGIN
constant integer HW_SHOP_MAX_SHOPS={HW_SHOP_MAX_SHOPS}
constant integer HW_SHOP_CELLS={HW_SHOP_CELLS}
constant integer HW_SHOP_CELL_COLS={HW_SHOP_CELL_COLS}
constant integer HW_SHOP_BUILDING_CODES={HW_SHOP_BUILDING_CODES}
integer array HW_shopUnitId
integer array HW_shopItemId
integer array HW_shopCost
string array HW_shopIcon
string array HW_shopName
string array HW_shopShopName
integer array HW_shopBuildingCode
integer array HW_shopTeamSide
integer array HW_shopCol
integer array HW_shopRow
integer array HW_shopPartBase
integer array HW_shopPartCount
integer array HW_shopPartCatIdx
integer array HW_shopPartUnitId
integer array HW_shopPartCost
string array HW_shopPartName
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
framehandle HW_shopDbg=null
framehandle HW_shopToggleText=null
real HW_shopRightX=0.8
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
    local integer base
    local integer cnt
    local integer k
    local integer total=0
    local integer catIdx
    local unit hero
    local unit shopUnit
    if idx<0 then
        return
    endif
    set cnt=HW_shopPartCount[idx]
    if cnt<=0 then
        call DisplayTextToPlayer(p,0,0,"|cffff6060HW Shop:|r "+HW_shopName[idx]+" has an empty parts table, purchase cancelled")
        return
    endif
    set base=HW_shopPartBase[idx]
    set hero=HW_ShopFindHero(p)
    if hero==null then
        call DisplayTextToPlayer(p,0,0,"|cffffcc00HW Shop:|r no hero found, purchase cancelled")
        return
    endif
    // 1) total cost of every orderable part (the clicked item plus its
    // recipe/component expansion, built at inject time -- see collect_catalog)
    set k=0
    loop
        exitwhen k>=cnt
        set total=total+HW_shopPartCost[base+k]
        set k=k+1
    endloop
    if GetPlayerState(p,PLAYER_STATE_RESOURCE_GOLD)<total then
        call DisplayTextToPlayer(p,0,0,"|cffff6060HW Shop:|r not enough gold for "+HW_shopName[idx]+" and its components ("+I2S(total)+"g needed), purchase cancelled")
        set hero=null
        return
    endif
    // 2) verify every part's shop building is reachable before spending anything
    // (prints the shop searched and, on failure, why the whole purchase is cancelled)
    set k=0
    loop
        exitwhen k>=cnt
        set catIdx=HW_shopPartCatIdx[base+k]
        set shopUnit=HW_ShopFindShopUnit(catIdx,GetUnitX(hero),GetUnitY(hero))
        if shopUnit==null then
            call DisplayTextToPlayer(p,0,0,"|cffffcc00HW Shop:|r skipped "+HW_shopPartName[base+k]+" -- no "+HW_shopShopName[catIdx]+" building found anywhere, purchase cancelled")
            set hero=null
            set shopUnit=null
            return
        endif
        set shopUnit=null
        set k=k+1
    endloop
    // 3) issue one real Sellunits order per part (recipe scroll + every component)
    set k=0
    loop
        exitwhen k>=cnt
        set catIdx=HW_shopPartCatIdx[base+k]
        set shopUnit=HW_ShopFindShopUnit(catIdx,GetUnitX(hero),GetUnitY(hero))
        call DisplayTextToPlayer(p,0,0,"HW Shop: order "+HW_shopShopName[catIdx]+" -> "+HW_shopPartName[base+k])
        call IssueNeutralImmediateOrderById(p,shopUnit,HW_shopPartUnitId[base+k])
        set k=k+1
    endloop
    call DisplayTextToPlayer(p,0,0,"|cff60ff60HW Shop:|r requested "+HW_shopName[idx]+" ("+I2S(total)+"g, "+I2S(cnt)+" part(s))")
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
function HW_ShopApplyTeamVisibility takes nothing returns nothing
    // Local-safe: every client computes its OWN answer from its OWN
    // GetLocalPlayer() and only ever feeds it into BlzFrameSetVisible (a pure
    // UI/client effect, never game state), exactly like HW_shopRightX's
    // client-width read above -- no handle is created here either, so, like
    // every other visibility toggle in this file, this cannot desync even
    // though each client ends up showing a different column.
    local boolean myRadiant=GetPlayerId(GetLocalPlayer())<=4
    local integer i=0
    local integer cellBase
    local integer j
    local boolean show
    loop
        exitwhen i>=HW_shopCount
        set show=(HW_shopTeamSide[i]==0)==myRadiant
        call BlzFrameSetVisible(HW_shopBlockHeader[i],show)
        set cellBase=i*HW_SHOP_CELLS
        set j=0
        loop
            exitwhen j>=HW_SHOP_CELLS
            if HW_shopCellBg[cellBase+j]!=null then
                call BlzFrameSetVisible(HW_shopCellBg[cellBase+j],show)
                call BlzFrameSetVisible(HW_shopCellBtn[cellBase+j],show)
            endif
            set j=j+1
        endloop
        set i=i+1
    endloop
endfunction
function HW_ShopBuild takes nothing returns nothing
    local framehandle ui=BlzGetOriginFrame(ORIGIN_FRAME_GAME_UI,0)
    local framehandle panelParent=BlzGetOriginFrame(HW_SHOP_PARENT_ORIGIN,0)
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
    set HW_shopPanel=BlzCreateFrameByType("BACKDROP","HWShopPanel",panelParent,"",0)
    // right screen edge in 4:3 frame coordinates depends on the client aspect ratio
    set HW_shopRightX=0.8
    if HW_SHOP_RIGHT_OVERRIDE>0.0 then
        set HW_shopRightX=HW_SHOP_RIGHT_OVERRIDE
    elseif HW_SHOP_RIGHT_OVERRIDE<0.0 then
        set HW_shopRightX=0.4+0.3*I2R(BlzGetLocalClientWidth())/I2R(BlzGetLocalClientHeight())
    endif
    call BlzFrameSetAbsPoint(HW_shopPanel,FRAMEPOINT_TOPRIGHT,HW_shopRightX,HW_SHOP_TOP_Y)
    call BlzFrameSetSize(HW_shopPanel,{PANEL_W:.6f},HW_SHOP_TOP_Y-HW_SHOP_BOTTOM_Y)
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
    set HW_shopDbg=BlzCreateFrameByType("TEXT","HWShopDbg",HW_shopPanel,"",0)
    call BlzFrameSetPoint(HW_shopDbg,FRAMEPOINT_TOPLEFT,HW_shopPanel,FRAMEPOINT_TOPLEFT,0.004,-0.004)
    call BlzFrameSetScale(HW_shopDbg,0.6)
    call BlzFrameSetText(HW_shopDbg,"client "+I2S(BlzGetLocalClientWidth())+"x"+I2S(BlzGetLocalClientHeight())+" right="+R2S(HW_shopRightX)+" slot="+I2S(GetPlayerId(GetLocalPlayer())))
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
    set HW_shopToggleText=BlzCreateFrameByType("TEXT","HWShopToggleText",HW_shopToggleBg,"",0)
    call BlzFrameSetAllPoints(HW_shopToggleText,HW_shopToggleBg)
    call BlzFrameSetTextAlignment(HW_shopToggleText,TEXT_JUSTIFY_MIDDLE,TEXT_JUSTIFY_CENTER)
    call BlzFrameSetText(HW_shopToggleText,"SHOP")
    set HW_shopToggleBtn=BlzCreateFrameByType("BUTTON","HWShopToggle",HW_shopToggleBg,"",0)
    call BlzFrameSetAllPoints(HW_shopToggleBtn,HW_shopToggleBg)
    set HW_shopToggleTrig=CreateTrigger()
    call BlzTriggerRegisterFrameEvent(HW_shopToggleTrig,HW_shopToggleBtn,FRAMEEVENT_CONTROL_CLICK)
    call TriggerAddAction(HW_shopToggleTrig,function HW_ShopToggleClick)
    set HW_shopSlotTrig=CreateTrigger()
    set i=0
    loop
        exitwhen i>=HW_shopCount
        set col=HW_shopCol[i]
        set row=HW_shopRow[i]
        set bx={MARGIN_X:.6f}+I2R(col)*{COL_W:.6f}
        set by=-{TOP_MARGIN:.6f}-I2R(row)*@@BLOCK_PITCH@@
        set HW_shopBlockHeader[i]=BlzCreateFrameByType("TEXT","HWShopBlockHeader",HW_shopPanel,"",0)
        // a scaled frame has its point offsets scaled as well: compensate
        call BlzFrameSetScale(HW_shopBlockHeader[i],0.55)
        call BlzFrameSetPoint(HW_shopBlockHeader[i],FRAMEPOINT_TOPLEFT,HW_shopPanel,FRAMEPOINT_TOPLEFT,bx/0.55,by/0.55)
        call BlzFrameSetSize(HW_shopBlockHeader[i],@@HEADER_W@@/0.55,{HEADER_H:.6f}/0.55)
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
                call BlzFrameSetPoint(HW_shopCellBg[cellBase+j],FRAMEPOINT_TOPLEFT,HW_shopPanel,FRAMEPOINT_TOPLEFT,bx+I2R(cc)*@@ICON_PITCH@@,by-{HEADER_H:.6f}-{HEADER_GAP:.6f}-I2R(rr)*@@ICON_PITCH@@)
                call BlzFrameSetSize(HW_shopCellBg[cellBase+j],@@ICON@@,@@ICON@@)
                call BlzFrameSetTexture(HW_shopCellBg[cellBase+j],HW_shopIcon[idx],0,true)
                set HW_shopCellBtn[cellBase+j]=BlzCreateFrameByType("BUTTON","HWShopCellBtn",HW_shopPanel,"",0)
                call BlzFrameSetPoint(HW_shopCellBtn[cellBase+j],FRAMEPOINT_TOPLEFT,HW_shopCellBg[cellBase+j],FRAMEPOINT_TOPLEFT,0,0)
                call BlzFrameSetSize(HW_shopCellBtn[cellBase+j],@@ICON@@,@@ICON@@)
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
    call HW_ShopApplyTeamVisibility()
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


def _match_by_norm(key: str, index: dict):
    """Exact-or-fuzzy lookup into a {normalized_name: value} index, same fuzzy
    rule as workshop.item_list (prefix match, only for keys of length >= 5, to
    avoid matching unrelated short names)."""
    if not key:
        return None
    if key in index:
        return index[key]
    for nk, v in index.items():
        if len(key) >= 5 and (nk.startswith(key) or key.startswith(nk)):
            return v
    return None


_NUM_TOKEN = re.compile(r'([+-])?\s*(\$[0-9A-Fa-f]+|\d+\.?\d*)')


def _eval_coord(expr: str) -> float | None:
    """Evaluate one CreateUnit coordinate argument as the decompiled war3map.j
    writes it: a plain decimal ('-6624', '7360.'), a hex literal ('$80',
    '$B4'), or a small constant-folded sum/difference of the two
    ('-6940+64', '5984+$80') -- only the sign of x/y matters here (side
    detection), so this only needs to get that right, not be a full
    expression evaluator."""
    expr = expr.strip()
    if not expr:
        return None
    total = 0.0
    matched = False
    for sign, tok in _NUM_TOKEN.findall(expr):
        matched = True
        v = float(int(tok[1:], 16)) if tok.startswith('$') else float(tok.rstrip('.') or '0')
        total += -v if sign == '-' else v
    return total if matched else None


def _shop_positions(script: str, code: str) -> list[tuple[float, float]]:
    """Every (x, y) this shop-building unit-type code is CreateUnit'd at in the
    decompiled war3map.j."""
    out = []
    for m in re.finditer(r"CreateUnit\([^,]+,\s*'" + re.escape(code) + r"'\s*,\s*([^,]+),\s*([^,]+)", script):
        x = _eval_coord(m.group(1))
        y = _eval_coord(m.group(2))
        if x is not None and y is not None:
            out.append((x, y))
    return out


def _shop_sides(script: str, codes: list[str]) -> set:
    """Which team base(s) a shop's own building code(s) are physically placed
    at, from the script's own CreateUnit coordinates (x<0,y<0 -> Radiant base,
    x>0,y>0 -> Dire base; a code placed at both, like nC38/n01K's Radiant AND
    Dire copies, belongs to both -- see the module docstring for why this,
    not a hardcoded per-shop table, is what fixes the composite-purchase
    bug)."""
    sides = set()
    for code in codes:
        for x, y in _shop_positions(script, code):
            if x < 0 and y < 0:
                sides.add('radiant')
            elif x > 0 and y > 0:
                sides.add('dire')
    return sides


def _build_parts(w, result: list[dict]) -> None:
    """Recipe/component expansion (built once, at inject time, in Python -- not
    at JASS runtime): for every catalog item, attach it['parts'] = a flat list
    of (cat_index, unit_code, cost, name) covering the item itself plus, if it
    is a recipe/composite item (matched against data/dota2_reference.json's
    "components"), every one of its components that is sold in a base shop of
    THIS SIDE's own catalog (`result` -- one team's catalog, see
    collect_catalog), recursively. A component only sold on the other team's
    exclusive shops, or in the secret (uC74) / side (u010/u00Z) shops, or not
    sold at all, is skipped, and one line naming it is printed (the task's
    requirement); it_dict['skipped'] also collects those lines for callers
    that want them without re-parsing stdout.

    Restricting the match to `result` (one side's own catalog, not the old
    flat union of both teams) is the actual fix for "composite purchase buys
    only the recipe scroll": see the module docstring for why matching across
    both teams let a part resolve to a shop the buying hero's team has no
    building near."""
    from workshop import norm, Workshop
    base_name = Workshop.item_base_name
    dota_items: dict = (w.dota2 or {}).get('items') or {}
    dota_by_norm = {}
    for dkey, dinfo in dota_items.items():
        n = norm(base_name(dinfo.get('name') or dkey))
        if n and n not in dota_by_norm:
            dota_by_norm[n] = dkey
    # every item sold anywhere in THIS side's catalog (already excludes the
    # secret/side shops and the other team's exclusive shops)
    name_index = {}
    for ci, cat in enumerate(result):
        for it in cat['items']:
            n = norm(base_name(it['name']))
            if n and n not in name_index:
                name_index[n] = (ci, it)
    # items sold ONLY in the secret/side shops, for the skip message
    secret_side_norm = set()
    for shop in w.shops():
        if shop['code'] not in ('uC74', 'u010', 'u00Z'):
            continue
        for u in shop['units']:
            n = norm(base_name(w.name(u, 'UnitFunc')))
            if n:
                secret_side_norm.add(n)

    def map_components(unit_code: str) -> list:
        """Components from the map's own shop tooltip ('Requires:' section):
        'Ring of Basilius - 525 (Supportive Vestments)' -> 'Ring of Basilius'.
        The 'Recipe - N' line is the scroll the clicked entry itself sells."""
        tip = w.txt_value(unit_code, 'Ubertip', 'UnitFunc')[1] or ''
        i = tip.find('Requires')
        if i < 0: return None
        body = tip[i:]
        j = body.find('Total Cost')
        if j > 0: body = body[:j]
        body = re.sub(r'\|c[0-9a-fA-F]{8}|\|r', '', body).replace('|n', '\n')
        comps = []; has_recipe = False
        for line in body.split('\n')[1:]:
            line = line.strip()
            m = re.match(r'^(.+?)\s*-\s*\d+', line)
            if not m: continue
            name = m.group(1).strip()
            if name.lower() == 'recipe': has_recipe = True; continue
            comps.append(name)
        # an entry WITHOUT a recipe line is bought whole by one click (the shop hands
        # over the finished item, e.g. Ring of Basilius): never expand those
        return comps if has_recipe else []

    def expand(ci: int, it: dict, visited: set, skipped: list) -> list:
        parts = [(ci, it['unit'], it['cost'], it['name'])]
        comps = map_components(it['unit'])
        if comps is None:
            dkey = _match_by_norm(norm(base_name(it['name'])), dota_by_norm)
            if dkey is None: return parts
            comps = [(dota_items.get(k) or {}).get('name') or k for k in dota_items.get(dkey, {}).get('components') or []]
        key = norm(base_name(it['name']))
        if key in visited:
            return parts
        visited.add(key)
        for comp_name in comps:
            found = _match_by_norm(norm(base_name(comp_name)), name_index)
            if found is None:
                cn = norm(base_name(comp_name))
                where = 'secret/side shop only' if _match_by_norm(cn, {k: True for k in secret_side_norm}) else 'not sold on this team (or this map)'
                msg = f"    skipped component '{comp_name}' of '{it['name']}' ({where})"
                skipped.append(msg)
                continue
            fci, fit = found
            parts.extend(expand(fci, fit, visited, skipped))
        return parts

    for ci, cat in enumerate(result):
        for it in cat['items']:
            it['parts'] = expand(ci, it, set(), it.setdefault('skipped', []))


def collect_catalog(w) -> dict:
    """Base shop categories -> items to sell, built from workshop.py's own reading
    of the map (shops()/item_list()/icon_info(), and ItemData/UnitBalance goldcost,
    Buttonpos for grid placement), split into two team-scoped catalogs.

    Returns {'radiant': [...], 'dire': [...]} -- see the module docstring for
    why a single flat catalog (v1-v4) is wrong: it duplicated the two side-
    flavoured shops for both teams and let composite items resolve components
    to a shop the buying hero's team has no building near. Each side's list
    only contains categories whose building has at least one CreateUnit
    placement on that side (`_shop_sides`); a category placed on both sides
    (most base shops, e.g. Weapons Dealer/n01K) appears, independently, in
    both.

    Secret shop (uC74) and side shops (u010, u00Z) are excluded on purpose
    (they stay clickable buildings, per docs/SHOP_UI_PLAN.md §4 step 7) -- so
    they are not purchasable from this panel either. Shops that share a name
    (Radiant/Dire "Black Market") are folded into one category, but their
    (possibly distinct) building unit-type codes are all kept
    (cat['shop_codes']) -- the purchase handler needs every physical building
    type that can sell this catalog to find the correct live unit to issue
    the sell order on (see the module docstring)."""
    excluded = {'uC74', 'u010', 'u00Z'}
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
    for i, cat in enumerate(result, 1):
        # The map's *.txt files mix latin1/cp1251 encodings; a non-ASCII shop-unit
        # name would render as "????????" in the client's font, so fall back to a
        # plain, always-displayable category label (docs/SHOP_UI_NOTES.md).
        if not _is_ascii(cat['name']):
            cat['name'] = f'Shop {i}'
        if len(cat['shop_codes']) > HW_SHOP_BUILDING_CODES:
            raise ValueError(f"shop {cat['name']!r} has {len(cat['shop_codes'])} building codes, "
                              f'HW_SHOP_BUILDING_CODES={HW_SHOP_BUILDING_CODES} is too small')
        cat['sides'] = _shop_sides(w.script, cat['shop_codes'])
        if not cat['sides']:
            print(f"WARNING: shop {cat['name']!r} ({','.join(cat['shop_codes'])}) has no CreateUnit "
                  f"placement at x<0,y<0 or x>0,y>0 in war3map.j -- showing on both teams as a fallback")
            cat['sides'] = {'radiant', 'dire'}
    radiant = [copy.deepcopy(c) for c in result if 'radiant' in c['sides']]
    dire = [copy.deepcopy(c) for c in result if 'dire' in c['sides']]
    _build_parts(w, radiant)
    _build_parts(w, dire)
    for side_cats in (radiant, dire):
        for cat in side_cats:
            cat['cells'] = _place_cells(cat['items'])
        if len(side_cats) > HW_SHOP_MAX_SHOPS:
            raise ValueError(f'{len(side_cats)} shop categories on one side, HW_SHOP_MAX_SHOPS={HW_SHOP_MAX_SHOPS} is too small')
    return {'radiant': radiant, 'dire': dire}


def parts_report(catalog: dict) -> str:
    """Human-readable summary of the recipe/component expansion, for the
    inject-time (no --apply) shop-ui command output (task requirement):
    how many items across both catalogs resolved >=2 parts, and up to 5
    examples (Vladmir's Offering and Battle Fury preferred if present)."""
    multi = []
    for side in ('radiant', 'dire'):
        for cat in catalog.get(side, []):
            for it in cat['items']:
                parts = it.get('parts') or []
                if len(parts) >= 2:
                    multi.append((side, cat['name'], it))
    lines = [f'Составных товаров (>=2 частей): {len(multi)}']
    highlight = ('vladmir', 'battle fury')
    examples = []
    seen = set()
    for want_highlight in (True, False):
        for side, catname, it in multi:
            if len(examples) >= 5:
                break
            if it['name'] in seen:
                continue
            is_hl = any(h in it['name'].lower() for h in highlight)
            if is_hl != want_highlight:
                continue
            examples.append((side, catname, it))
            seen.add(it['name'])
    for side, catname, it in examples:
        names = ', '.join(p[3] for p in it['parts'])
        lines.append(f"  [{side:7s}] {it['name']:28s} ({catname}) {len(it['parts'])} частей: {names}")
    return '\n'.join(lines)


def catalog_function(catalog: dict) -> tuple:
    """JASS function filling the HW_shop* arrays from the two Python-built team
    catalogs (see collect_catalog). Returns (jass_text, geometry) -- geometry
    is the dict from _geometry(), sized to the larger side's category count,
    needed by inject() to size the panel's blocks/icons.

    Categories are laid out flat as radiant + dire (Radiant's own indices
    first, Dire's follow, shifted by len(radiant)); HW_shopCol/HW_shopRow are
    precomputed here (col 0/row i for Radiant, col 1/row i for Dire) so
    HW_ShopBuild only ever reads them, it does not compute layout arithmetic
    from a single linear index any more (that was v1-v4's approach, dropped
    because "how many go per column" is no longer a fixed constant -- see the
    module docstring)."""
    radiant = catalog['radiant']
    dire = catalog['dire']
    combined = radiant + dire
    r_count = len(radiant)
    lines = ['function HW_ShopDataInit takes nothing returns nothing']
    part_idx = 0
    for ci, cat in enumerate(combined):
        side = 0 if ci < r_count else 1
        local_i = ci if ci < r_count else ci - r_count
        # only one team's blocks are visible on a client, so both teams share the
        # same grid: BLOCK_COLS columns, blocks filled column by column
        per_col = max(1, -(-max(r_count, len(dire)) // BLOCK_COLS))
        lines.append(f'    set HW_shopShopName[{ci}]="{_jass_string(cat["name"])}"')
        lines.append(f'    set HW_shopTeamSide[{ci}]={side}')
        lines.append(f'    set HW_shopCol[{ci}]={local_i // per_col}')
        lines.append(f'    set HW_shopRow[{ci}]={local_i % per_col}')
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
            parts = it.get('parts') or [(ci, it['unit'], it['cost'], it['name'])]
            lines.append(f'    set HW_shopPartBase[{idx}]={part_idx}')
            lines.append(f'    set HW_shopPartCount[{idx}]={len(parts)}')
            for pcat, punit, pcost, pname in parts:
                # pcat is local to this item's own side's catalog (0-based); dire's
                # need shifting into the combined flat index space (see above)
                real_cat = pcat if ci < r_count else pcat + r_count
                lines.append(f"    set HW_shopPartCatIdx[{part_idx}]={real_cat}")
                lines.append(f"    set HW_shopPartUnitId[{part_idx}]='{punit}'")
                lines.append(f'    set HW_shopPartCost[{part_idx}]={pcost}')
                lines.append(f'    set HW_shopPartName[{part_idx}]="{_jass_string(pname)}"')
                part_idx += 1
    lines.append(f'    set HW_shopCount={len(combined)}')
    lines.append('endfunction')
    shops_per_col = max(1, -(-max(r_count, len(dire)) // BLOCK_COLS))
    geo = _geometry(shops_per_col)
    geo.update(shops_per_col=shops_per_col, count_radiant=r_count, count_dire=len(dire))
    return '\n'.join(lines), geo


def inject(script: str, catalog: dict, right: float = 0.0, top: float = None, bottom: float = None, parent: str = 'gameui') -> str:
    """Return the script with the shop-window block added (idempotent). Coexists
    with the HW_COOLDOWN_* block; both are spliced the same way (globals appended
    to the first `globals` block, functions right before `main`, one call at the
    end of `main`)."""
    import re
    radiant = catalog.get('radiant') or []
    dire = catalog.get('dire') or []
    if not radiant and not dire:
        raise ValueError('empty shop catalog (both teams)')
    if len(radiant) + len(dire) > HW_SHOP_MAX_SHOPS:
        raise ValueError(f'{len(radiant) + len(dire)} shop categories, HW_SHOP_MAX_SHOPS={HW_SHOP_MAX_SHOPS} is too small')
    script = remove(script)
    data_func, geo = catalog_function(catalog)
    funcs = (FUNCTIONS.replace('// HW_SHOP_BEGIN', '// HW_SHOP_BEGIN\n' + data_func)
             .replace('HW_SHOP_PARENT_ORIGIN', 'ORIGIN_FRAME_WORLD_FRAME' if parent == 'world' else 'ORIGIN_FRAME_GAME_UI')
             .replace('HW_SHOP_RIGHT_OVERRIDE', f'{right:.6f}')
             .replace('HW_SHOP_TOP_Y', f'{(top if top is not None else PANEL_TOP_Y):.6f}')
             .replace('HW_SHOP_BOTTOM_Y', f'{(bottom if bottom is not None else PANEL_BOTTOM_Y):.6f}')
             .replace('@@BLOCK_PITCH@@', f"{geo['block_pitch']:.6f}")
             .replace('@@ICON_PITCH@@', f"{geo['icon_pitch']:.6f}")
             .replace('@@ICON@@', f"{geo['icon']:.6f}")
             .replace('@@HEADER_W@@', f"{geo['header_w']:.6f}"))
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
