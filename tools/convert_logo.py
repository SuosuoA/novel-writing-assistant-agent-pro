"""将logo.jpg转换为icon.ico文件"""
from PIL import Image
import os

# logo文件路径
logo_path = r"E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\logo\logo.jpg"
icon_path = r"E:\WorkBuddyworkspace\Novel Writing Assistant-Agent Pro\icon.ico"

# 打开logo图片
if os.path.exists(logo_path):
    try:
        # 打开并调整大小为256x256
        img = Image.open(logo_path)
        
        # 如果图片不是正方形，裁剪为正方形
        width, height = img.size
        min_size = min(width, height)
        left = (width - min_size) // 2
        top = (height - min_size) // 2
        right = left + min_size
        bottom = top + min_size
        img = img.crop((left, top, right, bottom))
        
        # 调整大小为256x256（推荐尺寸）
        img = img.resize((256, 256), Image.Resampling.LANCZOS)
        
        # 转换为RGBA模式（支持透明度）
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # 保存为.ico文件（多尺寸：256, 128, 64, 48, 32, 16）
        img.save(icon_path, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
        
        print(f"[SUCCESS] Icon generated: {icon_path}")
        print(f"[INFO] Source: {logo_path}")
        print(f"[INFO] Size: 256x256 (multi-size version)")
        
    except Exception as e:
        print(f"[ERROR] Conversion failed: {e}")
else:
    print(f"[ERROR] Logo file not found: {logo_path}")
