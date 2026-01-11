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
THUMB_DIR = PHOTOS_DIR / "thumbs"
COLLECTION_DIR = PROJECT_ROOT / "_photos"
TEMP_DIR = PROJECT_ROOT / "assets" / "images" / "photos" / "_temp"  # 临时存放新图片的目录
PHOTOS_DATA_FILE = PROJECT_ROOT / "_data" / "photos.yml"  # 照片信息记录文件

THUMB_MAX_WIDTH = 720
THUMB_QUALITY = 82


def path_to_site_url(file_path: Path) -> str:
    """将项目内的文件转换为站点可引用的URL"""
    try:
        rel_path = file_path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"图片必须位于项目目录内: {file_path}") from exc
    return "/" + rel_path.as_posix()


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



def create_thumbnail(image_path, max_width=THUMB_MAX_WIDTH, quality=THUMB_QUALITY):
    """为列表页生成小尺寸缩略图"""
    if not image_path.exists():
        return None

    THUMB_DIR.mkdir(parents=True, exist_ok=True)

    try:
        rel_path = image_path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        print(f"✗ 图片必须位于项目目录内: {image_path}")
        return None

    safe_name = "_".join(rel_path.with_suffix('').parts) + "_thumb.jpg"
    thumbnail_path = THUMB_DIR / safe_name

    # 如果缩略图是最新的，跳过生成
    if thumbnail_path.exists():
        if thumbnail_path.stat().st_mtime >= image_path.stat().st_mtime:
            return thumbnail_path

    try:
        with Image.open(image_path) as img:
            width, height = img.size
            # 只在需要时缩放
            if width > max_width:
                ratio = max_width / float(width)
                new_height = max(int(height * ratio), 1)
                img = img.resize((max_width, new_height), Image.LANCZOS)

            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            img.save(thumbnail_path, format="JPEG", quality=quality, optimize=True, progressive=True)

        print(f"✓ 生成缩略图: {thumbnail_path.name}")
        return thumbnail_path
    except Exception as exc:
        print(f"✗ 生成缩略图失败 {image_path}: {exc}")
        return None


def create_collection_file(image_path, date_obj, location=None, tags=None, teaser_url=None):
    """创建Jekyll collection文件"""
    # 生成文件名（基于图片文件名，去掉扩展名）
    base_name = image_path.stem
    collection_file = COLLECTION_DIR / f"{base_name}.md"
        
    # 准备front matter数据
    date_str = format_date_for_frontmatter(date_obj)
    try:
        image_path_str = path_to_site_url(image_path)
    except ValueError as exc:
        print(f"✗ {exc}")
        return None
    teaser_path_str = teaser_url or image_path_str
    
    # 构建YAML front matter
    # 使用 header.teaser 格式以便在collection layout中正确显示
    front_matter = {
        'title': f"{base_name}",
        'date': date_str,
        'header': {
            'teaser': teaser_path_str,
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
    image_path = Path(image_path).resolve()
    print(f"\n处理图片: {image_path}")

    if not image_path.exists():
        print(f"✗ 文件不存在: {image_path}")
        return image_path
    try:
        path_to_site_url(image_path)
    except ValueError as exc:
        print(f"✗ {exc}")
        return image_path
    
    # 读取EXIF数据
    exif_data = get_exif_data(image_path)
    
    # 获取日期
    date_obj = get_date_from_exif(exif_data)
    
    print("日期：",date_obj)
    
    # 创建collection文件
    thumbnail_path = create_thumbnail(image_path)
    teaser_url = None
    if thumbnail_path:
        teaser_url = path_to_site_url(thumbnail_path)

    create_collection_file(image_path, date_obj, location, tags, teaser_url)
    
    return image_path


def process_directory(source_dir=None, tags=None, location=None):
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
        process_single_image(image_path, tags, location)
    
    print(f"\n✓ 处理完成！共处理 {len(image_files)} 张图片")


def refresh_thumbnails():
    """为现有图片重新生成缩略图"""
    if not PHOTOS_DIR.exists():
        print(f"目录不存在: {PHOTOS_DIR}")
        return

    originals = []
    for pattern in ("*.jpg", "*.jpeg", "*.JPG", "*.JPEG", "*.png", "*.PNG"):
        originals.extend([p for p in PHOTOS_DIR.glob(pattern) if p.parent == PHOTOS_DIR])

    if not originals:
        print("没有找到需要生成缩略图的原始照片。")
        return

    print(f"找到 {len(originals)} 张原始照片，正在生成缩略图...")
    for photo in originals:
        create_thumbnail(photo)

    print("✓ 缩略图更新完成！")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='处理照片：重命名并创建collection文件')
    parser.add_argument('--source', '-s', type=str, 
                       help='源图片目录（默认为 assets/images/photos/_temp）')
    parser.add_argument('--tags', '-t', type=str, nargs='+',
                       help='照片标签（例如：--tags 风景 旅行）')
    parser.add_argument('--location', '-l', type=str,
                       help='拍摄地点，会写入collection front matter')
    parser.add_argument('--file', '-f', type=str,
                       help='处理单张图片文件')
    parser.add_argument('--refresh-thumbs', action='store_true',
                       help='仅为现有照片生成/刷新缩略图')
    
    args = parser.parse_args()
    
    # 确保目录存在
    COLLECTION_DIR.mkdir(exist_ok=True)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    
    if args.refresh_thumbs:
        refresh_thumbnails()
        sys.exit(0)

    if args.file:
        # 处理单张图片
        image_path = Path(args.file)
        if not image_path.exists():
            print(f"文件不存在: {image_path}")
            sys.exit(1)
        process_single_image(image_path, args.tags, args.location)
    else:
        # 批量处理
        process_directory(args.source, args.tags, args.location)


if __name__ == "__main__":
    main()

