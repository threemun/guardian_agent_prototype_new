from __future__ import annotations

import datetime as dt
import math
import os
import re
import uuid
import wave
from pathlib import Path
from typing import Any
from urllib import request

from .db import ROOT_DIR, dumps, now_iso, row_to_dict, rows_to_dicts, today_str


SAMPLE_AUDIO_DIR = ROOT_DIR / "samples" / "audio"


MOCK_CALLS: list[dict[str, Any]] = [
    {
        "key": "mom_childhood_courtyard",
        "title": "院子里的夏夜",
        "elder_id": "E001",
        "family_member": "王女士",
        "memory_date": "1972-07-18",
        "recorded_offset_days": 0,
        "emotion": "怀旧",
        "transcript": "妈妈：1972年夏天，我住在外婆家的小院里，傍晚井水很凉，西瓜放进木桶里镇着。女儿：听起来很舒服。妈妈：最舒服的是屋檐下那盏小灯，邻居们搬着竹椅说笑，你外公下班回来，还会带一包糖炒栗子。",
    },
    {
        "key": "mom_daughter_kindergarten",
        "title": "第一朵小红花",
        "elder_id": "E001",
        "family_member": "王女士",
        "memory_date": "1999-09-01",
        "recorded_offset_days": 1,
        "emotion": "欣慰",
        "transcript": "妈妈：1999年你第一天上幼儿园，刚进门还牵着我的衣角。后来老师给你一朵小红花，你一路举着给我看。女儿：原来我这么快就笑了。妈妈：是啊，那天我就觉得你有自己的小勇气了。",
    },
    {
        "key": "daughter_project_launch",
        "title": "项目上线后的汤",
        "elder_id": "E001",
        "family_member": "王女士",
        "memory_date": "2026-06-28",
        "recorded_offset_days": 2,
        "emotion": "鼓励",
        "transcript": "女儿：妈，项目终于上线了，大家一起把最后一版方案改得很漂亮。妈妈：我就知道你做得到。女儿：周末我想回家吃饭。妈妈：那我煮莲藕汤，你慢慢讲给我听。",
    },
    {
        "key": "family_recipe_noodles",
        "title": "一碗手擀面",
        "elder_id": "E001",
        "family_member": "王女士",
        "memory_date": "1986-02-09",
        "recorded_offset_days": 3,
        "emotion": "温暖",
        "transcript": "妈妈：1986年春节前，你外婆教我擀面，面板上撒一层薄薄的粉。女儿：所以你现在的面还是那个味道。妈妈：对，一碗面传下来，家里人坐在一起，味道就不会散。",
    },
    {
        "key": "old_photo_red_sweater",
        "title": "红毛衣照片",
        "elder_id": "E001",
        "family_member": "王女士",
        "memory_date": "2003-01-26",
        "recorded_offset_days": 4,
        "emotion": "喜悦",
        "transcript": "女儿：我翻到一张照片，我穿着红毛衣站在雪地里。妈妈：那是2003年冬天，你非要把围巾系成蝴蝶结。女儿：照片里你笑得很开心。妈妈：因为那天你一路踩雪，一路唱歌。",
    },
    {
        "key": "morning_market",
        "title": "清晨菜市场",
        "elder_id": "E001",
        "family_member": "王女士",
        "memory_date": "2011-05-12",
        "recorded_offset_days": 5,
        "emotion": "安心",
        "transcript": "妈妈：2011年我常带你去早市，摊主远远就招呼我们。女儿：我记得你会挑最嫩的青菜。妈妈：那时候你拎着小布袋跟在旁边，我觉得一天从菜篮子里就开始亮了。",
    },
    {
        "key": "granddaughter_calligraphy",
        "title": "外孙女写春联",
        "elder_id": "E001",
        "family_member": "王女士",
        "memory_date": "2024-02-08",
        "recorded_offset_days": 6,
        "emotion": "自豪",
        "transcript": "女儿：今年外孙女写的春联贴在门口了。妈妈：我看见照片了，横平竖直，很有精神。女儿：她说想学你以前写字的样子。妈妈：这就很好，家里的年味又多了一笔。",
    },
    {
        "key": "balcony_flowers",
        "title": "阳台上的花",
        "elder_id": "E001",
        "family_member": "王女士",
        "memory_date": "2025-04-16",
        "recorded_offset_days": 7,
        "emotion": "喜悦",
        "transcript": "妈妈：阳台那盆月季开了三朵，早晨一推窗就看见。女儿：你拍照给我，我想看看。妈妈：好，我还给它换了新土。花开的时候，屋子里也像有人轻轻笑了一下。",
    },
    {
        "key": "community_dance",
        "title": "广场舞的新朋友",
        "elder_id": "E001",
        "family_member": "王女士",
        "memory_date": "2023-10-03",
        "recorded_offset_days": 8,
        "emotion": "开朗",
        "transcript": "妈妈：2023年秋天，我在小区广场认识了几个新朋友。女儿：你们是不是一起跳舞？妈妈：对，她们还教我新的步子。音乐一响，大家笑着排好队，晚风都变热闹了。",
    },
    {
        "key": "rainy_library",
        "title": "雨天图书馆",
        "elder_id": "E001",
        "family_member": "王女士",
        "memory_date": "2008-06-21",
        "recorded_offset_days": 9,
        "emotion": "宁静",
        "transcript": "女儿：我小时候你带我去图书馆，外面下着雨。妈妈：2008年夏天，你坐在窗边看童话书。女儿：我还记得雨声。妈妈：那天很安静，我看着你翻页，觉得时间慢得刚刚好。",
    },
    {
        "key": "dad_factory_badge",
        "title": "旧厂牌",
        "elder_id": "E002",
        "family_member": "张先生",
        "memory_date": "1978-03-05",
        "recorded_offset_days": 10,
        "emotion": "自豪",
        "transcript": "张爷爷：1978年我进厂第一天，胸前挂着新的厂牌，亮得很。儿子：你还留着吗？张爷爷：留着，放在抽屉里。那时候大家一起学技术，手上沾着机油，心里却很有劲。",
    },
    {
        "key": "father_teaches_bicycle",
        "title": "学骑车的巷口",
        "elder_id": "E002",
        "family_member": "张先生",
        "memory_date": "1996-05-20",
        "recorded_offset_days": 11,
        "emotion": "鼓励",
        "transcript": "张爷爷：1996年你学骑自行车，我扶着后座在巷口跑了好几圈。儿子：后来你松手了吗？张爷爷：松了，你自己骑出去一小段，还回头喊我。那一声喊，我到现在都记得。",
    },
    {
        "key": "family_chess_table",
        "title": "饭后棋盘",
        "elder_id": "E002",
        "family_member": "张先生",
        "memory_date": "2001-08-14",
        "recorded_offset_days": 12,
        "emotion": "温暖",
        "transcript": "儿子：小时候吃完饭，你总在桌上摆棋。张爷爷：2001年暑假，你外公也常来，一家人围着棋盘出主意。儿子：我总悔棋。张爷爷：你悔棋的时候，大家笑得最响。",
    },
    {
        "key": "repair_radio",
        "title": "修好的收音机",
        "elder_id": "E002",
        "family_member": "张先生",
        "memory_date": "1989-11-02",
        "recorded_offset_days": 13,
        "emotion": "成就",
        "transcript": "张爷爷：1989年我修好一台老收音机，旋钮一转，声音就出来了。儿子：你以前手真巧。张爷爷：不是我一个人巧，是你奶奶在旁边递螺丝刀，我们俩配合得好。",
    },
    {
        "key": "new_home_keys",
        "title": "新家的钥匙",
        "elder_id": "E002",
        "family_member": "张先生",
        "memory_date": "2006-12-30",
        "recorded_offset_days": 14,
        "emotion": "安心",
        "transcript": "儿子：我们搬新家的那天，你把钥匙递给我。张爷爷：2006年底，屋里还没有多少家具，但窗户很亮。儿子：你说以后这里会很热闹。张爷爷：后来果然热闹，饭香和笑声慢慢把房子填满了。",
    },
    {
        "key": "tea_with_neighbor",
        "title": "邻居家的茶",
        "elder_id": "E002",
        "family_member": "张先生",
        "memory_date": "2018-09-09",
        "recorded_offset_days": 15,
        "emotion": "友善",
        "transcript": "张爷爷：2018年楼下邻居搬来，第一次见面就请我喝茶。儿子：后来你们常聊天。张爷爷：是啊，他讲老城的变化，我讲厂里的旧事。茶杯一端起来，陌生人也变熟了。",
    },
    {
        "key": "park_walk",
        "title": "公园晨走",
        "elder_id": "E002",
        "family_member": "张先生",
        "memory_date": "2025-05-06",
        "recorded_offset_days": 16,
        "emotion": "舒展",
        "transcript": "张爷爷：最近我每天早上去公园走一圈，湖边的柳树长得很好。儿子：步数也比以前多了。张爷爷：走完回来喝一杯温水，整个人都松快，像把一天的门慢慢打开。",
    },
    {
        "key": "grandson_math",
        "title": "孙子的小奖状",
        "elder_id": "E002",
        "family_member": "张先生",
        "memory_date": "2024-11-18",
        "recorded_offset_days": 17,
        "emotion": "自豪",
        "transcript": "儿子：孙子这次数学比赛拿了小奖状。张爷爷：我看见照片了，眼睛亮亮的。儿子：他说想拿给你看。张爷爷：那我得把抽屉腾一格，专门放他的奖状。",
    },
    {
        "key": "winter_dumplings",
        "title": "冬至饺子",
        "elder_id": "E002",
        "family_member": "张先生",
        "memory_date": "2022-12-22",
        "recorded_offset_days": 18,
        "emotion": "团圆",
        "transcript": "张爷爷：2022年冬至，我们包了三种馅的饺子。儿子：你负责擀皮，我负责包。张爷爷：你包得不算圆，但一锅煮出来，大家都说香。家里热气一升，冬天就不冷了。",
    },
    {
        "key": "old_song",
        "title": "老歌和午后",
        "elder_id": "E002",
        "family_member": "张先生",
        "memory_date": "1992-04-10",
        "recorded_offset_days": 19,
        "emotion": "怀旧",
        "transcript": "儿子：你以前午后总放那首老歌。张爷爷：1992年买的磁带，放了很多遍。儿子：我现在听到前奏就想起客厅。张爷爷：一首歌能把人带回家，这就是它的本事。",
    },
    {
        "key": "grandma_embroidery",
        "title": "绣花手帕",
        "elder_id": "E003",
        "family_member": "李女士",
        "memory_date": "1969-06-03",
        "recorded_offset_days": 20,
        "emotion": "珍惜",
        "transcript": "李奶奶：1969年我学绣花，第一块手帕绣得歪歪扭扭。女儿：你后来绣得很好。李奶奶：是你姥姥一点点教我。针脚慢下来，心也跟着安静下来。",
    },
    {
        "key": "daughter_piano",
        "title": "客厅里的琴声",
        "elder_id": "E003",
        "family_member": "李女士",
        "memory_date": "2002-03-17",
        "recorded_offset_days": 21,
        "emotion": "欣慰",
        "transcript": "李奶奶：2002年你练琴，客厅里每天都有断断续续的旋律。女儿：我那时候弹得不熟。李奶奶：可我爱听，因为每一遍都比上一遍更稳。家里有琴声，就像窗户开着。",
    },
    {
        "key": "family_trip_lake",
        "title": "湖边合影",
        "elder_id": "E003",
        "family_member": "李女士",
        "memory_date": "2015-10-04",
        "recorded_offset_days": 22,
        "emotion": "喜悦",
        "transcript": "女儿：2015年我们去湖边拍的合影还在相册里。李奶奶：那天阳光很好，你爸爸把相机架了三次。女儿：大家都笑场。李奶奶：笑场也好，照片里就有活气。",
    },
    {
        "key": "festival_lanterns",
        "title": "灯笼下的团圆饭",
        "elder_id": "E003",
        "family_member": "李女士",
        "memory_date": "2019-02-19",
        "recorded_offset_days": 23,
        "emotion": "团圆",
        "transcript": "李奶奶：2019年元宵节，门口挂着两个红灯笼。女儿：那晚你做了汤圆。李奶奶：芝麻馅的最受欢迎。灯笼一亮，桌上的碗也亮，大家说话都轻快。",
    },
    {
        "key": "garden_tomatoes",
        "title": "小番茄成熟了",
        "elder_id": "E003",
        "family_member": "李女士",
        "memory_date": "2023-07-08",
        "recorded_offset_days": 24,
        "emotion": "喜悦",
        "transcript": "女儿：你种的小番茄是不是红了？李奶奶：红了，2023年夏天结得特别好。女儿：下次我回来尝尝。李奶奶：我给你留最圆的那几个，洗干净放在白盘子里。",
    },
    {
        "key": "wardrobe_scarf",
        "title": "衣柜里的围巾",
        "elder_id": "E003",
        "family_member": "李女士",
        "memory_date": "2007-12-11",
        "recorded_offset_days": 25,
        "emotion": "温暖",
        "transcript": "李奶奶：2007年冬天，你给我买了一条浅蓝色围巾。女儿：你还留着吗？李奶奶：留着，放在衣柜上层。每次拿出来，都像把那年冬天也拿出来晒了晒。",
    },
    {
        "key": "neighbor_music_group",
        "title": "合唱队的下午",
        "elder_id": "E003",
        "family_member": "李女士",
        "memory_date": "2024-04-25",
        "recorded_offset_days": 26,
        "emotion": "开朗",
        "transcript": "李奶奶：社区合唱队下午排练，我站在第二排。女儿：你最喜欢哪首歌？李奶奶：那首节奏轻快的。大家一开口，屋子里就像有一条明亮的小河。",
    },
    {
        "key": "daughter_first_salary",
        "title": "第一份工资的蛋糕",
        "elder_id": "E003",
        "family_member": "李女士",
        "memory_date": "2010-08-31",
        "recorded_offset_days": 27,
        "emotion": "自豪",
        "transcript": "女儿：我第一份工资买了蛋糕回家。李奶奶：2010年夏末，你把蛋糕放在桌上，说请大家吃。女儿：你当时眼睛红红的。李奶奶：我是高兴，觉得你把自己的路走出来了。",
    },
    {
        "key": "handwritten_letter",
        "title": "抽屉里的信",
        "elder_id": "E003",
        "family_member": "李女士",
        "memory_date": "1998-10-12",
        "recorded_offset_days": 28,
        "emotion": "珍惜",
        "transcript": "李奶奶：1998年你在学校写给我的信，我还收着。女儿：我写了什么？李奶奶：你说食堂的包子很好吃，还画了一个笑脸。字不多，但我读了很多遍。",
    },
    {
        "key": "video_call_reunion",
        "title": "屏幕里的晚饭",
        "elder_id": "E003",
        "family_member": "李女士",
        "memory_date": "2026-07-05",
        "recorded_offset_days": 29,
        "emotion": "期待",
        "transcript": "女儿：下周我带孩子回来看你。李奶奶：好，我把你们爱吃的菜列出来。女儿：今晚视频里先看一眼菜单。李奶奶：屏幕这边也热闹，像晚饭已经提前摆上桌。",
    },
]


