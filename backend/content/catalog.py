# -*- coding: utf-8 -*-
"""Redesigned core workspaces and 5 handcrafted flagship TRPG campaigns."""
from __future__ import annotations

import copy
import time
from typing import Any, Dict, List

from backend.config import (
    DEFAULT_FAST_TRPG_SYSTEM_PROMPT,
    DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT,
    DEFAULT_UI_MODULES,
    normalize_project_schema,
)


def _wb(idx: int, name: str, keys: List[str], content: str, *, constant: bool = False, group: str = "核心世界观", sec: List[str] | None = None) -> Dict[str, Any]:
    return {
        "id": f"wb_seed_{idx}",
        "name": name,
        "group": group,
        "enabled": True,
        "enable": True,
        "constant": constant,
        "keys": keys,
        "secondary_keys": sec or [],
        "selective": bool(sec),
        "match_type": "OR",
        "key_region": 6,
        "value_region": "System",
        "sort": idx * 10,
        "depth": 5,
        "probability": 100,
        "content": content,
        "value": content,
    }


def _build_default_projects() -> Dict[str, Dict[str, Any]]:
    now = time.time()
    fast_og = [
        {
            "id": "og_fast_ash",
            "title": "圣女与暗巷",
            "content": "雨夜蒸汽下城区，我是一名旧伤未愈的落魄骑士，在钟楼暗巷撞见浑身湿透、被教会黑衣审讯官追捕的银发见习圣女。直接展开第一幕。",
        },
        {
            "id": "og_fast_fog",
            "title": "雾港断时钟",
            "content": "1926年被海雾封锁的孤岛渔村，我提着煤油灯推开钟表匠老宅铁门，壁炉余烬尚温，屋里所有怀表却全停在 00:07。开启悬疑调查。",
        },
        {
            "id": "og_fast_xianxia",
            "title": "太虚剑阁卧底",
            "content": "我是魔教安插在正道第一剑宗的亲传弟子，今夜潜入禁地藏经阁盗取剑印，推门却撞见闭关百年的清冷师尊独自在月下擦剑。",
        },
        {
            "id": "og_fast_sandbox",
            "title": "自由沙盒",
            "isSandbox": True,
            "content": "请开启自由沙盒跑团：根据我的角色卡或首句设定直接拉入高张力第一幕。",
        },
    ]

    proj_fast = normalize_project_schema(
        {
            "id": "proj_fast_trpg",
            "name": "极速跑团",
            "category": "极速跑团",
            "description": "低延迟轻量跑团：正文 + 折叠记忆 + 底部选项，低配秒回。",
            "simple_mode": True,
            "cot_enabled": False,
            "status_panel_enabled": False,
            "ruleset": "d20",
            "system_prompt": DEFAULT_FAST_TRPG_SYSTEM_PROMPT,
            "opening_greetings": fast_og,
            "max_context_turns": 16,
            "created_at": now,
        }
    )

    proj_default = normalize_project_schema(
        {
            "id": "proj_default",
            "name": "高级跑团",
            "category": "跑团",
            "description": "完整数值状态机 + 确定性检定 + 世界书联动。",
            "simple_mode": False,
            "cot_enabled": True,
            "status_panel_enabled": True,
            "ruleset": "d20",
            "ui_modules": [dict(m) for m in DEFAULT_UI_MODULES],
            "system_prompt": (
                "你是兼具电影镜头感与顶级游戏策划功底的互动跑团主持（DM）。\n"
                "全程使用第二人称（「你」）描写光影、声响、动作与微表情；NPC 具备独立动机与底线，绝不无脑顺从。\n"
                "当本回合造成血量、精力、背包、装备、NPC好感或危机进度变化时，在正文末尾附带精简 `<state_patch>{...}</state_patch>` JSON 增量或 `<status>` 状态栏，并给出 4 个差异化行动选项。\n\n"
                + DEFAULT_GLOBAL_SYSTEM_PROTOCOL_PROMPT
            ),
            "prefix": "【玩家行动】",
            "suffix": "【提醒：推进完整事件节点，更新状态变更，文末仅输出一次 1.~4. 选项】",
            "opening_greetings": copy.deepcopy(fast_og),
            "initial_state": {
                "resources": [
                    {"key": "hp", "label": "生命", "current": 100, "max": 100},
                    {"key": "stamina", "label": "精力", "current": 80, "max": 80},
                ],
                "attributes": {"体魄": 12, "敏捷": 12, "洞察": 12, "交涉": 12},
                "equipment": {},
                "inventory": [{"name": "应急干粮", "qty": 2, "desc": "恢复少量体力"}],
                "npcs": [],
                "quests": [],
                "clocks": [],
                "scene": {"time": "入夜", "location": "待定开场点", "condition": "正常"},
            },
            "created_at": now,
        }
    )

    proj_free = normalize_project_schema(
        {
            "id": "proj_free_chat",
            "name": "自由聊天",
            "category": "聊天",
            "description": "无规则、无状态栏的纯净对话与创作模式。",
            "simple_mode": False,
            "cot_enabled": True,
            "status_panel_enabled": False,
            "ruleset": "narrative",
            "system_prompt": "",
            "created_at": now,
        }
    )

    return {
        "proj_fast_trpg": proj_fast,
        "proj_default": proj_default,
        "proj_free_chat": proj_free,
    }


