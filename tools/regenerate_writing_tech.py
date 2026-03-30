"""重新生成写作技巧JSON文件 - 使用正确的JSON格式"""
import json
from pathlib import Path

# 定义写作技巧数据
writing_techniques = {
    "narrative": [
        {
            "knowledge_id": "writing_technique-narrative-001",
            "category": "writing_technique",
            "domain": "narrative",
            "title": "第一人称叙事",
            "content": "第一人称叙事是以'我'为视角展开叙述的写作手法。核心特点包括限制性视角、强代入感和主观性强。适用场景有心理小说、成长小说、日记体小说等。经典案例如《洛丽塔》《了不起的盖茨比》《麦田里的守望者》。写作要点：保持'我'的视角限制，通过'我'的心理活动塑造性格，注意叙述者的可靠性。",
            "keywords": ["第一人称", "叙事视角", "限制视角", "代入感", "主观性", "不可靠叙述"],
            "references": ["《洛丽塔》", "《了不起的盖茨比》", "《麦田里的守望者》", "《叙事学导论》"],
            "difficulty": "basic",
            "tags": ["叙事技巧", "基础", "视角"],
            "metadata": {
                "source": "literature",
                "confidence": 0.95,
                "language": "zh",
                "author": "后端架构师",
                "reference_type": "mandatory",
                "priority": 1.0
            }
        },
        {
            "knowledge_id": "writing_technique-narrative-002",
            "category": "writing_technique",
            "domain": "narrative",
            "title": "第三人称叙事",
            "content": "第三人称叙事是以'他/她'为视角展开叙述的写作手法。核心特点包括全知视角或限制视角、客观性强、灵活性高。适用场景有史诗小说、多线索小说、传统小说等。经典案例如《红楼梦》《战争与和平》《百年孤独》。写作要点：选择合适的视角类型，避免视角混乱，合理控制信息量。",
            "keywords": ["第三人称", "全知视角", "限制视角", "客观性", "灵活性", "多视角"],
            "references": ["《红楼梦》", "《战争与和平》", "《百年孤独》", "《叙事学》"],
            "difficulty": "basic",
            "tags": ["叙事技巧", "基础", "视角"],
            "metadata": {
                "source": "literature",
                "confidence": 0.95,
                "language": "zh",
                "author": "后端架构师",
                "reference_type": "mandatory",
                "priority": 1.0
            }
        }
    ],
    "description": [
        {
            "knowledge_id": "writing_technique-description-001",
            "category": "writing_technique",
            "domain": "description",
            "title": "心理描写",
            "content": "心理描写是通过文字表现人物内心世界的技巧。核心特点包括展现人物性格、推动情节发展、增强代入感。常用方法有内心独白、行为暗示、环境烘托。经典案例如《罪与罚》《少年维特的烦恼》《追忆似水年华》。写作要点：避免过度心理描写，结合行为和环境，注意心理描写的真实性。",
            "keywords": ["心理描写", "内心世界", "内心独白", "行为暗示", "环境烘托", "性格展现"],
            "references": ["《罪与罚》", "《少年维特的烦恼》", "《追忆似水年华》", "《心理描写艺术》"],
            "difficulty": "intermediate",
            "tags": ["描写技巧", "中级", "心理", "人物"],
            "metadata": {
                "source": "literature",
                "confidence": 0.95,
                "language": "zh",
                "author": "后端架构师",
                "reference_type": "mandatory",
                "priority": 1.0
            }
        }
    ],
    "rhetoric": [
        {
            "knowledge_id": "writing_technique-rhetoric-001",
            "category": "writing_technique",
            "domain": "rhetoric",
            "title": "比喻",
            "content": "比喻是通过两个事物的相似点进行类比的修辞手法。核心特点包括形象生动、创造联想、传达情感。三种类型：明喻（用'像'连接）、暗喻（用'是'连接）、借喻（直接用喻体）。经典案例如钱钟书《围城》中的比喻、鲁迅《阿Q正传》中的比喻。写作要点：喻体要熟悉，比喻要新颖，避免陈词滥调。",
            "keywords": ["比喻", "明喻", "暗喻", "借喻", "形象", "联想", "修辞"],
            "references": ["《围城》", "《阿Q正传》", "《修辞学》", "《比喻艺术》"],
            "difficulty": "basic",
            "tags": ["修辞技巧", "基础", "比喻"],
            "metadata": {
                "source": "literature",
                "confidence": 0.95,
                "language": "zh",
                "author": "后端架构师",
                "reference_type": "mandatory",
                "priority": 1.0
            }
        }
    ]
}

# 保存文件
kb_dir = Path(r"E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\data\knowledge")

for domain, items in writing_techniques.items():
    output_file = kb_dir / f"writing_technique_{domain}.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    
    print(f"Generated: {output_file.name} ({len(items)} items)")

print("\nDone!")