SAMPLE_TRANSCRIPTS = {item["key"]: item["transcript"] for item in MOCK_CALLS}

MOCK_STORY_SUMMARIES = {
    "mom_childhood_courtyard": "妈妈回忆1972年夏天住在外婆小院的夜晚，先讲井水冰西瓜和屋檐小灯，女儿回应听起来舒服，妈妈又补充邻居聊天和外公下班带糖炒栗子的细节。",
    "mom_daughter_kindergarten": "妈妈讲起女儿1999年第一天上幼儿园的经过，从进门牵着衣角，到拿到小红花后一路举给妈妈看；女儿回想自己很快笑了，妈妈把那天看作女儿长出小勇气的开始。",
    "daughter_project_launch": "女儿告诉妈妈项目终于上线，团队一起改好了最后一版方案；妈妈给予肯定，女儿说周末想回家吃饭，妈妈回应会煮莲藕汤并听她慢慢讲。",
    "family_recipe_noodles": "妈妈回忆1986年春节前跟外婆学擀面，女儿把这件事和现在家里的面味联系起来；妈妈最后说，一碗面传下来，家里人坐在一起，味道就不会散。",
    "old_photo_red_sweater": "女儿翻到自己穿红毛衣站在雪地里的照片，妈妈说明那是2003年冬天，还记得女儿把围巾系成蝴蝶结；两人接着聊到照片里的笑和一路踩雪唱歌。",
    "morning_market": "妈妈回忆2011年常带女儿去早市，菜摊主人会远远招呼她们；女儿记得妈妈会挑嫩青菜，妈妈补充女儿拎着小布袋跟在旁边，让一天从菜篮子里亮起来。",
    "granddaughter_calligraphy": "女儿告诉妈妈外孙女写的春联已经贴在门口，妈妈看过照片并称赞字有精神；女儿说孩子想学妈妈以前写字的样子，妈妈觉得家里的年味又多了一笔。",
    "balcony_flowers": "妈妈讲阳台上的月季早晨一推窗就能看见，女儿想让妈妈拍照；妈妈答应拍给她看，并补充自己已经给花换了新土。",
    "community_dance": "妈妈说自己2023年秋天在小区广场认识了新朋友，女儿追问她们是不是一起跳舞；妈妈讲朋友教她新的步子，大家随着音乐排队跳起来。",
    "rainy_library": "女儿回忆小时候妈妈带她去图书馆的雨天，妈妈补充那是2008年夏天，女儿坐在窗边看童话书；两人一起把雨声和安静阅读的场景留了下来。",
    "dad_factory_badge": "张爷爷回忆1978年进厂第一天胸前挂着新厂牌，儿子问厂牌是否还留着；张爷爷说它放在抽屉里，并补充那时大家一起学技术、手上有机油但心里有劲。",
    "father_teaches_bicycle": "张爷爷讲1996年教儿子学骑自行车，自己扶着后座在巷口跑了好几圈；儿子问后来是否松手，张爷爷回忆儿子独自骑出一小段后回头喊他的瞬间。",
    "family_chess_table": "儿子提起小时候饭后家里总摆棋盘，张爷爷说明2001年暑假外公也常来，一家人围着棋盘出主意；儿子说自己常悔棋，张爷爷记得大家因此笑得最响。",
    "repair_radio": "张爷爷回忆1989年修好一台旧收音机，儿子称赞他手巧；张爷爷说明这不是一个人的功劳，是奶奶在旁边递螺丝刀，两个人配合才修好。",
    "new_home_keys": "儿子回忆搬进新家那天张爷爷把钥匙递给他，张爷爷补充2006年底屋里家具不多但窗户很亮；两人接着聊到后来饭香和笑声把房子慢慢填满。",
    "tea_with_neighbor": "张爷爷讲2018年楼下邻居搬来，第一次见面就请他喝茶；儿子说他们后来常聊天，张爷爷补充两人从老城变化聊到厂里旧事，关系也熟络起来。",
    "park_walk": "张爷爷说最近每天早上去公园绕湖走一圈，儿子注意到步数比以前多；张爷爷补充走完回来喝温水，整个人都松快。",
    "grandson_math": "儿子告诉张爷爷孙子数学比赛拿了小奖状，张爷爷说自己看过照片，孩子眼睛亮亮的；儿子说孙子想拿给爷爷看，张爷爷打算专门腾抽屉收奖状。",
    "winter_dumplings": "张爷爷回忆2022年冬至一家人包三种馅的饺子，儿子负责包，他负责擀皮；张爷爷笑说儿子包得不算圆，但一锅煮出来大家都说香。",
    "old_song": "儿子提起张爷爷以前午后总放一首老歌，张爷爷说那是1992年买的磁带，已经放过很多遍；儿子说前奏会让他想起客厅，张爷爷回应一首歌能把人带回家。",
    "grandma_embroidery": "李奶奶回忆1969年学绣花，第一块手帕绣得歪歪扭扭；女儿说她后来绣得很好，李奶奶补充是姨姥一点点教她，针脚慢下来心也安静下来。",
    "daughter_piano": "李奶奶回忆2002年女儿练琴，客厅里每天都有断断续续的旋律；女儿说自己那时弹得不熟，李奶奶回应她爱听，因为每一遍都比上一遍更稳。",
    "family_trip_lake": "女儿提起2015年一家人在湖边拍的合影还在相册里，李奶奶补充那天阳光很好，爸爸把相机架了三次；两人接着聊到大家都笑场，照片因此有了活气。",
    "festival_lanterns": "李奶奶回忆2019年元宵节门口挂着红灯笼，女儿记得那晚她做了汤圆；李奶奶补充芝麻馅最受欢迎，灯笼亮起来后桌上的碗也显得热闹。",
    "garden_tomatoes": "女儿问李奶奶种的小番茄是不是红了，李奶奶说2023年夏天结得很好；女儿说下次回来尝，李奶奶答应把最圆的几颗洗净留在白盘子里。",
    "wardrobe_scarf": "李奶奶回忆2007年冬天女儿给她买过一条浅蓝色围巾，女儿问她是否还留着；李奶奶说围巾放在衣柜上层，每次拿出来都会想起那年冬天。",
    "neighbor_music_group": "李奶奶讲社区合唱队下午排练，自己站在第二排；女儿问她最喜欢哪首歌，李奶奶说喜欢节奏轻快的那首，大家一开口屋子就亮起来。",
    "daughter_first_salary": "女儿回忆第一份工资买了蛋糕回家，李奶奶补充那是2010年夏末，女儿把蛋糕放在桌上请大家吃；女儿记得妈妈眼睛红红的，李奶奶说那是高兴。",
    "handwritten_letter": "李奶奶说还收着女儿1998年在学校写给她的信，女儿追问信里写了什么；李奶奶记得女儿提到食堂包子好吃，还画了一个笑脸，字不多却读了很多遍。",
    "video_call_reunion": "女儿说下周会带孩子回来看李奶奶，李奶奶准备把大家爱吃的菜列出来；女儿提议今晚视频里先看菜单，李奶奶回应屏幕这边也像提前摆好了晚饭。",
}


