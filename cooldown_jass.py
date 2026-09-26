"""JASS block that draws numeric cooldowns over the 12 command buttons (Warcraft III 1.31+).

Injected into war3map.j by `map_fix.py cooldown-numbers`. Pure JASS, no vJASS.
Text frames are created once, a 0.1 s timer updates them for the unit the
local player selected last. Frames are client-side only, so this cannot desync.
"""
GLOBALS = """// HW_COOLDOWN_GLOBALS_BEGIN
framehandle array HW_cdText
unit HW_cdUnit=null
trigger HW_cdSel=null
timer HW_cdTimer=null
// HW_COOLDOWN_GLOBALS_END"""

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
function HW_cdSelect takes nothing returns boolean
    if GetTriggerPlayer()==GetLocalPlayer() then
        set HW_cdUnit=GetTriggerUnit()
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
    set i=0
    loop
        set a=BlzGetUnitAbilityByIndex(HW_cdUnit,i)
        exitwhen a==null
        set r=BlzGetUnitAbilityCooldownRemaining(HW_cdUnit,BlzGetAbilityId(a))
        if r>0.05 then
            set idx=BlzGetAbilityIntegerField(a,ABILITY_IF_BUTTON_POSITION_NORMAL_Y)*4+BlzGetAbilityIntegerField(a,ABILITY_IF_BUTTON_POSITION_NORMAL_X)
            if idx>=0 and idx<=11 then
                call BlzFrameSetText(HW_cdText[idx],HW_cdFormat(r))
                call BlzFrameSetVisible(HW_cdText[idx],true)
            endif
        endif
        set i=i+1
    endloop
    set a=null
endfunction
function HW_cdInit takes nothing returns nothing
    local integer i=0
    local framehandle btn
    loop
        exitwhen i>11
        set btn=BlzGetOriginFrame(ORIGIN_FRAME_COMMAND_BUTTON,i)
        set HW_cdText[i]=BlzCreateFrameByType("TEXT","HWcd",btn,"",0)
        call BlzFrameSetPoint(HW_cdText[i],FRAMEPOINT_CENTER,btn,FRAMEPOINT_CENTER,0.0,0.0)
        call BlzFrameSetTextAlignment(HW_cdText[i],TEXT_JUSTIFY_CENTER)
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

MAIN_CALL = "call TimerStart(CreateTimer(),0.0,false,function HW_cdStart) // HW_COOLDOWN_CALL"

def inject(script: str, font_height: float = 0.016) -> str:
    """Return the script with the cooldown block added (idempotent)."""
    import re
    script = remove(script)
    funcs = FUNCTIONS.replace('HW_CD_FONT', f'{font_height:.4f}')
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
