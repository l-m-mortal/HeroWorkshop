"""JASS block that draws numeric cooldowns over the 12 command buttons (Warcraft III 1.31+).

Injected into war3map.j by `map_fix.py cooldown-numbers`. Pure JASS, no vJASS.
Text frames are created once, a 0.1 s timer updates them for the unit the
local player selected last. Frames are client-side only, so this cannot desync.
"""
GLOBALS = """// HW_COOLDOWN_GLOBALS_BEGIN
framehandle array HW_cdText
integer array HW_cdIds
integer array HW_cdPos
integer HW_cdIdCount=0
integer array HW_cdUnitIds
integer array HW_cdUnitPos
integer HW_cdUnitN=0
integer HW_cdTicks=0
unit HW_cdUnit=null
group HW_cdGroup=null
timer HW_cdTimer=null
framehandle HW_cdDebug=null
boolean HW_cdIsDebug=false
// HW_COOLDOWN_GLOBALS_END"""

# 1.31 has no BlzGetAbilityId, so the unit's abilities are found by probing a
# generated list of every hero ability id of this map with GetUnitAbilityLevel
# (unlearned hero abilities have level 0 and are skipped; rescanned every 0.5 s).
FUNCTIONS = """// HW_COOLDOWN_BEGIN
function HW_cdFormat takes real r returns string
    local integer whole
    local integer tenth
    if r>=10.0 then
        return I2S(R2I(r+0.99))
    endif
    set whole=R2I(r)
    set tenth=R2I(r*10.0)-whole*10
    return I2S(whole)+"."+I2S(tenth)
endfunction
function HW_cdScan takes nothing returns nothing
    local integer i=0
    set HW_cdUnitN=0
    if HW_cdUnit==null then
        return
    endif
    loop
        exitwhen i>=HW_cdIdCount
        if GetUnitAbilityLevel(HW_cdUnit,HW_cdIds[i])>0 then
            set HW_cdUnitIds[HW_cdUnitN]=HW_cdIds[i]
            set HW_cdUnitPos[HW_cdUnitN]=HW_cdPos[i]
            set HW_cdUnitN=HW_cdUnitN+1
        endif
        set i=i+1
    endloop
endfunction
function HW_cdPick takes nothing returns nothing
    // The local player's current selection (client side only; frames are local too).
    local unit u
    call GroupClear(HW_cdGroup)
    call GroupEnumUnitsSelected(HW_cdGroup,GetLocalPlayer(),null)
    set u=FirstOfGroup(HW_cdGroup)
    if u!=HW_cdUnit then
        set HW_cdUnit=u
        call HW_cdScan()
    endif
    set u=null
endfunction
function HW_cdTick takes nothing returns nothing
    local integer i=0
    local integer idx
    local real r
    local string dbg
    set HW_cdTicks=HW_cdTicks+1
    if HW_cdTicks>=5 then
        set HW_cdTicks=0
        call HW_cdPick()
        call HW_cdScan()
    endif
    loop
        exitwhen i>11
        if HW_cdText[i]!=null then
            if HW_cdIsDebug then
                call BlzFrameSetText(HW_cdText[i],I2S(i))
                call BlzFrameSetVisible(HW_cdText[i],true)
            else
                call BlzFrameSetVisible(HW_cdText[i],false)
            endif
        endif
        set i=i+1
    endloop
    if HW_cdUnit==null then
        if HW_cdDebug!=null then
            call BlzFrameSetText(HW_cdDebug,"HW cd: nothing selected")
        endif
        return
    endif
    if GetUnitTypeId(HW_cdUnit)==0 then
        set HW_cdUnit=null
        return
    endif
    set dbg="HW cd: "+GetUnitName(HW_cdUnit)+" abils="+I2S(HW_cdUnitN)
    if HW_cdIsDebug then
        set dbg=dbg+" vis="
        set i=0
        loop
            exitwhen i>11
            if BlzFrameIsVisible(BlzGetOriginFrame(ORIGIN_FRAME_COMMAND_BUTTON,i)) then
                set dbg=dbg+"1"
            else
                set dbg=dbg+"0"
            endif
            set i=i+1
        endloop
    endif
    set i=0
    loop
        exitwhen i>=HW_cdUnitN
        set r=BlzGetUnitAbilityCooldownRemaining(HW_cdUnit,HW_cdUnitIds[i])
        if r>0.05 then
            set idx=HW_cdUnitPos[i]
            set dbg=dbg+" ["+I2S(idx)+"]="+HW_cdFormat(r)
            if idx>=0 and idx<=11 then
                if HW_cdText[idx]!=null then
                    call BlzFrameSetText(HW_cdText[idx],HW_cdFormat(r))
                    call BlzFrameSetVisible(HW_cdText[idx],true)
                endif
            endif
        endif
        set i=i+1
    endloop
    if HW_cdDebug!=null then
        call BlzFrameSetText(HW_cdDebug,dbg)
    endif
endfunction
function HW_cdInit takes nothing returns nothing
    local integer i=0
    local framehandle btn
    local framehandle ui=BlzGetOriginFrame(ORIGIN_FRAME_GAME_UI,0)
    call HW_cdIdsInit()
    set HW_cdGroup=CreateGroup()
    loop
        exitwhen i>11
        set btn=BlzGetOriginFrame(ORIGIN_FRAME_COMMAND_BUTTON,i)
        if btn!=null then
            set HW_cdText[i]=BlzCreateFrameByType("TEXT","HWcd",HW_CD_PARENT,"",0)
            call BlzFrameSetPoint(HW_cdText[i],FRAMEPOINT_CENTER,btn,FRAMEPOINT_CENTER,0.0,0.0)
            call BlzFrameSetTextAlignment(HW_cdText[i],TEXT_JUSTIFY_MIDDLE,TEXT_JUSTIFY_CENTER)
            call BlzFrameSetScale(HW_cdText[i],HW_CD_SCALE)
            call BlzFrameSetVisible(HW_cdText[i],false)
        endif
        set i=i+1
    endloop
    if HW_cdIsDebug then
        set HW_cdDebug=BlzCreateFrameByType("TEXT","HWcdDebug",ui,"",0)
        call BlzFrameSetAbsPoint(HW_cdDebug,FRAMEPOINT_TOP,0.4,0.56)
        call BlzFrameSetText(HW_cdDebug,"HW cd: init ok")
    endif
    set HW_cdTimer=CreateTimer()
    call TimerStart(HW_cdTimer,0.1,true,function HW_cdTick)
    set btn=null
    set ui=null
endfunction
function HW_cdStart takes nothing returns nothing
    call DestroyTimer(GetExpiredTimer())
    call HW_cdInit()
endfunction
// HW_COOLDOWN_END"""