TOPIC_KEYWORDS = {
    "童年旧事": ["小时候", "外婆", "小院", "井水", "屋檐", "糖炒栗子", "图书馆"],
    "子女成长": ["幼儿园", "小红花", "学骑", "练琴", "第一份工资", "奖状"],
    "家常饭菜": ["汤", "手擀面", "饺子", "汤圆", "蛋糕", "菜", "早市"],
    "邻里社区": ["邻居", "社区", "广场", "合唱队", "朋友", "跳舞"],
    "老物件": ["照片", "厂牌", "收音机", "磁带", "手帕", "围巾", "信"],
    "花草生活": ["阳台", "花", "月季", "番茄", "新土"],
    "工作成长": ["项目", "上线", "方案", "工作"],
    "家庭团圆": ["春节", "冬至", "元宵", "回家", "晚饭", "团圆"],
}


EMOTION_KEYWORDS = {
    "怀旧": ["小时候", "那时候", "老歌", "旧", "相册", "磁带", "厂牌"],
    "温暖": ["家", "围巾", "汤", "晚饭", "笑声", "屋子", "桌上"],
    "欣慰": ["小勇气", "练琴", "更稳", "长大", "自己的路"],
    "喜悦": ["笑", "开", "红了", "唱歌", "阳光", "热闹"],
    "自豪": ["奖状", "做得到", "很有精神", "第一份工资", "技术"],
    "安心": ["安静", "钥匙", "温水", "房子", "慢慢"],
    "期待": ["下周", "回来", "菜单", "想看看", "留"],
    "珍惜": ["收着", "留着", "很多遍", "手帕", "抽屉"],
    "开朗": ["朋友", "音乐", "排练", "步子", "轻快"],
    "团圆": ["一家人", "大家", "团圆", "冬至", "元宵"],
}


