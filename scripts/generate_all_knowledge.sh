#!/bin/bash
# 知识库自动生成脚本
# 预计耗时: 约2小时

echo "========================================"
echo "    知识库自动生成脚本"
echo "========================================"
echo ""

# 进入项目根目录
cd "$(dirname "$0")/.."

echo "[1/4] 开始生成科幻知识库（559条）..."
python tools/knowledge_generator_batch.py --category scifi --count 559
if [ $? -ne 0 ]; then
    echo "❌ 科幻知识库生成失败"
    exit 1
fi
echo "✅ 科幻知识库生成完成"
echo ""

echo "[2/4] 开始生成玄幻知识库（334条）..."
python tools/knowledge_generator_batch.py --category xuanhuan --count 334
if [ $? -ne 0 ]; then
    echo "❌ 玄幻知识库生成失败"
    exit 1
fi
echo "✅ 玄幻知识库生成完成"
echo ""

echo "[3/4] 开始生成通用知识库（237条）..."
python tools/knowledge_generator_batch.py --category general --count 237
if [ $? -ne 0 ]; then
    echo "❌ 通用知识库生成失败"
    exit 1
fi
echo "✅ 通用知识库生成完成"
echo ""

echo "[4/4] 生成统计信息..."
python tools/knowledge_generator_batch.py --stats
echo ""

echo "========================================"
echo "    知识库生成完成！"
echo "========================================"
echo ""
echo "请查看 data/knowledge/ 目录下的JSON文件"
echo ""
