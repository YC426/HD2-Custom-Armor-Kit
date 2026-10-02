-- Read-only ship visibility gate. The host supplies a build-verified reader;
-- this module never scans, writes, or calls native game functions.
--
-- 2.5.7 revision. The 2.5.6 gate hard-required GameSession.in_session()==true.
-- That function is best-effort everywhere else in this installation (the HUD
-- overlay skips it when absent, the EXO launcher skips it on error), so a
-- build where it answers false on the ship hid the panel for the whole
-- session: multi_perk's own config logic arms the panel only while
-- M.ship_ok, so one wrong signal made the mod permanently invisible
-- (MultiPerk.log 2026-10-01T09:59:23Z "ui gate blocked ... frame=2" and no
-- further gate line for the rest of the run).
--
-- The gate now reports every fact it observed through a second return value
-- and only treats the world/UI facts as authoritative. It can also run in
-- fallback mode, where native UI idle plus the three live ship markers stand
-- in for the session flag; the host must latch that authorization itself and
-- drop it on a scene/marker change (see multi_perk.lua may_show_panel).
local ShipVisibility = {}
ShipVisibility.game_sha256 = '2E2C3B7C2500646DADD5F2B4C6E0504DBB7E7896139F64CDDC0D1813C718F51E'
ShipVisibility.exe_sha256 = 'F5FEE03DCFDB2E553A4752C283590950AC13316B376D8196AA556FF0400D5F06'
local UI_GLOBAL_RVA, UI_STATE_OFFSET = 0x347ce28, 0x4294
local SHIP_MARKERS = {'be0be6b1875a4a66','ce2566805c9e893a','3b9bcf29e38da0a6'}
local function u32(s,o)
    if type(s)~='string' or #s<o+4 then return nil end
    local a,b,c,d=s:byte(o+1,o+4)
    return a+b*256+c*65536+d*16777216
end
local function pointer(s)
    local lo,hi=u32(s,0),u32(s,4)
    if not lo or not hi then return nil end
    local p=lo+hi*4294967296
    if p<65536 or p>=0x800000000000 then return nil end
    return p
