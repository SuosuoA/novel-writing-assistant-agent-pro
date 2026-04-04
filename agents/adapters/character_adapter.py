"""
人物管理器适配器

V3.2版本
创建日期: 2026-03-21
更新日期: 2026-04-03 14:10
新增：
- batch_import操作支持（V3.0）
- edit_character操作支持（V3.1）
- get_character_detail操作支持（V3.1）
- build_relation_graph操作支持（V3.1）
- extract_chapters_from_content操作支持（V3.2）：从章节文件提取人物出场
"""

import logging
import os
import re
from typing import Any, Dict, List

from ..agent_adapter import AgentAdapter
from ..priority import AgentTask

logger = logging.getLogger(__name__)


class CharacterManagerAdapter(AgentAdapter):
    """
    人物管理器适配器

    直接实现人物解析逻辑，不依赖旧版本模块
    """

    def __init__(self):
        # 不包装旧模块，直接使用
        super().__init__(
            agent_type="character_manager",
            module_path=None,  # 不包装旧模块
            class_name=None,
        )

    def initialize(self) -> bool:
        """初始化适配器"""
        self._initialized = True
        logger.info("[CharacterManagerAdapter] 初始化完成（直接实现模式）")
        return True

    def execute(self, task: AgentTask) -> Dict[str, Any]:
        """
        执行人物管理操作

        Args:
            task: 任务对象

        Returns:
            操作结果
        """
        if not self._initialized:
            raise RuntimeError(f"Agent {self.agent_type} 未初始化")

        payload = task.payload
        operation = payload.get("operation", "get_character")

        try:
            # 根据操作类型调用不同方法
            if operation == "batch_import":
                # 【V3.0】批量解析导入
                character_data = payload.get("character_data", {})
                content = character_data.get("content", "")
                source_file = character_data.get("source_file", "")
                result = self._batch_import(content, source_file)

            elif operation == "edit_character":
                # 【V3.1】编辑人物
                character_name = payload.get("character_name", "")
                character_data = payload.get("character_data", {})
                all_characters = payload.get("all_characters", [])
                result = self._edit_character(character_name, character_data, all_characters)

            elif operation == "get_character_detail":
                # 【V3.1】获取人物详情
                character_name = payload.get("character_name", "")
                all_characters = payload.get("all_characters", [])
                result = self._get_character_detail(character_name, all_characters)

            elif operation == "build_relation_graph":
                # 【V3.2】构建关系图谱（自动增强人物数据）
                all_characters = payload.get("all_characters", [])
                
                # 【新增】如果人物描述不完整，自动从章节文件中提取出场关系
                all_characters = self._enhance_characters_from_chapters(all_characters)
                
                result = self._build_relation_graph(all_characters)

            elif operation == "list_characters":
                result = {"characters": []}

            else:
                raise ValueError(f"未知操作: {operation}")

            # 更新状态
            self._increment_completed()

            return {
                "task_id": task.task_id,
                "result": result,
                "metadata": {"operation": operation},
            }

        except Exception as e:
            self._increment_failed()
            self._set_error(str(e))
            logger.error(f"人物管理操作失败: {e}", exc_info=True)
            raise

    def _batch_import(self, content: str, source_file: str = "") -> Dict[str, Any]:
        """
        批量解析导入人物（V5解析逻辑）

        Args:
            content: 文本内容
            source_file: 源文件路径

        Returns:
            解析结果 {"characters": [...]}
        """
        lines = content.split('\n')
        lines = [line.strip() for line in lines if line.strip()]
        characters = self._parse_characters_text(lines)

        # 【V3.2】自动从章节文件提取人物出场信息
        if source_file and characters:
            try:
                # 获取项目路径（人物文件所在目录的父目录）
                import os
                if os.path.isfile(source_file):
                    project_path = os.path.dirname(os.path.dirname(source_file))
                else:
                    project_path = os.getcwd()

                # 提取章节信息
                extract_result = self._extract_chapters_from_content(characters, project_path)
                if extract_result.get("success"):
                    characters = extract_result.get("characters", characters)
                    logger.info(f"从章节提取人物出场信息: {extract_result.get('message')}")
            except Exception as e:
                logger.warning(f"提取章节信息失败（不影响导入）: {e}")

        return {
            "characters": characters,
            "count": len(characters),
            "source_file": source_file
        }

    def _parse_characters_text(self, text_lines: List[str]) -> List[Dict[str, Any]]:
        """
        从文本行中解析多个人物设定（V5解析逻辑 - 修复版）

        支持：
        - Markdown格式：## 数字. 姓名（人物分隔符）
        - 三级标题：### 基本信息（人物内部章节）
        - 字段：**姓名**：张三
        - 分隔符：---（章节分隔）

        修复：三级标题和分隔符不再被误认为是新人物

        Returns:
            人物列表
        """
        characters = []

        if not text_lines:
            return characters

        current_character = None
        current_section = None
        desc_lines = []

        for line in text_lines:
            # 检测人物分隔符：## 数字. 姓名（但不是###）
            if line.startswith('##') and not line.startswith('###'):
                # 保存上一个人物
                if current_character:
                    if desc_lines:
                        filtered_lines = [dl.strip() for dl in desc_lines
                                       if dl.strip() and not dl.strip().startswith('-') and not dl.strip().startswith('*')]
                        if filtered_lines:
                            desc = '\n'.join(filtered_lines)
                            current_character.setdefault('description', '')
                            current_character['description'] += '\n' + desc if current_character['description'] else desc
                    characters.append(current_character)

                # 提取新人物的姓名
                clean_line = line[2:].strip()
                if '.' in clean_line:
                    name_part = clean_line.split('.', 1)[1].strip()
                else:
                    name_part = clean_line.strip()

                current_character = {
                    'name': name_part,
                    'role': '未设置',  # 默认角色类型
                    'status': '新建',
                    'emotion': '平静',
                    'chapters': '未设置',
                    'appearance': '',
                    'personality': '',
                    'background': '',
                    'goals': '',
                    'fears': '',
                    'mbti': '',
                    'description': ''
                }
                current_section = None
                desc_lines = []

            elif current_character:
                # 【修复】跳过章节分隔符（---）
                if line.strip() == '---':
                    continue

                # 【修复】三级标题只是章节标记，不产生新人物
                if line.startswith('###'):
                    # 保存上一个章节的内容
                    if desc_lines:
                        # 【修复】如果当前章节是"重要关系"或"人际关系"，保留列表项
                        if current_section in ['重要关系', '人际关系', '与其他角色的关系']:
                            # 保留所有内容，包括列表项
                            desc = '\n'.join([dl.strip() for dl in desc_lines if dl.strip()])
                        else:
                            # 其他章节过滤列表项
                            filtered_lines = [dl.strip() for dl in desc_lines
                                           if dl.strip() and not dl.strip().startswith('-') and not dl.strip().startswith('*')]
                            desc = '\n'.join(filtered_lines)
                        
                        if desc and current_section != '基本信息':
                            current_character['description'] += '\n' + desc if current_character['description'] else desc

                    current_section = line[3:].strip()
                    desc_lines = []

                # 检测Markdown字段：**字段名**：值（支持单星号和双星号，支持全角冒号）
                elif (line.startswith('*') or line.startswith('**')) and ('**：' in line or '*：' in line):
                    # 统一处理：将单星号转换为双星号，全角冒号转换为半角冒号
                    normalized_line = line.replace('：', ':')
                    # 处理单星号：将 *key* 替换为 **key**
                    if '*' in normalized_line and '**' not in normalized_line[:2]:
                        # 单星号格式：*字段名*:值
                        match = re.match(r'\*(.+?)\*:(.*)', normalized_line)
                    else:
                        # 双星号格式：**字段名**:值
                        match = re.match(r'\*\*(.+?)\*\*:(.*)', normalized_line)

                    if match:
                        key = match.group(1).strip()
                        value = match.group(2).strip()
                        self._map_field_to_character(current_character, key, value)

                # 其他内容积累到描述
                else:
                    desc_lines.append(line)

        # 保存最后一个人物
        if current_character:
            if desc_lines:
                # 【修复】如果是"重要关系"或"人际关系"章节，保留列表项
                if current_section in ['重要关系', '人际关系', '与其他角色的关系']:
                    desc = '\n'.join([dl.strip() for dl in desc_lines if dl.strip()])
                else:
                    filtered_lines = [dl.strip() for dl in desc_lines
                                   if dl.strip() and not dl.strip().startswith('-') and not dl.strip().startswith('*')]
                    if filtered_lines:
                        desc = '\n'.join(filtered_lines)
                    else:
                        desc = ''
                
                if desc and current_section != '基本信息':
                    current_character['description'] += '\n' + desc if current_character['description'] else desc
            characters.append(current_character)

        return characters

    def _map_field_to_character(self, character: Dict[str, Any], key: str, value: str):
        """
        将字段映射到人物属性（V5映射逻辑）

        Args:
            character: 人物字典
            key: 字段名
            value: 字段值
        """
        mapping = {
            '姓名': 'name',
            '性别': 'gender',
            '年龄': 'age',
            '角色': 'role',
            '角色类型': 'role',
            '角色定位': 'role',
            '身份': 'role',
            '外貌': 'appearance',
            '性格': 'personality',
            '背景': 'background',
            '出身背景': 'background',
            '目标': 'goals',
            '核心动机': 'goals',
            '恐惧': 'fears',
            'MBTI': 'mbti',
            'MBTI类型': 'mbti',
            '情绪': 'emotion',
            '状态': 'status',
            '核心动机': 'goals',
            '恐惧': 'fears',
            'MBTI': 'mbti',
            '情绪': 'emotion',
            '状态': 'status',
            '出场章节': 'chapters',
            # 【新增】重要关系字段映射
            '重要关系': 'important_relations',
            '与其他角色的关系': 'other_relations',
            '人际关系': 'relations'
        }

        field_name = mapping.get(key)
        if field_name and value:
            character[field_name] = value

    def _edit_character(self, character_name: str, character_data: Dict[str, Any], all_characters: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        编辑人物信息

        Args:
            character_name: 要编辑的人物名称
            character_data: 新的人物数据（要更新的字段）
            all_characters: 所有人物列表

        Returns:
            编辑结果 {"success": bool, "message": str, "characters": [...]}
        """
        try:
            # 查找要编辑的人物
            found_index = -1
            for i, char in enumerate(all_characters):
                if char.get('name') == character_name:
                    found_index = i
                    break

            if found_index == -1:
                return {
                    "success": False,
                    "message": f"未找到人物: {character_name}",
                    "characters": all_characters
                }

            # 更新人物字段（只更新提供的字段）
            for key, value in character_data.items():
                if value is not None and value != "":
                    all_characters[found_index][key] = value

            logger.info(f"成功编辑人物: {character_name}")
            return {
                "success": True,
                "message": f"人物 {character_name} 更新成功",
                "characters": all_characters
            }

        except Exception as e:
            logger.error(f"编辑人物失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"编辑失败: {str(e)}",
                "characters": all_characters
            }

    def _get_character_detail(self, character_name: str, all_characters: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        获取人物详情

        Args:
            character_name: 人物名称
            all_characters: 所有人物列表

        Returns:
            人物详情 {"character": {...}, "found": bool}
        """
        try:
            # 查找人物
            character = None
            for char in all_characters:
                if char.get('name') == character_name:
                    character = char
                    break

            if character is None:
                return {
                    "character": {},
                    "found": False,
                    "message": f"未找到人物: {character_name}"
                }

            return {
                "character": character,
                "found": True,
                "message": f"找到人物: {character_name}"
            }

        except Exception as e:
            logger.error(f"获取人物详情失败: {e}", exc_info=True)
            return {
                "character": {},
                "found": False,
                "message": f"获取失败: {str(e)}"
            }

    def _enhance_characters_from_chapters(self, all_characters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        【V3.2】从原始人物文件中重新解析，提取完整关系信息
        
        核心问题：GUI中使用的是手动添加的人物数据（缺少关系信息），
        而原始人物设定文件中包含"重要关系"章节。
        
        解决方案：自动读取原始人物文件，重新解析获取完整关系信息
        
        Args:
            all_characters: 原始人物列表
        
        Returns:
            增强后的人物列表（包含完整的关系信息）
        """
        from pathlib import Path
        
        # 提取人物名字
        character_names = [char.get('name', '') for char in all_characters if char.get('name')]
        if not character_names:
            return all_characters
        
        # 查找原始人物文件（支持多个路径）
        character_file = None
        current_dir = Path.cwd()
        
        search_paths = [
            # 方式1：小说作品/项目名/人物/人设.txt
            current_dir / "小说作品" / "逆袭小妹" / "人物" / "人设.txt",
            # 方式2：works/项目名/characters/characters.txt
            current_dir / "works" / "逆袭小妹" / "characters" / "characters.txt",
            # 方式3：根目录/人物/人设.txt
            current_dir / "人物" / "人设.txt"
        ]
        
        for path in search_paths:
            if path.exists() and path.is_file():
                character_file = path
                logger.info(f"[CharacterManagerAdapter] 找到人物文件: {character_file}")
                break
        
        if not character_file:
            logger.warning("[CharacterManagerAdapter] 未找到人物文件，无法提取关系信息")
            return all_characters
        
        # 重新解析人物文件
        try:
            content = character_file.read_text(encoding='utf-8')
            parsed_characters = self._parse_characters_text(content.split('\n'))
            logger.info(f"[CharacterManagerAdapter] 从文件重新解析了{len(parsed_characters)}个人物")
            
            # 【V3.2修复】直接返回所有解析出来的人物，不进行匹配过滤
            # 原因：mock_characters可能只是部分人物（如GUI中只加载了3个），
            #       但原始文件可能包含15个人物，关系图谱需要完整的人物数据
            logger.info(f"[CharacterManagerAdapter] 使用解析后的完整人物数据（{len(parsed_characters)}个人物）")
            return parsed_characters

        except Exception as e:
            logger.error(f"[CharacterManagerAdapter] 读取人物文件失败: {e}", exc_info=True)
            return all_characters

    def _build_relation_graph(self, all_characters: List[Dict[str, Any]], character_descriptions: Dict[str, str] = None) -> Dict[str, Any]:
        """
        构建人物关系图谱（使用NetworkX友好的数据结构）

        Args:
            all_characters: 所有人物列表
            character_descriptions: 人物描述字典（人物名 -> 描述文本），如果为None则自动从人物数据提取

        Returns:
            关系图谱数据 {"nodes": [...], "relations": [...]}
        """
        try:
            # 如果未提供描述字典，从人物数据中自动提取
            if character_descriptions is None:
                character_descriptions = {
                    char.get('name', ''): char.get('description', '')
                    for char in all_characters if char.get('name')
                }
                logger.info(f"[CharacterManagerAdapter] 自动从{len(character_descriptions)}个人物提取描述")

            # 节点：所有人物
            nodes = []
            for char in all_characters:
                name = char.get('name', '未命名')
                role = char.get('role', '未设置')
                status = char.get('status', '新建')
                nodes.append({
                    "id": name,
                    "label": name,
                    "role": role,
                    "status": status,
                    "type": "character"
                })

            # 关系列表
            relations = []

            # 关系关键词映射（更全面）
            relation_keywords = {
                # 家庭关系
                '父亲': 'father', '爸': 'father', '爸爸': 'father',
                '母亲': 'mother', '妈': 'mother', '妈妈': 'mother',
                '儿子': 'son', '女儿': 'daughter',
                '兄弟': 'brother', '兄': 'brother', '弟': 'brother',
                '姐妹': 'sister', '姐': 'sister', '妹': 'sister',
                '祖父': 'grandfather', '祖母': 'grandmother',
                '外祖父': 'grandfather', '外祖母': 'grandmother',
                # 情感关系
                '恋人': 'lover', '爱人': 'lover', '伴侣': 'lover', '情侣': 'lover',
                '前任': 'ex_lover', '暗恋': 'crush',
                '丈夫': 'husband', '妻子': 'wife', '老婆': 'wife', '老公': 'husband',
                # 友情关系
                '朋友': 'friend', '好友': 'friend', '闺蜜': 'friend', '兄弟': 'friend',
                '挚友': 'friend', '死党': 'friend',
                # 敌对关系
                '敌人': 'enemy', '仇人': 'enemy', '对手': 'enemy', '敌对': 'enemy',
                '死敌': 'enemy', '宿敌': 'enemy',
                # 职业关系
                '上司': 'boss', '老板': 'boss', '领导': 'boss',
                '下属': 'subordinate', '部下': 'subordinate',
                '同事': 'colleague', '同僚': 'colleague',
                '师': 'teacher', '老师': 'teacher', '师父': 'teacher',
                '生': 'student', '学生': 'student', '徒弟': 'student',
                # 其他关系
                '盟友': 'ally', '合作者': 'ally', '伙伴': 'ally',
                '邻居': 'neighbor',
                '同学': 'classmate',
                '同乡': 'fellow_townsman',
            }

            character_names = [char.get('name') for char in all_characters if char.get('name')]

            # 统一全角冒号为半角冒号，提高匹配率
            def normalize_text(text: str) -> str:
                return text.replace('：', ':').replace('：', ':').replace(':', ':')

            # 分析每个人物的描述，提取关系
            for char in all_characters:
                char_name = char.get('name', '')
                if not char_name:
                    continue

                # 获取描述文本（优先使用"人际关系/重要关系"字段，否则合并其他字段）
                description_parts = []
                
                # 【优先】使用"人际关系"或"重要关系"字段（这是作者明确标注的关系）
                relations_field = char.get('relations', '') or char.get('important_relations', '') or char.get('other_relations', '')
                if relations_field:
                    description_parts.append(relations_field)
                
                # 【降级】如果没有明确关系字段，合并其他所有字段
                description_parts.extend([
                    character_descriptions.get(char_name, ''),
                    char.get('description', ''),
                    char.get('personality', ''),
                    char.get('background', ''),
                    char.get('role', ''),
                    char.get('goals', ''),
                    char.get('fears', ''),
                    char.get('mbti', ''),
                    char.get('ability', '')
                ])
                
                full_description = '\n'.join([p for p in description_parts if p])
                
                # 标准化文本（统一冒号）
                normalized_description = normalize_text(full_description)

                # 【V3.2】优先解析列表格式的关系："- 人物名：关系描述"
                list_relations = self._parse_list_format_relations(normalized_description, character_names)
                
                # 【新增】使用列表格式的关系（如果有）
                extracted_relations = list_relations
                
                # 【降级】如果没有列表格式关系，则使用传统的名字匹配方法
                if not extracted_relations:
                    for other_name in character_names:
                        if other_name == char_name:
                            continue

                        # 检查名字是否在描述中（使用标准化文本）
                        if other_name not in normalized_description:
                            continue

                        # 提取包含其他名字的句子上下文
                        context = self._extract_relation_context(normalized_description, other_name)
                        
                        # 添加到提取的关系列表
                        extracted_relations.append({
                            'target': other_name,
                            'context': context
                        })
                
                # 处理提取到的关系
                for rel_data in extracted_relations:
                    other_name = rel_data['target']
                    context = rel_data.get('context', '')

                    # 检查关系关键词
                    relation_type = 'related'  # 默认关系
                    for keyword, rel_type in relation_keywords.items():
                        if keyword in context:
                            relation_type = rel_type
                            break

            # 避免重复添加关系（A->B 和 B->A 视为同一关系）
                    relation_exists = any(
                        (r['source'] == char_name and r['target'] == other_name) or
                        (r['source'] == other_name and r['target'] == char_name)
                        for r in relations
                    )

                    if not relation_exists:
                        relations.append({
                            "source": char_name,
                            "target": other_name,
                            "relation": relation_type,
                            "label": self._get_relation_label(relation_type),
                            "context": context
                        })
                        logger.info(f"[CharacterManagerAdapter] 提取关系: {char_name} -> {other_name} ({relation_type})")

            logger.info(f"构建关系图谱: {len(nodes)}个节点, {len(relations)}条边")
            return {
                "nodes": nodes,
                "relations": relations,
                "node_count": len(nodes),
                "edge_count": len(relations)
            }

        except Exception as e:
            logger.error(f"构建关系图谱失败: {e}", exc_info=True)
            return {
                "nodes": [],
                "relations": [],
                "node_count": 0,
                "edge_count": 0,
                "error": str(e)
            }

    def _get_relation_label(self, relation_type: str) -> str:
        """获取关系类型的中文名称"""
        labels = {
            'friend': '朋友',
            'lover': '恋人',
            'enemy': '敌人',
            'rival': '对手',
            'brother': '兄弟',
            'sister': '姐妹',
            'parent': '父母',
            'father_son': '父子',
            'father_daughter': '父女',
            'mother_son': '母子',
            'mother_daughter': '母女',
            'teacher_student': '师生',
            'master_servant': '主仆',
            'ally': '盟友',
            'related': '相关',
            # 新增关系类型
            'father': '父亲',
            'mother': '母亲',
            'son': '儿子',
            'daughter': '女儿',
            'grandfather': '祖父/外祖父',
            'grandmother': '祖母/外祖母',
            'ex_lover': '前任',
            'crush': '暗恋',
            'husband': '丈夫',
            'wife': '妻子',
            'boss': '上司',
            'subordinate': '下属',
            'colleague': '同事',
            'neighbor': '邻居',
            'classmate': '同学',
            'fellow_townsman': '同乡'
        }
        return labels.get(relation_type, '相关')

    def _parse_list_format_relations(self, description: str, character_names: List[str]) -> List[Dict[str, Any]]:
        """
        【V3.2】解析列表格式的关系描述
        
        格式示例：
        - 牛奶奶：最亲的亲人，愿意为她做任何事
        - 王翠花：热心邻居，经常给她送吃的
        
        Args:
            description: 描述文本
            character_names: 所有人物名字列表
        
        Returns:
            提取到的关系列表 [{'target': '人物名', 'context': '关系描述'}]
        """
        import re
        relations = []
        
        # 按行分割
        lines = description.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # 匹配列表格式："- 人物名：关系描述"
            # 支持多种分隔符：冒号（全角/半角）、破折号等
            match = re.match(r'^-\s*([^:：\d]+?)[:：]\s*(.+)', line)
            if match:
                target_name = match.group(1).strip()
                relation_desc = match.group(2).strip()
                
                # 检查是否是已知人物
                # 注意：target_name可能包含别名或括号说明，如"牛张氏（户口本上叫张秀兰）"
                # 需要模糊匹配
                matched_name = None
                for char_name in character_names:
                    if char_name in target_name or target_name in char_name:
                        matched_name = char_name
                        break
                
                if matched_name:
                    relations.append({
                        'target': matched_name,
                        'context': relation_desc
                    })
                    logger.debug(f"[CharacterManagerAdapter] 解析列表关系: {matched_name} -> {relation_desc[:50]}...")
        
        return relations

    def _extract_relation_context(self, description: str, other_name: str) -> str:
        """提取关系上下文（包含另一人物名的句子）"""
        sentences = description.split('。')
        for sentence in sentences:
            if other_name in sentence:
                # 返回包含关系上下文的句子（最多100字符）
                context = sentence.strip()
                if len(context) > 100:
                    context = context[:100] + '...'
                return context

    def _extract_chapters_from_content(self, all_characters: List[Dict[str, Any]], project_path: str) -> Dict[str, Any]:
        """
        从章节文件中提取人物出场信息

        Args:
            all_characters: 所有人物列表
            project_path: 项目路径

        Returns:
            提取结果 {"success": bool, "message": str, "characters": [...]}
        """
        try:
            # 获取章节目录
            chapters_dir = os.path.join(project_path, "章节")
            if not os.path.exists(chapters_dir):
                return {
                    "success": True,
                    "message": "章节目录不存在，使用默认值",
                    "characters": all_characters
                }

            # 获取所有章节文件
            chapter_files = []
            for file in os.listdir(chapters_dir):
                if file.endswith('.txt') and file != 'README.txt':
                    chapter_files.append(file)

            if not chapter_files:
                return {
                    "success": True,
                    "message": "章节目录为空",
                    "characters": all_characters
                }

            # 构建人物名集合
            character_names = set(char.get('name', '') for char in all_characters if char.get('name'))

            # 分析每个章节文件
            character_chapters = {name: [] for name in character_names}

            for chapter_file in sorted(chapter_files):
                chapter_path = os.path.join(chapters_dir, chapter_file)
                chapter_name = chapter_file.replace('.txt', '')

                try:
                    with open(chapter_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # 检查每个人物是否在该章节中出现
                    for char_name in character_names:
                        if char_name in content:
                            character_chapters[char_name].append(chapter_name)

                except Exception as e:
                    logger.warning(f"读取章节文件 {chapter_file} 失败: {e}")
                    continue

            # 更新人物的出场章节字段
            for char in all_characters:
                char_name = char.get('name', '')
                if char_name in character_chapters:
                    chapters_list = character_chapters[char_name]
                    if chapters_list:
                        # 将章节列表转换为逗号分隔的字符串
                        char['chapters'] = ', '.join(chapters_list)
                    else:
                        char['chapters'] = '未设置'

            logger.info(f"成功提取 {len(all_characters)} 个人物的出场章节信息")
            return {
                "success": True,
                "message": f"成功从 {len(chapter_files)} 个章节文件中提取人物出场信息",
                "characters": all_characters,
                "chapter_count": len(chapter_files)
            }

        except Exception as e:
            logger.error(f"提取人物出场章节失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"提取失败: {str(e)}",
                "characters": all_characters
            }
        return ""

