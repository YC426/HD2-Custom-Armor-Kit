# HD2 Custom Armor Kit / 自定义护甲

> ## ⛔ 已退役 / RETIRED — 2026-10-03
>
> **本模组已停止维护，仓库已归档（只读）。**
> **请改用 [Super Earth Armory Forge](https://github.com/Hung1510/Super-Earth-Armory-Forge)**
> （作者 Hung1510，Nexus Mods / AyakaMods 均有发布）。
>
> 它在**本模组的全部功能面**上都更强，逐条对比见下方
> [「为什么退役」](#为什么退役--why-retired)。产品层面本模组可被完全替代。
>
> **不要两个一起装。** 两者写同一批护甲 kit 记录，Armory Forge 的引擎注释明确说明
> 它会重读别的模组原地改过的行 —— 同开会互相踩。

This mod is **retired and this repository is archived (read-only)**. Use
**[Super Earth Armory Forge](https://github.com/Hung1510/Super-Earth-Armory-Forge)**
instead. Do **not** install both: they patch the same armor kit records.

---

## 退役时留下的实测结论 / The measurements worth keeping

本模组虽然退役，但开发过程中做过的实机实验产出了这个记录空间里少见的**定量结论**。
归档在此，供他人参考（也见
[上游报告草稿](https://github.com/YC426/HD2-Custom-Armor-Kit/blob/main/RETIREMENT-FINDINGS.md)）。

### 1. 写入 11 行效果行会让游戏在**读取**时 fastfail

| 测试 | 词条数 | 写入行数 | 属性换装 | 结果 |
|---|---|---|---|---|
| L1 | 1 | 2 | 无 | 安全 |
| L2 | 4 | 6 | 无 | 安全 |
| L3 / L4 / L5 | 1 | 2 | 有（0 / 1 / 3 件残留） | 安全 |
| **T1** | 5 | **11** | 无 | **崩溃** |
| **T3** | **4** | **11** | 无 | **崩溃** |
| **T2B** | 5 | **11** | 无 | **崩溃** |
| **L6** | 5 | **11** | 有 | **崩溃** |

崩溃签名（**5 次复现，偏移完全一致**）：

```
faulting module : game.dll 1.0.0.19155 (timestamp 0x6ab3b43f)
exception code  : 0xc0000409      (fastfail)
fault offset    : 0x20d63a4
WER             : fault bucket type 5, Event Name BEX64
```

**触发条件是「读取」而不是写入**：只应用、不悬停、不开军械库 → 不崩；
**在军械库中悬停那件被改过的护甲**（或打开军械库查看它）→ 数秒内崩溃。

**已用实验排除**：属性/权重换装（T1 完全不换装照样崩）、具体是哪几行
（T2B/T3 与 T1 的修饰符 id **零重叠**）、词条数量（T3 只用 4 个词条，与安全的 L2 相同）、
以及外部材料标注为「假」的那条 `击倒抗性` 行（T2B/T3 不含它）。
**7~10 行未测**，因此安全边界在 7~10 之间，11 已确认不安全。
**机制本身仍未查明。**

### 2. 槽位模型：装饰槽位与真实槽位

来自第三方研究材料（原文转录在完整归档中）：

- 一个被动的效果行分为 **装饰词条**（显示在游戏中但**没有实际效果**）与 **实际词条**
  （**藏在后面**）；实际词条排在所有装饰词条之后，顺序与装饰词条一致。
  例：蓄势出击 装饰 1↔3、2↔4；强化肩章 唯一动态词条（装填速度）在**第 4 槽位**。
- **修改第 3 / 第 4 槽位词条的「类型」才会崩**；覆盖**装饰**词条是安全的。
- **描述 ID = 0 是合法的**（显示为空、跳过该行显示），它本身不是缺陷。
- **弹药容量无法改值**（疑似硬编码），**装填速度可以**（1.3 = +30%）。

### 3. 已知缺陷（未修，如实记录）

- **属性换装会产生混合值三维**：按 `(body,slot,type)` 匹配时，供体缺少的件保留本体重量，
  供体多出的件根本不会被写入。例：AD-49 ← A-9 的总重是 **25** 而纯 A-9 是 **28** ——
  使用者会看到「不是那件护甲的三维」。
- `rowbudget = 11` 只是**防御性护栏**，不是实测安全值；而且它**挡不住**上面那个崩溃
  （T1 恰好 11 行、一格未超，照样崩）。

---

## 为什么退役 / Why retired

| 能力 | Super Earth Armory Forge | 本模组 |
|---|---|---|
| 面板键位 | **F7**，另支持手柄（Back+Start） | Esc → GAME 页 |
| 实时改数值 | **输入 `75%` / `+50 armor`，`-- - + ++` 微调，`R` 重置** | 只能整条选用 |
| 预设 / 快速切换 | **预设页 + F9 轮换 + 撤销 30 步** | 无 |
| 护甲三维 | **轻/中/重，可单件，也可"全护甲跟随"** | 可换供体，但会得到混合值 |
| 冲突策略 | Stack all / Strongest only | `merge=sum` / `merge=keep`（等价） |
| 数值可信度标注 | **UNTESTED / CONFIRMED IN GAME** | 无 |
| 网页构建器 + 分享码 | **有** | 无 |
| 搜索 / 缩放 / 拖动 / 手柄 | **有** | 部分 |
| 问题报告 | **一键 Copy problem report + STATUS 文件** | 靠自己翻日志 |
| 发布与维护 | Nexus / AyakaMods / CI / 更新流程 | 本地自用 |

---

## 历史内容（归档保留）/ Historical content

开发源码快照：**2.5.10，未完成实际游戏验收，不是稳定发布版。**

可直接导入管理器的 ZIP 在本地 `dist/Custom-Armor-Kit-2.5.10-dev.zip`，线上在
[测试 Release](https://github.com/YC426/HD2-Custom-Armor-Kit/releases/tag/v2.5.10-dev.20261002)。
不要将 GitHub 自动生成的 Source code ZIP 当作模组安装包。

源码保留受 `development.enable` 控制的开发驱动供本地诊断；构建工具会从安装包中
剥离该驱动及 tooltip 探针，并重新编译、审计实际封装的 Lua。

### Local validation / 本地检查

```powershell
python -m pip install -r requirements-dev.txt
python -B work/standalone/build_armor.py --validate-only
```

检查包括 Lua / LuaJIT 编译、FFI 声明审计、护甲逻辑和菜单状态模拟，以及隔离目录
中的部署保护测试。通过这些检查不等于游戏功能通过。检查不会部署游戏文件。

### Packaging / 构建安装包

先按 THIRD_PARTY_NOTICES.md 提供外部封装工具，再运行
`python -B work/standalone/build_armor.py`。部署是另外显式启用的 `--deploy` 选项。
工具只允许操作本模组声明，保护其他模组层。

### Workspace relationship / 与原工作区的关系

本仓库具有独立 `.git` 和提交历史。`work/standalone/` 保存本模组源码、构建工具和测试。
原综合工作区继续保留历史包、实机证据与第三方只读参考。

---

## 许可与致谢 / License & credits

本模组的实现是独立的，但开发过程中参考了一份**第三方只读研究材料**（护甲词条槽位模型），
其结论已在上面第 2 节转述并注明来源性质。Armory Forge 的推荐**不构成任何隶属或背书关系**，
仅为便于使用者找到仍在维护的替代品。