end
function ShipVisibility.new(engine,bridge,options)
    local marker_ids
    local ui_global
    local escape_only=type(options)=='table' and options.escape_only==true
    local escape_run=0
    -- session_required=false lets the host use "native UI idle plus the three
    -- live ship markers" as the authorization when the session helper is not
    -- available (missing, raising, or answering nil). An explicit false from
    -- GameSession.in_session() is never overridden here; the host decides that
    -- with its own latch and config, so a broken session helper cannot silently
    -- turn the title screen into a ship scene.
    local session_required=true
    if type(options)=='table' and options.session_required~=nil then
        session_required=options.session_required~=false
    end
    -- world_scope='main' (default) reads only Application.main_world(). The live
    -- 2.5.7 log proved that assumption wrong on this build: with a real session
    -- and in_session()==true, the main world held 0 of the 3 ship markers for
    -- 18,000+ frames (MultiPerk.log 2026-10-01T11:13:56Z onward), so the panel
    -- was hidden for the whole run. world_scope='any' searches the bounded
    -- Application.worlds() list for the one world that actually carries all
    -- three marker resources with live units - the same scene predicate, just
    -- without assuming which world the engine calls "main".
    local world_scope='main'
    if type(options)=='table' and type(options.world_scope)=='string' then
        world_scope=options.world_scope
    end
    local max_worlds=17
    if type(options)=='table' and type(options.max_worlds)=='number' then
        max_worlds=math.max(1,math.min(32,math.floor(options.max_worlds)))
    end
    local ship_world
    -- 2.5.8: the WORKING 2.5.5 build never used in_session / main_world /
    -- units_by_resource at all. Its ship test was the world COUNT: the ship
    -- runs 9+ worlds while the title screen has only a couple
    -- ("in-game gate: the ship runs 9+ worlds; the title screen only a couple").
    -- Every marker/in_session gate added from 2.5.6 on was built on an
    -- assumption this build does not satisfy, and hid the panel completely.
    -- world_scope='count' restores the proven signal; the marker and session
    -- predicates stay available behind world_scope='any'/'main'.
    local min_worlds=8
    if type(options)=='table' and type(options.min_worlds)=='number' then
        min_worlds=math.max(2,math.min(64,math.floor(options.min_worlds)))
    end
    -- Native screens the panel may stay visible under, by screen id. 'The
    -- native UI is busy' is ONE shared flag: it is raised by the armory, the
    -- hellpod loadout and the galactic war map alike, so relaxing it shows the
    -- panel in all three (2026-10-01 live regression) and it cannot be used to
    -- single out the armory. The per-screen id below can.
    -- The id stack lives at ui+0x429c: five 4-byte screen ids followed by the
    -- depth at ui+0x429c+20 (= ui+0x42b0, the 'depth' field read below). Two
    -- independent published mods read this exact block on this exact game
    -- build and both name screen 5 the armory and screen 14 the loadout.
    -- An empty list keeps the old behaviour exactly: every native screen hides
    -- the panel.
    local ui_allow={}
    if type(options)=='table' and type(options.ui_allow)=='table' then
        for _,id in ipairs(options.ui_allow) do
            if type(id)=='number' and id%1==0 and id>=0 and id<=255 then ui_allow[id]=true end
        end
    end
    -- marker_ids is only cached after a complete conversion; a partial cache
    -- would let a later sample read indexed resources with nil ids.
    local function marker_list()
        if marker_ids then return marker_ids end
        local converted={}
        for i,hash in ipairs(SHIP_MARKERS)do
            local id=engine.IdString64.from_hex(hash)
            if id==nil or id==false then return nil,'marker_id_unavailable' end
            converted[i]=id
        end
        marker_ids=converted
        return marker_ids
    end
    local function fail(info,reason)
        escape_run=0
        info.reason=reason
        if info.fields then info.fields.reason=reason end
        return false,reason,info.world
    end
    local function snapshot(info)
        local fields=info.fields or info
        local app,world,unit,ids,network,session = engine.Application,engine.World,
            engine.Unit,engine.IdString64,engine.Network,engine.GameSession
        if type(app)~='table' or type(app.main_world)~='function'
            or type(app.worlds)~='function' then return fail(info,'world_api_unavailable') end
        if type(world)~='table' or type(world.units_by_resource)~='function'
            or type(unit)~='table' or type(unit.alive)~='function' then
            return fail(info,'marker_api_unavailable')
        end
        if type(ids)~='table' or type(ids.from_hex)~='function' then
            return fail(info,'marker_id_unavailable')
        end
        if type(network)~='table' or type(network.game_session)~='function' then
            return fail(info,'session_api_unavailable')
        end
        local session_ok,session_object=pcall(network.game_session)
        if not session_ok or session_object==nil or session_object==false then
            -- A real session object is the only positive sign that the player
            -- is past the boot sequence at all.
            return fail(info,'not_in_session')
        end
        info.session=true
        fields.session=true
        local session_flag=nil
        if type(session)=='table' then
            if type(session.in_session)=='function' then
                local flag_ok,flag=pcall(session.in_session,session_object)
                if flag_ok then
                    if flag==true then
                        session_flag=true
                    elseif flag==false then
                        session_flag=false
                    end
                end
            end
        end
        info.in_session=session_flag
        info.session_required=session_required
        fields.in_session=session_flag
        fields.session_required=session_required
        if session_flag==false then
            if session_required then
                return fail(info,'not_in_session')
            end
        end
        info.fallback=(session_flag~=true)
        fields.fallback=info.fallback
        local list=marker_list()
        -- Verify the ship marker scene on one world. Returns nil on success, or
        -- the first reason it failed plus the marker counts it managed to read.
        local function scene(worlds_candidate)
            local counts={}
            if not list then return nil,counts end
            for index,id in ipairs(list)do
                local units_ok,units=pcall(world.units_by_resource,worlds_candidate,id)
                if not units_ok or type(units)~='table' or #units<1 or #units>16 then
                    return 'ship_marker_absent',counts
                end
                for _,object in ipairs(units)do
                    local alive_ok,alive=pcall(unit.alive,object)
                    if not alive_ok or alive~=true then return 'ship_marker_dead',counts end
                end
                counts[index]=#units
            end
            return nil,counts
        end
        -- Shared tail: the native build proof, the idle-UI read and the closing
        -- scene identity check. Both the world-count signal and the marker
        -- signals end here, so the safety checks cannot drift apart.
        local function finish(finfo,ffields,fscene_world,fmarkers)
            if type(bridge)~='table' or type(bridge.read)~='function'
                or type(bridge.verify)~='function' then return fail(finfo,'native_build_unverified') end
            local verify_ok,verified=pcall(bridge.verify)
            if not verify_ok or verified~=true then return fail(finfo,'native_build_unverified') end
            if bridge.game_sha256~=ShipVisibility.game_sha256
                or bridge.exe_sha256~=ShipVisibility.exe_sha256 then
                return fail(finfo,'native_build_unverified')
            end
            if type(bridge.base)~='number' or bridge.base<65536 then
                return fail(finfo,'native_base_unavailable')
            end
            local global=bridge.base+UI_GLOBAL_RVA
            local global_ok,global_bytes=pcall(bridge.read,global,8)
            if not global_ok or type(global_bytes)~='string' then
                return fail(finfo,'ui_unavailable')
            end
            local ui=pointer(global_bytes)
            if not ui then return fail(finfo,'ui_unavailable') end
            local state_ok,state=pcall(bridge.read,ui+UI_STATE_OFFSET,0x90)
            if not state_ok or type(state)~='string' or #state~=0x90 then
                return fail(finfo,'ui_unreadable')
            end
            local current,pending,depth=u32(state,0),u32(state,4),u32(state,0x1c)
            local secondary,secondary_pending=u32(state,0x84),u32(state,0x8c)
            -- The screen-id stack sits inside the same window we already read:
            -- five 4-byte ids at +8..+0x1b, the depth at +0x1c.
            local stack={}
            for index=0,4 do stack[index+1]=u32(state,8+4*index) end
            local screen=nil
            if depth and depth>=1 and depth<=#stack then screen=stack[depth] end
            finfo.ui={current=current,pending=pending,depth=depth,secondary=secondary,
                secondary_pending=secondary_pending,stack=stack,screen=screen}
            finfo.ui_idle=(current==0 and pending==0 and depth==0 and secondary==0
                and secondary_pending==0)
            ffields.ui=finfo.ui
            ffields.ui_idle=finfo.ui_idle
            ffields.ui_screen=screen
            ffields.ui_stack=stack
            ffields.marker_counts=fmarkers
            if depth>5 or secondary>25 then return fail(finfo,'ui_bounds_changed') end
            -- One named native screen may keep the panel (the armory, when the
            -- host asks for it); everything else hides it exactly as before.
            local allowed=(screen~=nil and ui_allow[screen]==true)
            local escape_menu_bytes,escape_screen_bytes,escape_tab
            if escape_only then
                if screen~=1 or pending~=0 or secondary~=0 or secondary_pending~=0 then
                    return fail(finfo,'escape_closed')
                end
                escape_menu_bytes=bridge.read(bridge.base+0x347ce38,8)
                local menu=pointer(escape_menu_bytes)
                escape_screen_bytes=menu and bridge.read(menu+200,8)
                local presenter=pointer(escape_screen_bytes)
                escape_tab=presenter and bridge.read(presenter+58700,4)
                if u32(escape_tab,0)~=0 then return fail(finfo,'escape_other_tab') end
                if bridge.read(bridge.base+0x347ce38,8)~=escape_menu_bytes
                    or bridge.read(menu+200,8)~=escape_screen_bytes
                    or bridge.read(presenter+58700,4)~=escape_tab then
                    return fail(finfo,'ui_transitioning')
                end
            end
            finfo.ui_screen_allowed=allowed
            ffields.ui_screen_allowed=allowed
            if not finfo.ui_idle and not allowed then return fail(finfo,'native_ui_busy') end
            local global_again_ok,global_again=pcall(bridge.read,global,8)
            local state_again_ok,state_again=pcall(bridge.read,ui+UI_STATE_OFFSET,0x90)
            if not global_again_ok or not state_again_ok
                or global_again~=global_bytes or state_again~=state then
                return fail(finfo,'ui_transitioning')
            end
            if ui_global and ui_global~=ui then return fail(finfo,'ui_presenter_changed') end
            ui_global=ui
            local session_ok2,session_again=pcall(network.game_session)
            if not session_ok2 or session_again~=session_object then
                return fail(finfo,'scene_transitioning')
            end
            -- Marker worlds are re-verified; a world-count scene has no marker
            -- scene to re-verify, so the count itself is re-read instead.
            if fscene_world~=nil then
                local reason2,counts2=scene(fscene_world)
                if reason2 and world_scope~='count' then return fail(finfo,reason2) end
                if not reason2 then
                    finfo.marker_counts=counts2
                    ffields.marker_counts=counts2
                end
            end
            finfo.world=fscene_world
            ffields.world=fscene_world
            if escape_only then
                escape_run=escape_run+1
                if escape_run<3 then
                    finfo.reason='escape_confirming'
                    ffields.reason=finfo.reason
                    return false
                end
            end
            -- A named native screen keeps its own reason, so the log always
            -- says WHY the panel stayed up instead of claiming a ship idle.
            -- The caller reads info.reason, not this return value, so it has to
            -- be stored on the info table as well.
            local reason=(allowed and ('ship_screen_'..tostring(screen)) or 'ship_idle')
            finfo.reason=reason
            ffields.reason=reason
            return true,reason
        end
        local worlds_ok,worlds=pcall(app.worlds)
        if not worlds_ok or type(worlds)~='table' then return fail(info,'worlds_unavailable') end
        fields.worlds_total=#worlds
        -- The proven 2.5.5 signal, checked before anything that depends on
        -- Application.main_world(): the ship's world list is far larger than
        -- the title screen's.
        if world_scope=='count' then
            if #worlds<min_worlds then
                info.worlds=#worlds
                fields.worlds=#worlds
                return fail(info,'few_worlds('..#worlds..')')
            end
            local main_ok,main=pcall(app.main_world)
            if not main_ok or main==nil or main==false then
                return fail(info,'main_world_unavailable')
            end
            info.main=tostring(main)
            if escape_only then
                local menu_world
                for _,candidate in ipairs(worlds) do
                    if candidate~=nil and candidate~=main then menu_world=candidate break end
                end
                if not menu_world then return fail(info,'menu_world_unavailable') end
                main=menu_world
            end
            info.world=main
            info.worlds=#worlds
            fields.main=tostring(main)
            fields.world=main
            fields.worlds=#worlds
            local scene_world=main
            local markers={}
            local reason2,counts2=scene(main)
            if not reason2 then markers=counts2 end
            info.markers=markers
            info.marker_counts=markers
            fields.markers=markers
            fields.marker_counts=markers
            return finish(info,fields,scene_world,markers)
        end
        local main_ok,main=pcall(app.main_world)
        if not main_ok or main==nil or main==false then return fail(info,'main_world_unavailable') end
        info.main=tostring(main)
        info.world=main
        fields.main=tostring(main)
        fields.world=main
        local listed=false
        for _,candidate in ipairs(worlds)do if candidate==main then listed=true break end end
        if not listed then return fail(info,'main_world_unlisted') end
        if not list then return fail(info,'marker_id_unavailable') end
        local markers={}
        info.markers=markers
        info.marker_counts=markers
        fields.markers=markers
        fields.marker_counts=markers
        local scene_world=main
        local reason,counts
        if world_scope~='main' then
            local best,scanned
            if ship_world then
                -- prefer the world that already proved to be the ship once
                reason,counts=scene(ship_world)
                if not reason then best,scanned=ship_world,1 end
            end
            if not best then
                for index=1,math.min(max_worlds,#worlds)do
                    scanned=(scanned or 0)+1
                    reason,counts=scene(worlds[index])
                    if not reason then best=worlds[index] break end
                end
            end
            fields.worlds_scanned=scanned or 0
            if not best then
                -- world_scope='session': no world carries the marker set at
                -- all, which on this build means the marker resource ids are
                -- not resolvable here (live log: 0 markers in every world for
                -- 18k+ frames with a real session). Report it as a recoverable
                -- fallback - a real session object plus an idle native UI - and
                -- let the host's latch decide, exactly as it already does for
                -- the non-affirmative session case.
                if world_scope=='session' then
                    info.markers={}
                    info.marker_counts={}
                    info.markers_all_absent=true
                    info.fallback=true
                    fields.markers={}
                    fields.marker_counts={}
                    fields.markers_all_absent=true
                    fields.fallback=true
                    return fail(info,'ship_markers_unresolvable')
                end
                return fail(info,'ship_marker_absent')
            end
            ship_world=best
            scene_world=best
            info.world=best
            info.main_matches=(best==main)
            fields.world=best
            fields.main_matches=info.main_matches
            markers=counts
        else
            reason,counts=scene(main)
            if reason then return fail(info,reason) end
            markers=counts
        end
        info.markers=markers
        info.marker_counts=markers
        fields.markers=markers
        fields.marker_counts=markers
        return finish(info,fields,scene_world,markers)
    end
    return {sample=function()
        local fields={reason=nil}
        local info={reason=nil,fields=fields}
        local ok,value=pcall(snapshot,info)
        if not ok then
            local text=tostring(value)
            info.reason=text:match('([^:]+)$') or info.reason or 'gate_error'
            fields.reason=info.reason
            return false,info.reason,info.world,fields
        end
        if value~=true then
            fields.reason=info.reason or 'gate_blocked'
            return false,fields.reason,info.world,fields
        end
        fields.reason=info.reason or 'ship_idle'
        return true,fields.reason,info.world,fields
    end,
    reset=function()
        marker_ids=nil
        ui_global=nil
        ship_world=nil
        escape_run=0
    end}
end
return ShipVisibility
