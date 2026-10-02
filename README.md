# HD2 Custom Armor Kit / 自定义护甲

开发源码快照：**2.5.10，尚未完成实际游戏验收，不是稳定发布版。**
Development snapshot: **2.5.10, in-game acceptance remains incomplete.**

可直接导入管理器的 ZIP 在本地 `dist/Custom-Armor-Kit-2.5.10-dev.zip`，线上在
[测试 Release](https://github.com/YC426/HD2-Custom-Armor-Kit/releases/tag/v2.5.10-dev.20261002)。
不要将 GitHub 自动生成的 Source code ZIP 当作模组安装包。

目标：Esc 菜单中的双语护甲卡片编辑、多个不同护甲同时修改、自动发现护甲。
目前军械库崩溃、真实安全词条上限、动态词条效果、多卡隔离、鼠标拖动及完整
中英文实机切换仍需验证。11 行只是临时软件限制，不能视为已证明的安全上限。
源码保留受 `development.enable` 控制的开发驱动供本地诊断；构建工具会从安装包中
剥离该驱动及 tooltip 探针，并重新编译、审计实际封装的 Lua。

## Local validation / 本地检查

```powershell
python -m pip install -r requirements-dev.txt
python -B work/standalone/build_armor.py --validate-only
```

检查包括 Lua / LuaJIT 编译、FFI 声明审计、护甲逻辑和菜单状态模拟，以及隔离目录
中的部署保护测试。通过这些检查不等于游戏功能通过。检查不会部署游戏文件。

## Packaging / 构建安装包

先按 THIRD_PARTY_NOTICES.md 提供外部封装工具，再运行
`python -B work/standalone/build_armor.py`。部署是另外显式启用的 `--deploy` 选项，
当前未验收快照不建议部署。工具只允许操作本模组声明，保护其他模组层。

## Workspace relationship / 与原工作区的关系

本仓库具有独立 `.git` 和提交历史。`work/standalone/` 保存本模组源码、构建工具和测试。
原综合工作区继续保留历史包、实机证据与第三方只读参考；它们不上传本仓库。
三份运行源码与原工作区快照逐字节一致。仓库构建工具移除了旧私人路径，包检查
仅检查本地候选，不依赖私人部署回执，也不调用另一模组的包检查。
后续开发应在此仓库提交；部署前须核对原工作区与仓库的源码差异，不能假定自动同步。