KNOWN_PEOPLE = [
    "王爷爷",
    "张爷爷",
    "李奶奶",
    "妈妈",
    "女儿",
    "儿子",
    "外婆",
    "外公",
    "奶奶",
    "姥姥",
    "爸爸",
    "老师",
    "邻居",
    "孙子",
    "外孙女",
]


NEGATIVE_WORDS = ["难过", "害怕", "失望", "吵架", "孤单", "疼痛", "摔倒", "生气", "严重", "痛苦"]


class MemoryAgent:
    """Call recording to family-memory extraction pipeline."""

    def __init__(self, conn):
        self.conn = conn

    def ingest_call_recording(self, payload: dict[str, Any]) -> dict[str, Any]:
        elder_id = payload.get("elder_id", "E001")
        family_member = payload.get("family_member", "子女")
        mock_key = payload.get("mock_key") or Path(payload.get("audio_uri", "")).stem
        audio_uri = payload.get("audio_uri") or str(sample_audio_path(mock_key or "mom_childhood_courtyard"))
        transcript = payload.get("transcript") or self._transcribe(audio_uri, mock_key)
        call_started_at = payload.get("call_started_at") or now_iso()
        recording_id = payload.get("recording_id") or f"call_{uuid.uuid4().hex[:12]}"
        duration = int(payload.get("audio_duration_seconds") or estimate_duration_seconds(audio_uri, transcript))
        mock_meta = get_mock_call(mock_key)
        memory_date = payload.get("memory_date") or payload.get("event_date") or (mock_meta or {}).get("memory_date") or today_str()

        self.conn.execute(
            """
            INSERT INTO call_recordings
            (id, elder_id, family_member, call_started_at, audio_uri, audio_duration_seconds,
             transcript, stt_provider, status, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                recording_id,
                elder_id,
                family_member,
                call_started_at,
                audio_uri,
                duration,
                transcript,
                os.getenv("STT_PROVIDER", "mock"),
                "analyzed",
                dumps(
                    {
                        "mock_key": mock_key,
                        "memory_date": memory_date,
                        "pipeline": ["audio_ingest", "speech_to_text", "whole_dialogue_memory", "positive_filter", "entity_extract", "story_plot_summary"],
                    }
                ),
                now_iso(),
            ),
        )
        fallback_title = payload.get("title") or (mock_meta or {}).get("title") or ""
        segments = self._extract_segments(recording_id, elder_id, transcript, memory_date, fallback_title, mock_key)
        self.conn.commit()
        return {"recording": self.get_recording(recording_id), "segments": segments}

    def create_mock_memory(self, mock_key: str = "mom_childhood_courtyard", elder_id: str | None = None) -> dict[str, Any]:
        ensure_sample_audio_files()
        item = get_mock_call(mock_key) or MOCK_CALLS[0]
        base_date = dt.date.fromisoformat(today_str())
        call_date = base_date - dt.timedelta(days=int(item.get("recorded_offset_days", 0)))
        return self.ingest_call_recording(
            {
                "elder_id": elder_id or item["elder_id"],
                "family_member": item["family_member"],
                "audio_uri": str(sample_audio_path(item["key"])),
                "mock_key": item["key"],
                "call_started_at": f"{call_date.isoformat()}T20:10:00",
                "memory_date": item["memory_date"],
                "audio_duration_seconds": 72 + (abs(hash(item["key"])) % 80),
            }
        )

    def search_memories(
        self,
        query: str = "",
        person: str = "",
        emotion: str = "",
        topic: str = "",
        memory_start_date: str = "",
        memory_end_date: str = "",
        recorded_start_date: str = "",
        recorded_end_date: str = "",
        elder_id: str = "",
        limit: int = 60,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT ms.*, cr.call_started_at, cr.family_member, cr.audio_uri, cr.audio_duration_seconds
            FROM memory_segments ms
            JOIN call_recordings cr ON cr.id = ms.recording_id
            WHERE ms.sentiment_score >= 0.66
        """
        params: list[Any] = []
        if elder_id:
            sql += " AND ms.elder_id = ?"
            params.append(elder_id)
        if query:
            like = f"%{query}%"
            sql += " AND (ms.title LIKE ? OR ms.topic LIKE ? OR ms.event_summary LIKE ? OR ms.lyric_text LIKE ? OR ms.source_text LIKE ? OR ms.keywords_json LIKE ?)"
            params.extend([like, like, like, like, like, like])
        if person:
            like = f"%{person}%"
            sql += " AND (ms.people_json LIKE ? OR ms.source_text LIKE ? OR ms.keywords_json LIKE ?)"
            params.extend([like, like, like])
        if emotion:
            like = f"%{emotion}%"
            sql += " AND (ms.emotion = ? OR ms.keywords_json LIKE ? OR ms.entities_json LIKE ?)"
            params.extend([emotion, like, like])
        if topic:
            like = f"%{topic}%"
            sql += " AND (ms.topic = ? OR ms.keywords_json LIKE ? OR ms.event_summary LIKE ? OR ms.source_text LIKE ?)"
            params.extend([topic, like, like, like])
        if memory_start_date:
            sql += " AND ms.memory_date >= ?"
            params.append(memory_start_date)
        if memory_end_date:
            sql += " AND ms.memory_date <= ?"
            params.append(memory_end_date)
        if recorded_start_date:
            sql += " AND substr(cr.call_started_at, 1, 10) >= ?"
            params.append(recorded_start_date)
        if recorded_end_date:
            sql += " AND substr(cr.call_started_at, 1, 10) <= ?"
            params.append(recorded_end_date)
        sql += " ORDER BY ms.memory_date DESC, cr.call_started_at DESC, ms.created_at DESC LIMIT ?"
        params.append(limit)
        return rows_to_dicts(self.conn.execute(sql, params).fetchall())

    def facets(self, elder_id: str = "") -> dict[str, Any]:
        sql = "SELECT people_json, emotion, topic, memory_date FROM memory_segments WHERE sentiment_score >= 0.66"
        params: list[Any] = []
        if elder_id:
            sql += " AND elder_id = ?"
            params.append(elder_id)
        rows = self.conn.execute(sql, params).fetchall()
        people: set[str] = set()
        emotions: set[str] = set()
        topics: set[str] = set()
        years: set[str] = set()
        for row in rows:
            data = row_to_dict(row)
            people.update(data.get("people", []))
            if data.get("emotion"):
                emotions.add(data["emotion"])
            if data.get("topic"):
                topics.add(data["topic"])
            if data.get("memory_date"):
                years.add(data["memory_date"][:4])
        return {"people": sorted(people), "emotions": sorted(emotions), "topics": sorted(topics), "memory_years": sorted(years)}

    def latest_recordings(self, elder_id: str = "", limit: int = 10) -> list[dict[str, Any]]:
        sql = "SELECT * FROM call_recordings"
        params: list[Any] = []
        if elder_id:
            sql += " WHERE elder_id = ?"
            params.append(elder_id)
        sql += " ORDER BY call_started_at DESC, created_at DESC LIMIT ?"
        params.append(limit)
        return rows_to_dicts(self.conn.execute(sql, params).fetchall())

    def get_recording(self, recording_id: str) -> dict[str, Any] | None:
        return row_to_dict(self.conn.execute("SELECT * FROM call_recordings WHERE id = ?", (recording_id,)).fetchone())

    def _transcribe(self, audio_uri: str, mock_key: str) -> str:
        if os.getenv("STT_PROVIDER", "mock").lower() in {"funasr", "openai_compatible"}:
            return OpenAICompatibleTranscriber().transcribe(audio_uri)
        return MockTranscriber().transcribe(audio_uri, mock_key)

    def _extract_segments(
        self,
        recording_id: str,
        elder_id: str,
        transcript: str,
        fallback_memory_date: str,
        fallback_title: str = "",
        mock_key: str = "",
    ) -> list[dict[str, Any]]:
        full_dialogue = normalize_dialogue_text(transcript)
        chunks = [full_dialogue] if full_dialogue and is_positive_memory(full_dialogue) else []
        saved: list[dict[str, Any]] = []
        for order, chunk in enumerate(chunks, start=1):
            topic = classify_topic(chunk)
            people = extract_people(chunk)
            time_text = extract_time_text(chunk)
            memory_date = extract_memory_date(chunk, fallback_memory_date)
            emotion, score = classify_emotion(chunk)
            title = make_title(chunk, fallback_title, order)
            event_summary = summarize_event(chunk, topic, title)
            lyric_text = make_story_text(chunk, topic, people, time_text, emotion, title, mock_key)
            keywords = extract_keywords(chunk, topic, emotion)
            memory_id = f"mem_{uuid.uuid4().hex[:12]}"
            self.conn.execute(
                """
                INSERT INTO memory_segments
                (id, recording_id, elder_id, title, topic, memory_time_text, memory_date, people_json, emotion,
                 sentiment_score, event_summary, lyric_text, source_text, keywords_json, entities_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    recording_id,
                    elder_id,
                    title,
                    topic,
                    time_text,
                    memory_date,
                    dumps(people),
                    emotion,
                    score,
                    event_summary,
                    lyric_text,
                    full_dialogue,
                    dumps(keywords),
                    dumps(
                        {
                            "people": people,
                            "time": time_text,
                            "memory_date": memory_date,
                            "emotion": emotion,
                            "topic": topic,
                            "complete_dialogue": True,
                            "dialogue_turns": parse_dialogue_turns(full_dialogue),
                        }
                    ),
                    now_iso(),
                ),
            )
            saved.append(row_to_dict(self.conn.execute("SELECT * FROM memory_segments WHERE id = ?", (memory_id,)).fetchone()))
        return saved


class MockTranscriber:
    def transcribe(self, audio_uri: str, mock_key: str) -> str:
        key = mock_key if mock_key in SAMPLE_TRANSCRIPTS else Path(audio_uri).stem
        return SAMPLE_TRANSCRIPTS.get(key, SAMPLE_TRANSCRIPTS[MOCK_CALLS[0]["key"]])


class OpenAICompatibleTranscriber:
    """Adapter for FunASR/OpenAI-compatible ASR endpoints."""

    def transcribe(self, audio_uri: str) -> str:
        base_url = os.getenv("STT_BASE_URL", "")
        if not base_url:
            raise RuntimeError("STT_BASE_URL is required when STT_PROVIDER=funasr or openai_compatible")
        boundary = f"----GuardianAgent{uuid.uuid4().hex}"
        audio_path = Path(audio_uri)
        audio = audio_path.read_bytes()
        fields = {"model": os.getenv("STT_MODEL", "iic/SenseVoiceSmall"), "language": "zh"}
        body = build_multipart_body(boundary, fields, "file", audio_path.name, audio)
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        api_key = os.getenv("STT_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        req = request.Request(base_url, data=body, headers=headers, method="POST")
        with request.urlopen(req, timeout=120) as resp:
            data = resp.read().decode("utf-8")
        import json

        parsed = json.loads(data)
        return parsed.get("text") or parsed.get("transcript") or data


def build_multipart_body(boundary: str, fields: dict[str, str], file_field: str, filename: str, content: bytes) -> bytes:
    lines: list[bytes] = []
    for key, value in fields.items():
        lines.extend([f"--{boundary}".encode(), f'Content-Disposition: form-data; name="{key}"'.encode(), b"", value.encode("utf-8")])
    lines.extend(
        [
            f"--{boundary}".encode(),
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"'.encode(),
            b"Content-Type: audio/wav",
            b"",
            content,
            f"--{boundary}--".encode(),
            b"",
        ]
    )
    return b"\r\n".join(lines)


def split_by_topic(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    sentences = [part.strip() for part in re.split(r"(?<=[。！？?])", cleaned) if part.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_topic = ""
    for sentence in sentences:
        topic = classify_topic(sentence)
        if current and (len("".join(current)) > 150 or (current_topic and topic != current_topic)):
            chunks.append("".join(current))
            current = []
        current.append(sentence)
        current_topic = topic
    if current:
        chunks.append("".join(current))
    return chunks[:5]


def classify_topic(text: str) -> str:
    scores = {topic: sum(1 for word in words if word in text) for topic, words in TOPIC_KEYWORDS.items()}
    best_topic, score = max(scores.items(), key=lambda item: item[1])
    return best_topic if score else "家庭日常"


def extract_people(text: str) -> list[str]:
    people = [name for name in KNOWN_PEOPLE if name in text]
    speaker_matches = re.findall(r"([\u4e00-\u9fa5]{1,4})：", text)
    for speaker in speaker_matches:
        if speaker not in people:
            people.append(speaker)
    return people or ["家人"]


def extract_time_text(text: str) -> str:
    match = re.search(r"\d{4}年(?:春天|夏天|秋天|冬天|春节|元宵节|冬至|夏末)?", text)
    if match:
        return match.group(0)
    for pattern in ["小时候", "第一天", "最近", "周末", "下周", "早晨", "下午", "今晚"]:
        if pattern in text:
            return pattern
    return "这段通话"


def extract_memory_date(text: str, fallback: str) -> str:
    if fallback and fallback != today_str():
        return fallback
    match = re.search(r"(\d{4})年", text)
    if match:
        return f"{match.group(1)}-01-01"
    return fallback or today_str()


def classify_emotion(text: str) -> tuple[str, float]:
    scores = {emotion: sum(1 for word in words if word in text) for emotion, words in EMOTION_KEYWORDS.items()}
    emotion, score = max(scores.items(), key=lambda item: item[1])
    if score == 0:
        return "温暖", 0.70
    return emotion, min(0.96, 0.68 + score * 0.06)


def is_positive_memory(text: str) -> bool:
    return not any(word in text for word in NEGATIVE_WORDS)


def summarize_event(text: str, topic: str, title: str = "") -> str:
    turns = parse_dialogue_turns(text)
    if not turns:
        sentences = extract_clean_sentences(text)
        sentence = sentences[0] if sentences else strip_speakers(text)[:46]
        return trim_text(sentence, 46)
    first = summarize_turn_content(turns[0]["text"])
    last = summarize_turn_content(turns[-1]["text"])
    focus = title or topic
    if len(turns) == 1:
        return trim_text(f"围绕{focus}讲起{first}", 46)
    return trim_text(f"围绕{focus}，从{first}讲到{last}", 46)


def make_story_text(
    text: str,
    topic: str,
    people: list[str],
    time_text: str,
    emotion: str,
    title: str = "",
    mock_key: str = "",
) -> str:
    if mock_key in MOCK_STORY_SUMMARIES:
        return MOCK_STORY_SUMMARIES[mock_key]

    turns = parse_dialogue_turns(text)
    if not turns:
        sentences = extract_clean_sentences(text)
        if not sentences:
            return trim_text(strip_speakers(text), 120)
        return f"这段通话围绕{title or topic}展开，主要讲到{summarize_turn_content(sentences[0])}。"

    beats = []
    for index, turn in enumerate(turns[:5]):
        beats.append(summarize_dialogue_beat(turn, index, len(turns)))
    if len(turns) > 5:
        beats.append(f"最后，{turns[-1]['speaker']}把话题收束到{summarize_turn_content(turns[-1]['text'])}")

    focus = title or topic
    body = "；".join(beats)
    return f"这通电话围绕“{focus}”展开：{body}。"


def strip_speakers(text: str) -> str:
    return re.sub(r"[\u4e00-\u9fa5]{1,4}：", "", text).strip()


def normalize_dialogue_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_dialogue_turns(text: str) -> list[dict[str, str]]:
    cleaned = normalize_dialogue_text(text)
    parts = re.split(r"([\u4e00-\u9fa5]{1,6})：", cleaned)
    turns: list[dict[str, str]] = []
    preface = parts[0].strip()
    if len(parts) <= 1:
        return [{"speaker": "家人", "text": cleaned}] if cleaned else []
    for index in range(1, len(parts), 2):
        speaker = parts[index].strip()
        content = parts[index + 1].strip() if index + 1 < len(parts) else ""
        if content:
            turns.append({"speaker": speaker, "text": content})
    if preface and turns:
        turns[0]["text"] = f"{preface}{turns[0]['text']}"
    return turns


def summarize_dialogue_beat(turn: dict[str, str], index: int, total: int) -> str:
    speaker = turn["speaker"]
    content = summarize_turn_content(turn["text"])
    if index == 0:
        verb = "先讲起"
    elif index == total - 1:
        verb = "最后补充"
    elif "？" in turn["text"] or "吗" in turn["text"] or "是不是" in turn["text"]:
        verb = "追问"
    else:
        verb = "回应"
    return f"{speaker}{verb}{content}"


def summarize_turn_content(text: str) -> str:
    content = strip_speakers(text)
    content = re.sub(r"^(是啊|对|好|嗯|原来|那|所以)[，,。 ]*", "", content)
    content = re.sub(r"[。！？?]+$", "", content)
    phrase_rules = [
        ("小红花", "拿到小红花这件事"),
        ("幼儿园", "第一天上幼儿园的经过"),
        ("项目", "项目上线后的进展"),
        ("莲藕汤", "周末回家吃饭的安排"),
        ("擀面", "学做手擀面的经过"),
        ("红毛衣", "红毛衣雪地照片"),
        ("早市", "一起去早市买菜"),
        ("春联", "外孙女写春联"),
        ("月季", "阳台月季开花"),
        ("跳舞", "在广场学跳舞"),
        ("图书馆", "雨天去图书馆读书"),
        ("厂牌", "进厂第一天的旧厂牌"),
        ("自行车", "学骑自行车"),
        ("棋盘", "饭后围着棋盘聊天"),
        ("收音机", "一起修好旧收音机"),
        ("钥匙", "搬进新家时递钥匙"),
        ("邻居", "和邻居喝茶聊天"),
        ("公园", "早上去公园散步"),
        ("奖状", "孙子拿到小奖状"),
        ("饺子", "冬至一起包饺子"),
        ("老歌", "午后反复播放的老歌"),
        ("绣花", "学绣花手帕"),
        ("练琴", "客厅里练琴"),
        ("湖边", "湖边合影"),
        ("汤圆", "元宵节做汤圆"),
        ("番茄", "小番茄成熟"),
        ("围巾", "保存蓝色围巾"),
        ("合唱队", "社区合唱队排练"),
        ("第一份工资", "第一份工资买蛋糕"),
        ("信", "学校寄来的手写信"),
        ("晚饭", "视频里商量团圆饭"),
    ]
    for key, phrase in phrase_rules:
        if key in content:
            return phrase
    return trim_text(content, 30)


def trim_text(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", "", text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "..."


def extract_clean_sentences(text: str) -> list[str]:
    plain = strip_speakers(text)
    return [s.strip(" ，,。！？?") for s in re.split(r"[。！？?]", plain) if s.strip(" ，,。！？?")]


def limit_memory_title(title: str) -> str:
    cleaned = re.sub(r"[\s·，,。！？?：:；;、]", "", title)
    if "院子" in cleaned and "夏夜" in cleaned:
        return "院子夏夜"
    for suffix in ("的夏夜", "的上午", "的下午", "的一天", "后的汤", "后的家常"):
        cleaned = cleaned.replace(suffix, "")
    if len(cleaned) <= 10:
        return cleaned or "家庭片段"
    words = [
        "小红花",
        "项目上线",
        "手擀面",
        "红毛衣照片",
        "清晨菜市场",
        "春联",
        "阳台花",
        "广场舞",
        "图书馆",
        "旧厂牌",
        "学骑车",
        "饭后棋盘",
        "收音机",
        "新家钥匙",
        "邻居茶",
        "公园晨走",
        "小奖状",
        "冬至饺子",
        "午后老歌",
        "绣花手帕",
        "客厅琴声",
        "湖边合影",
        "元宵汤圆",
        "小番茄",
        "蓝色围巾",
        "合唱队",
        "工资蛋糕",
        "抽屉来信",
        "视频晚饭",
        "院子夏夜",
    ]
    for word in words:
        if word in cleaned:
            return word[:10]
    return cleaned[:10]


def make_title(text: str, fallback_title: str = "", order: int = 1) -> str:
    if fallback_title:
        return limit_memory_title(fallback_title)
    title_rules = [
        ("小红花", "小红花"),
        ("项目", "项目上线"),
        ("手擀面", "手擀面"),
        ("红毛衣", "红毛衣照片"),
        ("早市", "清晨菜市"),
        ("春联", "写春联"),
        ("月季", "阳台花开"),
        ("跳舞", "广场跳舞"),
        ("图书馆", "雨天读书"),
        ("厂牌", "旧厂牌"),
        ("自行车", "学骑车"),
        ("棋盘", "饭后棋局"),
        ("收音机", "修收音机"),
        ("钥匙", "新家钥匙"),
        ("邻居", "邻里喝茶"),
        ("公园", "公园晨走"),
        ("奖状", "小奖状"),
        ("饺子", "冬至饺子"),
        ("老歌", "午后老歌"),
        ("绣花", "绣花手帕"),
        ("练琴", "客厅琴声"),
        ("湖边", "湖边合影"),
        ("汤圆", "元宵汤圆"),
        ("番茄", "小番茄"),
        ("围巾", "蓝色围巾"),
        ("合唱队", "合唱队"),
        ("第一份工资", "工资蛋糕"),
        ("信", "抽屉来信"),
        ("晚饭", "视频晚饭"),
    ]
    for key, title in title_rules:
        if key in text:
            return title
    sentences = extract_clean_sentences(text)
    if sentences:
        cleaned = re.sub(r"[，,。！？?\s]", "", sentences[0])
        if cleaned:
            return limit_memory_title(cleaned)
    return f"家庭片段{order}"


def extract_keywords(text: str, topic: str, emotion: str) -> list[str]:
    words = [topic, emotion]
    for dictionary in (TOPIC_KEYWORDS, EMOTION_KEYWORDS):
        for values in dictionary.values():
            for word in values:
                if word in text and word not in words:
                    words.append(word)
    for person in extract_people(text):
        if person not in words:
            words.append(person)
    return words[:10]


def sample_audio_path(mock_key: str) -> Path:
    return SAMPLE_AUDIO_DIR / f"{mock_key}.wav"


def ensure_sample_audio_files() -> None:
    SAMPLE_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    expected = {f"{item['key']}.wav" for item in MOCK_CALLS}
    for old_file in SAMPLE_AUDIO_DIR.glob("*.wav"):
        if old_file.name not in expected:
            old_file.unlink()
    for index, item in enumerate(MOCK_CALLS):
        path = sample_audio_path(item["key"])
        if not path.exists():
            write_tone_wav(path, 260 + (index * 37) % 360, seconds=1.0 + (index % 5) * 0.18)


def write_tone_wav(path: Path, frequency: int, seconds: float = 1.2, sample_rate: int = 16000) -> None:
    frames = int(sample_rate * seconds)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for i in range(frames):
            value = int(1600 * math.sin(2 * math.pi * frequency * i / sample_rate))
            wav.writeframesraw(value.to_bytes(2, "little", signed=True))


def estimate_duration_seconds(audio_uri: str, transcript: str) -> int:
    path = Path(audio_uri)
    if path.exists():
        try:
            with wave.open(str(path), "rb") as wav:
                return max(1, int(wav.getnframes() / wav.getframerate()))
        except wave.Error:
            pass
    return max(20, len(transcript) // 4)


def get_mock_call(mock_key: str) -> dict[str, Any] | None:
    for item in MOCK_CALLS:
        if item["key"] == mock_key:
            return item
    return None