def _build_flagship_campaigns() -> List[Dict[str, Any]]:
    state_patch_hint = (
        "\n\n【状态同步格式】在剧情正文与 `<memory>` 之间输出精准的 `<state_patch>` JSON 增量（仅写本回合变化的字段）：\n"
        "<state_patch>{\"resources_delta\": {\"hp\": -10}, \"clock_delta\": {\"警戒时钟\": 1}, \"inv_add\": [], \"inv_remove\": [], \"npc_upsert\": [], \"scene_set\": {\"location\": \"...\"}}</state_patch>\n"
        "最后在文末输出：\n你打算怎么做？\n1. ...\n2. ... 【🎲属性检定】\n3. ...\n4. ..."
    )

    # 1. 《灰雾钟楼：圣女与审讯官》
    c1 = normalize_project_schema({
        "id": "camp_ashbell",
        "name": "灰雾钟楼：圣女与审讯官",
        "category": "奇幻冒险",
        "author": "Easy-TRPG",
        "tags": ["蒸汽暗黑", "d20", "潜行逃亡", "双人张力"],
        "ruleset": "d20",
        "description": "雨夜蒸汽下城区，落魄骑士与逃亡银发圣女在教会猎犬围剿下的 72 小时突围。",
        "detailed_description": "### 剧本特色\n- **规则体系**：D20 关键节点检定 + 失败推进（Fail Forward）\n- **核心机制**：`教会警戒` 6格危机时钟、`圣痕侵蚀` 双刃剑资源\n- **推荐玩法**：兼顾潜行周旋、地下黑市交易与圣女信任博弈。",
        "simple_mode": False,
        "cot_enabled": True,
        "status_panel_enabled": False,
        "system_prompt": (
            "你是《灰雾钟楼》的暗黑蒸汽奇幻 DM。世界设定：维多利亚工业都市「伦维尔」被煤矿黑雾与教会高压统治，"
            "主角曾是被革职的圣殿骑士，如今靠接地下护送与黑市黑活度日。\n"
            "关键机制：1. 使用第二人称电影级叙事，突出煤油灯火、雨声、齿轮轰鸣与火药硝烟；"
            "2. 教会「灰衣审讯庭」绝不仁慈，一旦警戒时钟满格（6/6）将直接封锁城区并派出蒸汽猎犬与铁处女行刑队；"
            "3. 圣女希尔薇娅外柔内韧，藏有教会禁书秘密，会对你的每一次选择做出真实心理评估。"
            + state_patch_hint
        ),
        "initial_state": {
            "resources": [
                {"key": "hp", "label": "生命", "current": 95, "max": 100},
                {"key": "stigma", "label": "圣痕侵蚀", "current": 15, "max": 100},
                {"key": "silver", "label": "先令银币", "current": 42, "max": 9999},
            ],
            "attributes": {"格斗": 14, "潜行": 13, "洞察": 12, "威慑": 11},
            "equipment": {
                "主手": {"name": "缺口制式骑兵短剑", "desc": "曾隶属灰烬骑士团"},
                "防具": {"name": "浸油防雨风衣", "desc": "掩盖旧伤与武器"},
            },
            "inventory": [
                {"name": "劣质止血绷带", "qty": 2, "desc": "恢复 20 生命"},
                {"name": "黄铜防风打火机", "qty": 1, "desc": "昏暗区照明"},
            ],
            "npcs": [
                {"name": "希尔薇娅", "affinity": 45, "relation": "戒备的逃亡圣女", "status": "左肩渗血，紧握圣银短杖", "mood": "紧张警惕"},
                {"name": "审讯官马库斯", "affinity": 10, "relation": "冷血追捕者", "status": "正带队封锁东街", "mood": "冷酷"},
            ],
            "quests": [{"title": "离开封锁区", "status": "进行中", "progress": "天亮前穿过下水道或黑市港口"}],
            "clocks": [{"name": "警戒时钟", "current": 2, "max": 6, "kind": "threat"}],
            "scene": {"time": "23:40 暴雨夜", "location": "伦维尔下城区·废钟楼夹道", "condition": "浓雾低能见度"},
        },
        "opening_greetings": [
            {
                "id": "og_ash_1",
                "title": "钟楼初遇（经典开局）",
                "content": "暴雨敲打着伦维尔下城区锈蚀的铁皮屋檐。你捂着肋下隐隐作痛的旧伤，刚在废弃钟楼的拱门下点亮黄铜打火机，一双染血的银白色靴子便闯进微弱的火光——银发见习圣女希尔薇娅背靠湿冷石柱滑落，手里反握着半截圣银短杖抵住自己咽喉，而百米外街口已传来审讯庭铁靴整齐踩过积水的沉重回响。",
            },
            {
                "id": "og_ash_2",
                "title": "暗港接头（潜行线）",
                "content": "你提前三十分钟抵达漂浮着煤渣油膜的暗港七号码头，本应接走圣女的走私蒸汽艇却已人去船空，甲板上只留下一枚尚未熄灭的教会黑蜡火漆与半张撕毁的港口通缉令。",
            },
        ],
        "world_book": [
            _wb(1, "伦维尔铁律（常驻）", [], "伦维尔分为上层白塔区（教会与蒸汽贵族）与下层黑雾区。下城区禁持重火器，夜间十一点后实行宵禁，巡逻队见无通行证者格杀勿论。", constant=True),
            _wb(2, "希尔薇娅的秘密", ["希尔薇娅", "圣女", "圣银", "短杖"], "希尔薇娅体内的「初代圣痕」其实是教会用来封印深渊熔炉的活体钥匙，一旦她被抓回白塔，将在七日内被剥离灵魂。她袖中藏有一枚能打开地下秘道的水晶钥匙。", group="登场人物设定"),
            _wb(3, "灰衣审讯庭", ["审讯官", "马库斯", "猎犬", "教会"], "审讯官马库斯率领机械猎犬（靠嗅觉追踪圣银与血迹）与蒸汽火枪手。若出现火光或枪声，警戒时钟立即 +2。", group="地点与势力"),
            _wb(4, "锈牙黑市", ["黑市", "医生", "走私", "船", "码头"], "黑雾区地下诊所的「瞎眼巴克」愿意用圣银碎片换取违禁炼金药剂和伪造船票，但他最讨厌教会线人。", group="地点与势力"),
            _wb(5, "蒸汽下水道", ["下水道", "排水道", "地道"], "钟楼地下通往泰晤士暗渠的检修门早已锈死，强行撬动需力量或工具检定，内部潜伏着吞食矿渣的盲眼变异鼠群。", group="地点与势力"),
            _wb(6, "圣痕反噬", ["圣痕", "仪式", "禁咒", "侵蚀"], "当希尔薇娅或主角催动圣银短杖时，能爆发强力光辉逼退追兵，但圣痕侵蚀会立刻 +15~25，超过 80 会引来高空飞艇的以太探测器锁定。", group="隐藏剧情触发"),
        ],
        "bundled_cards": [
            {
                "id": "card_silvia_ash",
                "name": "希尔薇娅",
                "description": "十七岁逃亡见习圣女，银发灰眸，表面顺从克制，实则意志坚定，带着教会最高机密逃离白塔。",
                "personality": "外冷内韧、极度警惕但重诺，不愿无辜者替自己送命。",
                "scenario": "伦维尔蒸汽下城区逃亡中。",
            },
            {
                "id": "card_marcus_inq",
                "name": "审讯官马库斯",
                "description": "灰衣审讯庭第三分队队长，右臂改造为黄铜以太义肢，信奉绝对秩序。",
                "personality": "冷静、精密、善用心理压迫与包围战术。",
                "scenario": "正在伦维尔下城区全城搜捕。",
            },
        ],
    })

    # 2. 《00:07 雾港断时录》
    c2 = normalize_project_schema({
        "id": "camp_fogport",
        "name": "00:07 雾港断时录",
        "category": "悬疑克苏鲁",
        "author": "Easy-TRPG",
        "tags": ["CoC d100", "克苏鲁", "孤岛推理", "时间循环"],
        "ruleset": "d100",
        "description": "1926 年断电孤岛，所有钟表停在 00:07，海雾中走来的究竟是失踪居民还是不可名状的回响？",
        "detailed_description": "### 剧本特色\n- **规则体系**：标准 CoC `1d100`（常规 / 困难 / 极难 / 大成功）\n- **核心机制**：`理智 SAN`、`海雾涨潮` 6格时钟、线索串联推理。",
        "simple_mode": False,
        "cot_enabled": True,
        "status_panel_enabled": False,
        "system_prompt": (
            "你是 1920 年代克苏鲁悬疑跑团 KP（守密人）。禁止直接剧透幕后邪神，必须通过潮湿盐味、怀表齿轮停摆、"
            "居民不自然的重复举动来营造逐步逼近的心理恐怖。\n"
            "检定规则：涉及调查异常、医学验尸、撬锁或直面诡异时，在选项标注 `【🎲侦查检定】` / `【🎲理智检定】`；"
            "直面不可名状之物时依据 CoC 规则扣减 SAN 并记录异变症状。"
            + state_patch_hint
        ),
        "initial_state": {
            "resources": [
                {"key": "hp", "label": "体力", "current": 12, "max": 12},
                {"key": "san", "label": "理智 SAN", "current": 65, "max": 80},
            ],
            "attributes": {"侦查": 65, "心理学": 55, "图书馆": 60, "手枪": 40, "信用": 50},
            "equipment": {
                "主手": {"name": "黄铜煤油提灯", "desc": "驱散浓雾 6 米"},
                "腰间": {"name": "点38转轮手枪", "desc": "装弹 6 发，对灵体未必有效"},
            },
            "inventory": [
                {"name": "委托函（老钟表匠）", "qty": 1, "desc": "署名赫伯特·韦斯特"},
                {"name": "停摆的银怀表", "qty": 1, "desc": "指针卡在 00:07"},
            ],
            "npcs": [
                {"name": "码头守夜人老汤姆", "affinity": 50, "relation": "神情恍惚的当地人", "status": "在码头小屋磨鱼叉", "mood": "麻木"},
            ],
            "quests": [{"title": "查明钟表停摆与岛民失踪真相", "status": "进行中", "progress": "探索钟表匠老宅与海崖灯塔"}],
            "clocks": [{"name": "海雾涨潮时钟", "current": 1, "max": 6, "kind": "threat"}],
            "scene": {"time": "00:07（停滞）", "location": "雾港镇·钟表匠老宅门廊", "condition": "海雾吞没码头"},
        },
        "opening_greetings": [
            {
                "id": "og_fog_1",
                "title": "停滞的老宅（经典调查）",
                "content": "1926 年十一月的海风带着腐烂海藻味。你作为来自波士顿的私家侦探，提着煤油灯推开钟表匠老宅生锈的铁门。壁炉里的松木灰尚带余温，长桌上的热红茶还冒着细微白气——可墙上七座挂钟与桌上的怀表，却全都精准地卡在午夜十二点零七分，秒针纹丝不动。",
            },
            {
                "id": "og_fog_2",
                "title": "灯塔无线电失联",
                "content": "接送你的渔船刚驶离雾港三十米便被白雾吞没，无线电里只剩下一段每隔七秒重复一次的莫尔斯电码：「不要看钟，不要下楼。」",
            },
        ],
        "world_book": [
            _wb(1, "雾港基础档案（常驻）", [], "雾港镇位于新英格兰外海十海里，居民约百余人，十年前曾打捞起一块非金非石的绿色星形钟盘。每周二午夜轮渡才会靠岸。", constant=True),
            _wb(2, "00:07 时间锚点", ["怀表", "挂钟", "00:07", "时间", "秒针"], "老宅地下室藏着连接潮汐钟摆的黄铜仪轨，所有岛上表针会在海面升起异星潮汐时同时停滞，只有上发条且逆时针拨动的人能察觉夹层暗门。", group="隐藏剧情触发"),
            _wb(3, "灯塔守卫与日志", ["灯塔", "日志", "无线电", "电码"], "灯塔三楼锁着近三个月的航海日志，最后几页字迹逐渐变得扭曲，反复写着「水下钟声敲了十三下」。", group="地点与势力"),
            _wb(4, "礁石礼拜堂", ["礼拜堂", "教堂", "牧师", "钟声"], "村西崖边的破旧木质礼拜堂看似供奉海神，祭坛底座刻有螺旋状触须浮雕，地下通往退潮时才显露的海蚀洞。", group="地点与势力"),
            _wb(5, "老汤姆的异常", ["汤姆", "守夜人", "渔民", "脖子"], "仔细观察老汤姆或村里渔民的衣领下方，会发现皮肤上长着类似鱼鳃的细小灰白裂痕，他们夜间会梦游般走向海边。", group="登场人物设定"),
            _wb(6, "地下钟表室", ["地下室", "暗门", "钟表匠", "赫伯特"], "钟表匠并未死亡，他用银链将自己锁在地下室保险柜外，手中死死抱着用铅盒封印的绿色星形钟盘。", group="隐藏剧情触发"),
        ],
        "bundled_cards": [
            {
                "id": "card_tom_fog",
                "name": "守夜人老汤姆",
                "description": "六十岁的雾港码头守夜人，左手少了两根手指，总在深夜擦拭一盏没有油的鲸油灯。",
                "personality": "沉默寡言，对外来者既排斥又隐约流露求救的挣扎。",
                "scenario": "雾港码头雾夜值守中。",
            },
        ],
    })

    # 3. 《太虚劫：魔宗暗桩》
    c3 = normalize_project_schema({
        "id": "camp_swordspy",
        "name": "太虚劫：魔宗暗桩",
        "category": "古风仙侠",
        "author": "Easy-TRPG",
        "tags": ["仙侠卧底", "d20", "剑修博弈", "高张力"],
        "ruleset": "d20",
        "description": "魔教潜伏正道第一剑宗的暗桩，在窃取镇派剑印的深夜，正撞上闭关百年的清冷师尊。",
        "detailed_description": "### 剧本特色\n- **规则体系**：D20 潜行与话术博弈\n- **核心机制**：`伪装完整度`、`剑阁疑心` 时钟、`魔元` vs `剑气` 双修切换。",
        "simple_mode": False,
        "cot_enabled": True,
        "status_panel_enabled": False,
        "system_prompt": (
            "你是东方高武仙侠潜伏跑团 DM。文风兼具古风剑意与暗流涌动的心理压迫感。\n"
            "主角表面身份是「太虚剑阁」外门翘楚、受师尊青眼收入内门的年轻剑修，实则是魔教幽冥殿安插十年的死士暗桩。\n"
            "注意：太虚剑阁长老个个修为高绝，一旦谎言出现逻辑漏洞或魔气外泄，「剑阁疑心」时钟立刻推进；但师尊沈清寒心思极深，她看破却未必立刻点破。"
            + state_patch_hint
        ),
        "initial_state": {
            "resources": [
                {"key": "hp", "label": "气血", "current": 100, "max": 100},
                {"key": "qi", "label": "真元", "current": 80, "max": 80},
                {"key": "disguise", "label": "伪装完整", "current": 90, "max": 100},
            ],
            "attributes": {"剑法": 14, "隐匿": 15, "定力": 13, "机变": 14},
            "equipment": {
                "佩剑": {"name": "青霜剑", "desc": "太虚剑阁内门制式灵剑，刻有宗门印记"},
                "暗藏": {"name": "敛息玉佩", "desc": "压制体内幽冥魔功波动"},
            },
            "inventory": [
                {"name": "替死纸人", "qty": 1, "desc": "可抵挡一次致命探查"},
                {"name": "宗门值夜令牌", "qty": 1, "desc": "允许子时前在藏经阁外围行走"},
            ],
            "npcs": [
                {"name": "沈清寒（师尊）", "affinity": 55, "relation": "清冷剑尊 · 未知深浅", "status": "月下独坐擦剑，剑意锁定三丈", "mood": "淡漠审视"},
            ],
            "quests": [{"title": "脱身与剑印之谜", "status": "进行中", "progress": "应对沈清寒的突然盘问"}],
            "clocks": [{"name": "剑阁疑心", "current": 1, "max": 6, "kind": "threat"}],
            "scene": {"time": "子时三刻", "location": "太虚剑阁·藏经阁九层露台", "condition": "寒月清冷，剑气微鸣"},
        },
        "opening_greetings": [
            {
                "id": "og_sword_1",
                "title": "月下撞破（巅峰开局）",
                "content": "你屏息运起敛息诀，指尖刚刚触及九层紫檀木门上的禁制阵纹，门轴却先一步无声向内滑开。清冷月色如霜雪倾泻，本该在后山寒潭闭关百年的剑尊沈清寒正端坐蒲团之上，素白剑穗垂落膝边，指腹缓缓拭过三尺秋水寒锋。「这么晚来九层，」她连眼睫都未抬，「是找功法，还是找本座？」",
            },
            {
                "id": "og_sword_2",
                "title": "暗号接应危机",
                "content": "你刚将半枚拓印好的剑印图谱藏入袖底，山下护山大阵忽然鸣响三声紫钟——外门巡山长老抓住了另一名试图潜逃的魔宗线人，对方手中正握着与你同源的幽冥传讯符。",
            },
        ],
        "world_book": [
            _wb(1, "太虚剑阁门规（常驻）", [], "太虚剑阁为天下剑道魁首，共分七峰。九层藏经阁仅历代剑尊与亲传首徒可入，私闯者轻则废去修为逐出山门，重则镇压剑冢。", constant=True),
            _wb(2, "沈清寒其人", ["沈清寒", "师尊", "剑尊", "蒲团"], "沈清寒修「太上忘情剑」，实则三十年前曾与魔宗上一代圣女有过一段旧怨。她收你入门并非毫无察觉，而是在借你引出幽冥殿幕后宗主。", group="登场人物设定"),
            _wb(3, "幽冥殿暗桩规矩", ["魔宗", "幽冥", "暗桩", "魔功", "令牌"], "魔宗在你十岁时种下「九幽锁心蛊」，每逢月圆若不吞服解药或上交宗门情报，便会经脉寸断。", group="地点与势力"),
            _wb(4, "镇派剑印真相", ["剑印", "禁地", "阵法"], "九层供奉的并非单纯兵符，而是镇压太虚山底古魔剑灵的封印枢机；一旦剑印被盗，整座仙门将在三日内灵脉逆流。", group="隐藏剧情触发"),
        ],
        "bundled_cards": [
            {
                "id": "card_shen_qinghan",
                "name": "沈清寒",
                "description": "太虚剑阁掌教尊者，白衣胜雪，修为已至化境，一双浅琉璃眸仿佛能洞穿人心虚妄。",
                "personality": "外冷内敏、护短却原则极重，说话言简意赅，压迫感极强。",
                "scenario": "九层藏经阁月下擦剑。",
            },
        ],
    })

    # 4. 《霓虹裂隙 2089》
    c4 = normalize_project_schema({
        "id": "camp_neon2089",
        "name": "霓虹裂隙 2089",
        "category": "赛博朋克",
        "author": "Easy-TRPG",
        "tags": ["赛博朋克", "2d6 PbtA", "义体黑市", "高燃动作"],
        "ruleset": "2d6",
        "description": "酸雨夜之城黑市义体诊所：雇主横尸手术台，加密芯片发烫，浮空装甲车探照灯已封死巷口。",
        "detailed_description": "### 剧本特色\n- **规则体系**：PbtA `2d6`（10+ 完胜 / 7~9 付出代价成功 / 6- 局势急转直下）\n- **核心机制**：`义体过载`、`信用点`、黑客骇入与荒坂围剿时钟。",
        "simple_mode": False,
        "cot_enabled": True,
        "status_panel_enabled": False,
        "system_prompt": (
            "你是 2089 年赛博朋克动作悬疑 DM，采用 PbtA 2d6 判定哲学：\n"
            "- 10+ 潇洒达成且占尽优势；7~9 虽然得手但立刻引发副作用（过载上升、弹药见底、引来增援）；6- 敌人立刻开火或现场剧变。\n"
            "- 描写充斥霓虹水洼倒影、神经插槽过热嗡鸣、合成烟草与冷酷企业雇佣兵风格。"
            + state_patch_hint
        ),
        "initial_state": {
            "resources": [
                {"key": "hp", "label": "生命", "current": 100, "max": 100},
                {"key": "overload", "label": "义体过载", "current": 20, "max": 100},
                {"key": "eb", "label": "信用点", "current": 1850, "max": 99999},
            ],
            "attributes": {"反应": 2, "黑客": 1, "冷血": 2, "肉体": 1},
            "equipment": {
                "主手": {"name": "荒坂制式智能手枪", "desc": "弹匣 10/12，可锁头微调"},
                "义体": {"name": "二型斯安威斯坦", "desc": "短时神经加速，每次使用过载 +20"},
            },
            "inventory": [
                {"name": "军用神经镇静剂", "qty": 2, "desc": "降低义体过载 30"},
                {"name": "未知发烫加密芯片", "qty": 1, "desc": "带荒坂生物锁"},
            ],
            "npcs": [
                {"name": "零号（义体医生）", "affinity": 60, "relation": "黑市搭档", "status": "正锁死诊所卷帘门", "mood": "暴躁焦急"},
            ],
            "quests": [{"title": "带芯片杀出或黑掉封锁网", "status": "进行中", "progress": "破解装甲车包围圈"}],
            "clocks": [{"name": "荒坂合围时钟", "current": 2, "max": 6, "kind": "threat"}],
            "scene": {"time": "02:18 酸雨夜", "location": "底城区·地下义体诊所后室", "condition": "警笛逼近，全频段干扰"},
        },
        "opening_greetings": [
            {
                "id": "og_neon_1",
                "title": "手术台死局（经典开局）",
                "content": "酸雨顺着霓虹灯牌「无痛拆装」滴落进积水。你刚拔出神经接口插槽，手术台上的中间人雇主却早已瞳孔扩散——他胸口开着一道整洁的激光烧灼孔，手里死死攥着仍在发烫的黑色生物芯片。下一秒，诊所玻璃外墙被探照灯照得惨白，两架荒坂重工浮空装甲车的引擎轰鸣压低了屋顶雨水。",
            },
        ],
        "world_book": [
            _wb(1, "夜之城底层法则（常驻）", [], "在 2089 年的夜之城底城区，企业特勤享有治外法权。义体过载超过 80 会触发赛博精神病幻觉与短暂失控。", constant=True),
            _wb(2, "黑色生物芯片", ["芯片", "数据", "生物锁", "密码"], "这枚芯片里记录着荒坂高管「黑墙边缘实验」的 AI 幽灵人格钥匙，中间人死前最后把解密密钥隐藏在诊所冷柜的义眼编号里。", group="隐藏剧情触发"),
            _wb(3, "义体医生零号", ["零号", "医生", "诊所", "后门"], "零号是前创伤小组外科医，他诊所冰柜后藏着一条直通地铁废弃维护通道的逃生井。", group="登场人物设定"),
            _wb(4, "荒坂特勤清道夫", ["荒坂", "装甲车", "清道夫", "无人机"], "领队是一名搭载光学迷彩的忍者级刺客，优先瘫痪目标黑客链路。", group="地点与势力"),
        ],
        "bundled_cards": [
            {
                "id": "card_zero_doc",
                "name": "零号医生",
                "description": "带着半张金属颌骨的地下义体医生，左眼是工业级放大义眼，嘴上骂骂咧咧但从不出卖老主顾。",
                "personality": "毒舌、务实、贪财却讲底线。",
                "scenario": "酸雨夜诊所戒备中。",
            },
        ],
    })

    # 5. 《星陨边境：三人小队》（原生多角色群聊示范模组）
    c5 = normalize_project_schema({
        "id": "camp_frontier_party",
        "name": "星陨边境：三人小队",
        "category": "TRPG跑团",
        "author": "Easy-TRPG",
        "tags": ["多角色群聊", "小队冒险", "d20", "分支示范"],
        "ruleset": "d20",
        "description": "自带三名性格迥异的常驻队友卡，开局即体验真正的多角色群聊配合与多线分支。",
        "detailed_description": "### 剧本特色\n- **原生群聊示范**：安装后自动携带「林夜（战术官）」「苏糖（炼金师）」「霍渊（断剑客）」三张队友角色卡！\n- **自由点名**：可在右边栏随时点名特定队友发言或开启自动轮转。\n- **分支推荐**：遗迹三岔口极适合体验树形平行世界分支。",
        "simple_mode": False,
        "cot_enabled": True,
        "status_panel_enabled": False,
        "system_prompt": (
            "你是《星陨边境》的小队冒险 DM，擅长调度多角色之间的化学反应。\n"
            "玩家是四人探索小队的队长，队伍包含：\n"
            "1. 林夜（冷静精准的战术斥候兼弓弩手）；2. 苏糖（爱搞爆炸药剂的话痨炼金少女）；3. 霍渊（沉默寡言的重剑护卫）。\n"
            "注意：每次若系统指定了主视角发言角色，请重点描写该角色的行动、台词与性格反差，同时推动遗迹探索。"
            + state_patch_hint
        ),
        "group_defaults": {"enabled": True, "mode": "round_robin"},
        "initial_state": {
            "resources": [
                {"key": "hp", "label": "小队士气", "current": 90, "max": 100},
                {"key": "supplies", "label": "补给点数", "current": 6, "max": 10},
                {"key": "starlight", "label": "星辉结晶", "current": 120, "max": 9999},
            ],
            "attributes": {"指挥": 14, "感知": 13, "博学": 12, "勇武": 13},
            "equipment": {
                "主手": {"name": "星铁探索短矛", "desc": "可拆卸为探路杖"},
                "徽记": {"name": "边境公会铜徽", "desc": "记录探索度"},
            },
            "inventory": [
                {"name": "苏糖牌不稳定火药瓶", "qty": 3, "desc": "炸开障碍或制造混乱"},
                {"name": "绳索与岩钉包", "qty": 1, "desc": "团队攀爬必备"},
            ],
            "npcs": [
                {"name": "林夜", "affinity": 72, "relation": "可靠副手", "status": "举弩警戒左翼走廊", "mood": "冷静"},
                {"name": "苏糖", "affinity": 78, "relation": "炼金炸弹狂", "status": "正晃动一瓶冒绿光的试剂", "mood": "兴奋好奇"},
                {"name": "霍渊", "affinity": 65, "relation": "沉默重剑士", "status": "扛剑守在队伍断后位置", "mood": "沉稳"},
            ],
            "quests": [{"title": "探索星陨古天文台", "status": "进行中", "progress": "破解第一道星象闸门"}],
            "clocks": [{"name": "遗迹坍塌倒计时", "current": 1, "max": 8, "kind": "threat"}],
            "scene": {"time": "黄昏入夜", "location": "星陨裂谷·古天文台外厅", "condition": "星铁磁力异常"},
        },
        "opening_greetings": [
            {
                "id": "og_party_1",
                "title": "遗迹三岔口（推荐群聊开局）",
                "content": "夕阳最后一道余晖没入裂谷。你们四人刚刚撬开覆满藤蔓的古天文台石门，迎面出现三条截然不同的通道：左侧传来轻微齿轮滴答声；中间石碑刻着星象残缺谜题；右侧隐约飘出焦糖混合硫磺的古怪气味。林夜单膝蹲下检查地上新鲜脚印，霍渊默默把断剑横在身前，苏糖已经迫不及待举起了发光试剂瓶：「队长！走哪边？这瓶药剂我可刚调好！」",
            },
        ],
        "world_book": [
            _wb(1, "星陨边境规则（常驻）", [], "星陨裂谷是古代星辰陨落形成的奇异遗迹，越往深处星铁浓度越高，罗盘会失灵，但星铁武器会发出微光。", constant=True),
            _wb(2, "林夜的默契", ["林夜", "陷阱", "弩", "脚印"], "林夜极擅长发现机关暗线和追踪痕迹，他曾独自在裂谷存活半年，其实隐瞒着寻找失踪妹妹的私心。", group="登场人物设定"),
            _wb(3, "苏糖的背包", ["苏糖", "药剂", "炸弹", "炼金"], "苏糖的药剂往往威力惊人但附带奇怪颜色的烟雾或滑稽副作用，遇上古文字时她能用荧光显影液快速还原。", group="登场人物设定"),
            _wb(4, "霍渊的断剑", ["霍渊", "断剑", "防御", "护卫"], "霍渊手中半截陨铁大剑能硬抗塌方与机械守卫重击，他平时只说三个字以内，危急关头却永远挡在队友身前。", group="登场人物设定"),
        ],
        "bundled_cards": [
            {
                "id": "card_linye",
                "name": "林夜",
                "description": "黑发冷峻的战术斥候，手持精密折叠连弩，永远提前算好两条退路。",
                "personality": "冷静毒舌但极其靠谱，习惯优先评估风险。",
                "scenario": "星陨遗迹小队斥候。",
            },
            {
                "id": "card_sutang",
                "name": "苏糖",
                "description": "背着比人还高的黄铜药水箱的元气炼金术师，眼里只有稀奇材料与大爆炸。",
                "personality": "话痨好奇、乐观大胆，容易把小事搞成大场面。",
                "scenario": "星陨遗迹小队技术支援。",
            },
            {
                "id": "card_huoyuan",
                "name": "霍渊",
                "description": "身披磨损披风的沉默断剑客，肩扛陨铁断剑，存在感如磐石般令人安心。",
                "personality": "极度寡言、行动力极强、信守承诺。",
                "scenario": "星陨遗迹小队前锋护卫。",
            },
        ],
    })

    return [c1, c2, c3, c4, c5]


DEFAULT_PROJECTS_MAP = _build_default_projects()
EXPLORE_PRESET_APPS: List[Dict[str, Any]] = _build_flagship_campaigns()


def ensure_default_projects_in_db(db: Any) -> None:
    """Ensure the 3 default starter projects exist in user SQLite DB (non-destructive)."""
    existing_ids = {p["id"] for p in db.list_projects()}
    for pid, proj in DEFAULT_PROJECTS_MAP.items():
        if pid not in existing_ids:
            db.save_project(copy.deepcopy(proj))
