"""JASS block that draws numeric cooldowns over the 12 command buttons (Warcraft III 1.31+).

Injected into war3map.j by `map_fix.py cooldown-numbers`. Pure JASS, no vJASS.
Text frames are created once, a 0.1 s timer updates them for the unit the
local player selected last. Frames are client-side only, so this cannot desync.
"""
GLOBALS = """// HW_COOLDOWN_GLOBALS_BEGIN
framehandle array HW_cdText
integer array HW_cdIds
integer HW_cdIdCount=0
integer array HW_cdUnitIds
integer HW_cdUnitN=0
integer HW_cdTicks=0
unit HW_cdUnit=null
trigger HW_cdSel=null
timer HW_cdTimer=null
// HW_COOLDOWN_GLOBALS_END"""

# 1.31 has no BlzGetAbilityId, so the unit's abilities are found by probing a
# generated list of every hero ability id of this map with BlzGetUnitAbility.
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
        if BlzGetUnitAbility(HW_cdUnit,HW_cdIds[i])!=null then
            set HW_cdUnitIds[HW_cdUnitN]=HW_cdIds[i]
            set HW_cdUnitN=HW_cdUnitN+1
        endif
        set i=i+1
    endloop
endfunction
function HW_cdSelect takes nothing returns boolean
    if GetTriggerPlayer()==GetLocalPlayer() then
        set HW_cdUnit=GetTriggerUnit()
        call HW_cdScan()
    endif
    return false
endfunction
function HW_cdTick takes nothing returns nothing
    local integer i=0
    local integer idx
    local real r
    local ability a
    loop
        exitwhen i>11
        call BlzFrameSetVisible(HW_cdText[i],false)
        set i=i+1
    endloop
    if HW_cdUnit==null then
        return
    endif
    if GetUnitTypeId(HW_cdUnit)==0 then
        set HW_cdUnit=null
        return
    endif
    set HW_cdTicks=HW_cdTicks+1
    if HW_cdTicks>=10 then
        set HW_cdTicks=0
        call HW_cdScan()
    endif
    set i=0
    loop
        exitwhen i>=HW_cdUnitN
        set r=BlzGetUnitAbilityCooldownRemaining(HW_cdUnit,HW_cdUnitIds[i])
        if r>0.05 then
            set a=BlzGetUnitAbility(HW_cdUnit,HW_cdUnitIds[i])
            if a!=null then
                set idx=BlzGetAbilityIntegerField(a,ABILITY_IF_BUTTON_POSITION_NORMAL_Y)*4+BlzGetAbilityIntegerField(a,ABILITY_IF_BUTTON_POSITION_NORMAL_X)
                if idx>=0 and idx<=11 then
                    call BlzFrameSetText(HW_cdText[idx],HW_cdFormat(r))
                    call BlzFrameSetVisible(HW_cdText[idx],true)
                endif
            endif
        endif
        set i=i+1
    endloop
    set a=null
endfunction
function HW_cdInit takes nothing returns nothing
    local integer i=0
    local framehandle btn
    call HW_cdIdsInit()
    loop
        exitwhen i>11
        set btn=BlzGetOriginFrame(ORIGIN_FRAME_COMMAND_BUTTON,i)
        set HW_cdText[i]=BlzCreateFrameByType("TEXT","HWcd",btn,"",0)
        call BlzFrameSetPoint(HW_cdText[i],FRAMEPOINT_CENTER,btn,FRAMEPOINT_CENTER,0.0,0.0)
        call BlzFrameSetTextAlignment(HW_cdText[i],TEXT_JUSTIFY_MIDDLE,TEXT_JUSTIFY_CENTER)
        call BlzFrameSetFont(HW_cdText[i],"Fonts\\\\FRIZQT__.TTF",HW_CD_FONT,0)
        call BlzFrameSetTextColor(HW_cdText[i],BlzConvertColor(255,255,255,255))
        call BlzFrameSetLevel(HW_cdText[i],5)
        call BlzFrameSetVisible(HW_cdText[i],false)
        set i=i+1
    endloop
    set HW_cdSel=CreateTrigger()
    set i=0
    loop
        exitwhen i>=bj_MAX_PLAYER_SLOTS
        call TriggerRegisterPlayerUnitEvent(HW_cdSel,Player(i),EVENT_PLAYER_UNIT_SELECTED,null)
        set i=i+1
    endloop
    call TriggerAddCondition(HW_cdSel,Condition(function HW_cdSelect))
    set HW_cdTimer=CreateTimer()
    call TimerStart(HW_cdTimer,0.1,true,function HW_cdTick)
    set btn=null
endfunction
function HW_cdStart takes nothing returns nothing
    call DestroyTimer(GetExpiredTimer())
    call HW_cdInit()
endfunction
// HW_COOLDOWN_END"""

def ids_function(ids) -> str:
    """JASS function filling HW_cdIds with the map's hero ability rawcodes."""
    lines = ['function HW_cdIdsInit takes nothing returns nothing']
    for i, code in enumerate(ids):
        lines.append(f"    set HW_cdIds[{i}]='{code}'")
    lines.append(f'    set HW_cdIdCount={len(ids)}')
    lines.append('endfunction')
    return '\n'.join(lines)

MAIN_CALL = "call TimerStart(CreateTimer(),0.0,false,function HW_cdStart) // HW_COOLDOWN_CALL"

def inject(script: str, ids, font_height: float = 0.016) -> str:
    """Return the script with the cooldown block added (idempotent)."""
    import re
    ids = [c for c in ids if re.match(r'^[0-9A-Za-z]{4}$', c)]
    if not ids: raise ValueError('no ability ids')
    script = remove(script)
    funcs = FUNCTIONS.replace('HW_CD_FONT', f'{font_height:.4f}').replace('// HW_COOLDOWN_BEGIN', '// HW_COOLDOWN_BEGIN\n' + ids_function(ids))
    # globals: append to the first globals block
    g = re.search(r'^globals\r?\n', script, re.M)
    if not g: raise ValueError('globals block not found')
    end = script.index('endglobals', g.end())
    eol = '\r\n' if '\r\n' in script[:2000] else '\n'
    script = script[:end] + GLOBALS.replace('\n', eol) + eol + script[end:]
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
