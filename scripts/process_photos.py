#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
照片处理脚本
功能：
1. 从图片EXIF数据读取日期，自动重命名图片为 日期_{id} 格式
2. 自动创建 _photos collection 文件，包含日期、地点、tag等信息
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import json
import yaml

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
PHOTOS_DIR = PROJECT_ROOT / "assets" / "images" / "photos"
COLLECTION_DIR = PROJECT_ROOT / "_photos"
TEMP_DIR = PROJECT_ROOT / "assets" / "images" / "photos" / "_temp"  # 临时存放新图片的目录
PHOTOS_DATA_FILE = PROJECT_ROOT / "_data" / "photos.yml"  # 照片信息记录文件


def get_exif_data(image_path):
    """读取图片的EXIF数据"""
    try:
        image = Image.open(image_path)
        exif_data = image._getexif()
        
        if exif_data is None:
            return None
        
        exif = {}
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            exif[tag] = value
        
        return exif
    except Exception as e:
        print(f"读取EXIF数据失败 {image_path}: {e}")
        return None


def get_date_from_exif(exif_data):
    """从EXIF数据中提取拍摄日期"""
    if not exif_data:
        return None
    
    # 尝试多个可能的日期字段
    date_fields = ['DateTimeOriginal', 'DateTimeDigitized', 'DateTime']
    
    for field in date_fields:
        if field in exif_data:
            try:
                date_str = exif_data[field]
                # EXIF日期格式通常是 "YYYY:MM:DD HH:MM:SS"
                if isinstance(date_str, str):
                    date_obj = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                    return date_obj
            except Exception as e:
                print(f"解析日期失败 {field}: {e}")
                continue
    
    return None


def format_date_for_filename(date_obj):
    """将日期格式化为文件名格式：YYMMDD"""
    return date_obj.strftime("%y%m%d")


def format_date_for_frontmatter(date_obj):
    """将日期格式化为Jekyll front matter格式：YYYY-MM-DD"""
    return date_obj.strftime("%Y-%m-%d")


def generate_photo_id(date_str, existing_files):
    """生成照片ID（同一日期的照片编号）"""
    # 查找同一天的照片数量
    same_date_files = [f for f in existing_files if f.startswith(date_str)]
    
    if not same_date_files:
        return 1
    
    # 提取已有的ID
    ids = []
    for f in same_date_files:
        try:
            # 格式：日期_ID.jpg
            parts = f.replace('.jpg', '').replace('.JPG', '').split('_')
            if len(parts) == 2:
                ids.append(int(parts[1]))
        except:
            continue
    
    if ids:
        return max(ids) + 1
    else:
        return 1


def rename_image(image_path, date_obj=None, target_dir=PHOTOS_DIR):
    
    date_str = format_date_for_filename(date_obj)
    
    # 获取目标目录中已有的文件
    existing_files = [f.name for f in target_dir.glob("*.jpg")] + \
                     [f.name for f in target_dir.glob("*.JPG")]
    
    # 生成新的ID
    photo_id = generate_photo_id(date_str, existing_files)
    
    # 生成新文件名
    new_filename = f"{date_str}_{photo_id}.jpg"
    new_path = target_dir / new_filename
    
    # 如果文件已存在，增加ID
    counter = photo_id
    while new_path.exists():
        counter += 1
        new_filename = f"{date_str}_{counter}.jpg"
        new_path = target_dir / new_filename
    
    # 如果文件不在目标目录，需要先移动/复制
    if image_path.parent != target_dir:
        try:
            import shutil
            # 如果目标目录不存在，创建它
            target_dir.mkdir(parents=True, exist_ok=True)
            # 复制文件到目标目录
            shutil.copy2(image_path, new_path)
            print(f"✓ 复制并重命名: {image_path.name} -> {new_filename}")
            return new_path, date_obj
        except Exception as e:
            print(f"✗ 复制文件失败 {image_path}: {e}")
            return image_path, date_obj
    else:
        # 文件已在目标目录，只需重命名
        try:
            if image_path.name != new_filename:
                image_path.rename(new_path)
                print(f"✓ 重命名: {image_path.name} -> {new_filename}")
            return new_path, date_obj
        except Exception as e:
            print(f"✗ 重命名失败 {image_path}: {e}")
            return image_path, date_obj


