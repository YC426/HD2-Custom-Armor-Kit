"""Exercise retained dragging, current game language and stable row ceiling."""
from pathlib import Path
import lupa

source = Path(__file__).with_name('multi_perk.lua').read_text(encoding='utf-8')
def cut(start, end):
    at = source.index(start)
    return source[at:source.index(end, at)]

lua = lupa.LuaRuntime(unpack_returned_tuples=True)
lua.execute('''
HOME='' M={} PANEL={gui=1,bounds={x=1000,y=400,w=560,h=400,title=78},regions={}}
MOVES=0
stingray={Gui={move=function(gui,x,y) assert(gui==1) MOVES=MOVES+1 GX=x GY=y end}}
function log()end
function save_panel_position() SAVED=true end
''' + cut('local function panel_offset(', '\nlocal ui_point=') + '''
assert(panel_drag(stingray,{x=1100,y=780,down=true},1920,1080))
assert(panel_drag(stingray,{x=600,y=680,down=true},1920,1080))
assert(GX==-500 and GY==-100,'drag must move the existing GUI with the cursor')
assert(PANEL.sig==nil and PANEL.gui==1,'drag must retain its GUI')
local n=MOVES
panel_offset(stingray,1920,1080)
assert(MOVES==n,'stationary panel performs no native move')
assert(panel_drag(stingray,{x=-1000,y=2000,down=true},1920,1080))
assert(GX==-1000 and GY==280,'drag must keep the entire panel in the viewport')
assert(panel_drag(stingray,{x=0,y=1080,down=false},1920,1080))
assert(SAVED and not PANEL.drag,'release saves placement and ends the drag')
assert(not panel_drag(stingray,{x=100,y=700,down=true},1920,1080),'content click must not start drag')
''')
lua.execute('''
VISBRIDGE={base=100000,verify=function()return true end}
INDEX=12 CODE='cn' READS=0
function rd(at,n)
 READS=READS+1
 if at==100000+0x3326340 then return string.pack('<I8',200000) end
 if at==200000+705712 then return string.pack('<I4',INDEX) end
 if at==100000+0x37c5650+INDEX*8 then return string.pack('<I8',300000) end
 if at==300008 then return string.pack('<I8',400000) end
 if at==400000 then return CODE..string.rep(string.char(0),n-#CODE) end
end
function u32(s,o) return string.unpack('<I4',s,o+1) end
function u64(s,o) return string.unpack('<I8',s,o+1) end
''' + cut('local function read_game_language()', '\nlocal VISIBILITY') + '''
update_language('auto',1)
assert(M.lang=='zh','Chinese must resolve from the current language setting')
CODE='us'
update_language('auto',122)
assert(M.lang=='en','auto must follow a changed game language')
update_language('zh',123)
assert(M.lang=='zh','explicit language override must be honored')
INDEX=99
update_language('auto',244)
assert(M.lang=='zh','unreadable setting preserves last known language')
local n=READS update_language('auto',245)
assert(READS==n,'language reads must be throttled')
''')
lua.execute('local PERKS={} local RT={} local M={} local function unhex(s)return s end\n' +
            cut('local function compose(', '\nlocal S=') + '''
local rows={}
for i=1,11 do rows[i]=string.format('%08x',i)..string.rep('0',16)..'01000000' end
assert(compose(rows,999).nmod==11,'11 unique rows must fit')
rows[12]=string.format('%08x',12)..string.rep('0',16)..'01000000'
local data,why=compose(rows,999)
assert(not data and why:find('budget',1,true),'12th row cannot bypass stable cap through config')
''')
print('PASS drag without GUI rebuild, clamp, release, language changes, stable 11-row ceiling')

font = lua.execute(cut('local GLYPHS={}', '\n-- editor draft') + '\nreturn GLYPHS')
labels = lua.execute(cut('local ENLABELS={', '\nlocal function L(') + '\nreturn ENLABELS')
english = Path(__file__).with_name('zh_data.lua').read_text(encoding='utf-8')
perks, names = lua.execute(english[english.index('local EN_PERKS={'):] + '\nreturn EN_PERKS,EN_ARMOR_NAMES')
texts = list(labels.values()) + list(names.values())
for entry in perks.values():
    texts.extend(entry.values())
missing = sorted({ch for s in texts for ch in s.upper() if ch != ' ' and ord(ch) < 128 and font[ch] is None})
assert not missing, f'English menu font drops characters: {missing}'
print('PASS every English label, armor name and perk description has visible glyphs')

# Labels must identify the native passive, including the previously swapped
# Ballistic Padding/Adreno-Defibrillator entries. The reference is read only.
foundation=Path(__file__).resolve().parents[1]/'fork'/'foundation.lua'
reference=foundation.read_text(encoding='utf-8')
loader=lupa.LuaRuntime(unpack_returned_tuples=True)
def load_catalog(name):
    start=reference.index('local '+name+' = (function()')
    end=reference.index('\nend)()',start)+len('\nend)()')
    return loader.execute(reference[start:end]+'\nreturn '+name)
catalog=load_catalog('CatalogData')
labels=load_catalog('CatalogLabels')['strings']
english_table=loader.execute(english[english.index('local EN_PERKS={'):english.index('local EN_ARMOR_NAMES={')]+'\nreturn EN_PERKS')
for enum,entry in english_table.items():
    expected=labels[catalog['passives'][enum]['name_loc']]
    assert entry[1].upper()==expected, (enum,entry[1],expected)
    for index in range(2,len(entry)+1):
        assert '...' not in entry[index], (enum,'truncated description')
        assert len(entry[index])<=33, (enum,'description exceeds panel width',entry[index])
print('PASS English names match native passive IDs; complete descriptions fit each row')