def ids_function(ids, positions=None) -> str:
    """JASS function filling HW_cdIds with the map's hero ability rawcodes and
    HW_cdPos with each ability's command-card slot (y*4+x, -1 = unknown)."""
    positions = positions or {}
    lines = ['function HW_cdIdsInit takes nothing returns nothing']
    for i, code in enumerate(ids):
        lines.append(f"    set HW_cdIds[{i}]='{code}'")
        lines.append(f"    set HW_cdPos[{i}]={positions.get(code, -1)}")
    lines.append(f'    set HW_cdIdCount={len(ids)}')
    lines.append('endfunction')
    return '\n'.join(lines)

MAIN_CALL = "call TimerStart(CreateTimer(),1.0,false,function HW_cdStart) // HW_COOLDOWN_CALL"

def inject(script: str, ids, font_height: float = 0.016, positions=None, parent: str = 'gameui', debug: bool = False) -> str:
    """Return the script with the cooldown block added (idempotent).

    parent: 'gameui' anchors the text frames to the game UI (positioned over the
    command buttons); 'button' makes them children of the command buttons.
    debug: show slot numbers on every button and a status line at the top."""
    import re
    ids = [c for c in ids if re.match(r'^[0-9A-Za-z]{4}$', c)]
    if not ids: raise ValueError('no ability ids')
    script = remove(script)
    funcs = (FUNCTIONS.replace('HW_CD_SCALE', f'{max(0.5, font_height / 0.01):.2f}')
             .replace('HW_CD_PARENT', 'ui' if parent == 'gameui' else 'btn')
             .replace('// HW_COOLDOWN_BEGIN', '// HW_COOLDOWN_BEGIN\n' + ids_function(ids, positions)))
    globals_block = GLOBALS.replace('boolean HW_cdIsDebug=false', f'boolean HW_cdIsDebug={"true" if debug else "false"}')
    # globals: append to the first globals block
    g = re.search(r'^globals\r?\n', script, re.M)
    if not g: raise ValueError('globals block not found')
    end = script.index('endglobals', g.end())
    eol = '\r\n' if '\r\n' in script[:2000] else '\n'
    script = script[:end] + globals_block.replace('\n', eol) + eol + script[end:]
    # functions: right before main
    m = re.search(r'^function main takes nothing returns nothing\r?\n', script, re.M)
    if not m: raise ValueError('function main not found')
    script = script[:m.start()] + funcs.replace('\n', eol) + eol + script[m.start():]
    # call: as the last statement of main
    m = re.search(r'^function main takes nothing returns nothing\r?\n', script, re.M)
    e = re.search(r'^endfunction', script[m.end():], re.M)
    pos = m.end() + e.start()
    script = script[:pos] + MAIN_CALL + eol + script[pos:]
    return script

def remove(script: str) -> str:
    import re
    script = re.sub(r'// HW_COOLDOWN_GLOBALS_BEGIN.*?// HW_COOLDOWN_GLOBALS_END\r?\n', '', script, flags=re.S)
    script = re.sub(r'// HW_COOLDOWN_BEGIN.*?// HW_COOLDOWN_END\r?\n', '', script, flags=re.S)
    script = re.sub(r'^.*// HW_COOLDOWN_CALL\r?\n', '', script, flags=re.M)
    return script