def create_collection_file(image_path, date_obj, location=None, tags=None):
    """创建Jekyll collection文件"""
    # 生成文件名（基于图片文件名，去掉扩展名）
    base_name = image_path.stem
    collection_file = COLLECTION_DIR / f"{base_name}.md"
        
    # 准备front matter数据
    date_str = format_date_for_frontmatter(date_obj)
    image_path_str = f"/assets/images/photos/{image_path.name}"
    
    # 构建YAML front matter
    # 使用 header.teaser 格式以便在collection layout中正确显示
    front_matter = {
        'title': f"{base_name}",
        'date': date_str,
        'header': {
            'teaser': image_path_str,
            'image': image_path_str
        },
    }
    
    if location:
        front_matter['location'] = location
    
    if tags:
        front_matter['tags'] = tags if isinstance(tags, list) else [tags]
    
    # 写入文件
    try:
        with open(collection_file, 'w', encoding='utf-8') as f:
            f.write("---\n")
            for key, value in front_matter.items():
                if isinstance(value, dict):
                    # 处理嵌套字典（如header）
                    f.write(f"{key}:\n")
                    for sub_key, sub_value in value.items():
                        f.write(f"  {sub_key}: {sub_value}\n")
                elif isinstance(value, list):
                    f.write(f"{key}:\n")
                    for item in value:
                        f.write(f"  - {item}\n")
                else:
                    f.write(f"{key}: {value}\n")
            f.write("---\n\n")
            f.write(f"拍摄于 {date_str}")
            if location:
                f.write(f"，地点：{location}")
            f.write("。\n")
        
        print(f"✓ 创建collection文件: {collection_file.name}")
       
        return collection_file
    except Exception as e:
        print(f"✗ 创建collection文件失败: {e}")
        return None

def process_single_image(image_path, tags=None, location=None):
    """处理单张图片"""
    print(f"\n处理图片: {image_path.name}")
    
    # 读取EXIF数据
    exif_data = get_exif_data(image_path)
    
    # 获取日期
    date_obj = get_date_from_exif(exif_data)
    
    print("日期：",date_obj)
    # 重命名图片（传入已获取的日期，避免重复读取EXIF）
    new_path, _ = rename_image(image_path, date_obj)
    
    # 创建collection文件
    create_collection_file(new_path, date_obj, location, tags)
    
    return new_path


def process_directory(source_dir=None, tags=None):
    """批量处理目录中的图片"""
    if source_dir is None:
        source_dir = TEMP_DIR
    else:
        source_dir = Path(source_dir)
    
    if not source_dir.exists():
        print(f"目录不存在: {source_dir}")
        return
    
    # 支持的图片格式
    image_extensions = ['.jpg', '.jpeg', '.JPG', '.JPEG', '.png', '.PNG']
    
    # 查找所有图片文件
    image_files = []
    for ext in image_extensions:
        image_files.extend(source_dir.glob(f"*{ext}"))
    
    if not image_files:
        print(f"在 {source_dir} 中未找到图片文件")
        return
    
    print(f"找到 {len(image_files)} 张图片")
    
    # 处理每张图片
    for image_path in sorted(image_files):
        process_single_image(image_path, tags)
    
    print(f"\n✓ 处理完成！共处理 {len(image_files)} 张图片")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='处理照片：重命名并创建collection文件')
    parser.add_argument('--source', '-s', type=str, 
                       help='源图片目录（默认为 assets/images/photos/_temp）')
    parser.add_argument('--tags', '-t', type=str, nargs='+',
                       help='照片标签（例如：--tags 风景 旅行）')
    parser.add_argument('--location', '-l', type=str)
    parser.add_argument('--file', '-f', type=str,
                       help='处理单张图片文件')
    
    args = parser.parse_args()
    
    # 确保目录存在
    COLLECTION_DIR.mkdir(exist_ok=True)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    
    if args.file:
        # 处理单张图片
        image_path = Path(args.file)
        if not image_path.exists():
            print(f"文件不存在: {image_path}")
            sys.exit(1)
        process_single_image(image_path, args.tags, args.location)
    else:
        # 批量处理
        process_directory(args.source, args.tags)


if __name__ == "__main__":
    main()

