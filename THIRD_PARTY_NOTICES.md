# External dependencies

Python validation uses Lupa / LuaJIT under their respective upstream licenses.
The existing package builders require externally supplied `build_addon.py` and
`archive.py` in `work/standalone/vendor/bingus/`. Those third-party implementations
are not redistributed here. Obtain them with the appropriate upstream permission.
They encode the existing addon format; their name does not require reinstalling
Bingus alongside an MDL runtime. This repository does not contain game binaries,
other installed mods, personal configuration, or runtime logs.

No new license grant for this project's own code is made by this snapshot.

`work/fork/foundation.lua` contains only the factual passive catalog and English
label tables extracted from the workspace reference catalog. It excludes the
reference mod's runtime, GUI, disassembler, and loading behavior. `zh_data.lua`
contains the existing game's localized labels used by this mod.
