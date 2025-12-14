#!/usr/bin/env python3
"""
TomatOS 拆分文件自动合并脚本 (独立版)
无需依赖其他模块，支持 7-Zip 和 Python 两种合并方式
"""

import os
import sys
import json
import hashlib
import subprocess
import platform
import shutil
from pathlib import Path

# 尝试导入 logger，如果失败则使用 print
try:
    from logger import logger
    def log_info(msg): logger.info(msg)
    def log_warning(msg): logger.warning(msg)
    def log_error(msg): logger.error(msg)
except ImportError:
    def log_info(msg): print(f"[INFO] {msg}")
    def log_warning(msg): print(f"[WARN] {msg}")
    def log_error(msg): print(f"[ERROR] {msg}")

class StandaloneMerger:
    def __init__(self):
        self.system = platform.system().lower()
        self.sevenzip_path = self._find_sevenzip()

    def _find_sevenzip(self):
        """查找系统中已安装的 7-Zip"""
        if self.system == "windows":
            possible_paths = [
                Path("C:\\Program Files\\7-Zip\\7z.exe"),
                Path("C:\\Program Files (x86)\\7-Zip\\7z.exe"),
                Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "7-Zip" / "7z.exe",
                Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "7-Zip" / "7z.exe",
            ]
            for path_dir in os.environ.get("PATH", "").split(os.pathsep):
                possible_paths.append(Path(path_dir) / "7z.exe")
            
            for path in possible_paths:
                if path.exists():
                    return path
        elif self.system in ["linux", "darwin"]:
            try:
                result = subprocess.run(["which", "7z"], capture_output=True, text=True)
                if result.returncode == 0:
                    return Path(result.stdout.strip())
            except:
                pass
        return None

    def _calculate_file_hash(self, file_path):
        """计算文件的 SHA256 哈希值"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def merge_file(self, info_file_path):
        """合并文件"""
        try:
            with open(info_file_path, "r", encoding="utf-8") as f:
                split_info = json.load(f)
            
            base_dir = info_file_path.parent
            original_file = base_dir / split_info["original_file"]
            
            # 检查目标文件是否已存在
            if original_file.exists():
                log_info(f"文件已存在，跳过合并: {original_file.name}")
                return True

            method = split_info.get("method", "python")
            log_info(f"开始合并: {split_info['original_file']} (方法: {method})")

            success = False
            if method == "7zip" and self.sevenzip_path:
                success = self._merge_with_7zip(split_info, base_dir, original_file)
            
            # 如果 7-Zip 失败或方法是 python，尝试 Python 合并
            if not success:
                if method == "7zip":
                    log_info("7-Zip 合并不可用或失败，尝试使用 Python 合并...")
                success = self._merge_with_python(split_info, base_dir, original_file)

            if success:
                # 验证哈希
                if "original_hash" in split_info:
                    log_info("正在验证文件完整性...")
                    current_hash = self._calculate_file_hash(original_file)
                    if current_hash == split_info["original_hash"]:
                        log_info("✓ 哈希验证通过")
                        return True
                    else:
                        log_error("✗ 哈希验证失败！文件可能已损坏")
                        original_file.unlink(missing_ok=True)
                        return False
                return True
            
            return False

        except Exception as e:
            log_error(f"合并过程出错: {e}")
            return False

    def _merge_with_7zip(self, split_info, base_dir, output_path):
        """使用 7-Zip 合并"""
        try:
            volumes = split_info.get("volumes", [])
            if not volumes:
                return False
            
            first_volume = base_dir / volumes[0]["volume_file"]
            if not first_volume.exists():
                return False

            # 7z x first_volume -oOutput
            # 注意：7z 会自动处理分卷，只需要指定第一个
            # 我们解压到临时目录，然后移动
            temp_dir = base_dir / f"{split_info['original_file']}.temp"
            temp_dir.mkdir(exist_ok=True)
            
            cmd = [str(self.sevenzip_path), "x", str(first_volume), f"-o{temp_dir}", "-y"]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                log_warning(f"7-Zip 解压失败: {result.stderr}")
                shutil.rmtree(temp_dir, ignore_errors=True)
                return False
            
            # 移动文件
            extracted_files = list(temp_dir.glob("*"))
            if len(extracted_files) == 1:
                extracted_files[0].rename(output_path)
                shutil.rmtree(temp_dir, ignore_errors=True)
                return True
            
            shutil.rmtree(temp_dir, ignore_errors=True)
            return False
        except Exception as e:
            log_warning(f"7-Zip 合并异常: {e}")
            return False

    def _merge_with_python(self, split_info, base_dir, output_path):
        """使用 Python 合并"""
        try:
            # 获取所有分块/分卷
            chunks = []
            if "chunks" in split_info:
                chunks = split_info["chunks"]
                # 排序
                chunks.sort(key=lambda x: x["chunk_num"])
                file_key = "chunk_file"
            elif "volumes" in split_info:
                chunks = split_info["volumes"]
                chunks.sort(key=lambda x: x["volume_num"])
                file_key = "volume_file"
            else:
                return False

            total_size = split_info.get("original_size", 0)
            processed_size = 0
            
            with open(output_path, "wb") as out_f:
                for i, chunk in enumerate(chunks):
                    chunk_path = base_dir / chunk[file_key]
                    if not chunk_path.exists():
                        log_error(f"找不到分块文件: {chunk_path.name}")
                        return False
                    
                    with open(chunk_path, "rb") as in_f:
                        # 大文件分块读取写入，避免内存溢出
                        while True:
                            data = in_f.read(1024 * 1024) # 1MB buffer
                            if not data:
                                break
                            out_f.write(data)
                    
                    # 简单的进度显示
                    if "chunk_size" in chunk:
                        processed_size += chunk["chunk_size"]
                    elif "volume_size" in chunk:
                        processed_size += chunk["volume_size"]
                    
                    if total_size > 0:
                        percent = (processed_size / total_size) * 100
                        print(f"\r合并进度: {percent:.1f}%", end="", flush=True)
            
            print() # 换行
            return True
        except Exception as e:
            log_error(f"Python 合并异常: {e}")
            if output_path.exists():
                output_path.unlink()
            return False

def merge_split_files_on_setup():
    """在安装时自动合并拆分文件"""
    log_info("检查并合并拆分的大文件...")
    
    project_root = Path(__file__).parent
    merger = StandaloneMerger()
    
    # 扫描拆分信息文件
    split_info_files = []
    for root, dirs, files in os.walk(project_root):
        if any(d in root for d in ['venv', '__pycache__', '.git', 'node_modules']):
            continue
        for file in files:
            if file.endswith('.split_info.json') or file == 'split_info.json':
                split_info_files.append(Path(root) / file)
    
    if not split_info_files:
        log_info("未找到拆分文件，跳过合并步骤")
        return True
    
    log_info(f"找到 {len(split_info_files)} 个拆分文件需要合并")
    
    success_count = 0
    for info_file in split_info_files:
        try:
            if merger.merge_file(info_file):
                success_count += 1
        except Exception as e:
            log_error(f"处理 {info_file.name} 时出错: {e}")
    
    if success_count == len(split_info_files):
        log_info("✓ 所有拆分文件合并成功")
        return True
    else:
        log_warning(f"⚠ 部分文件合并失败: {success_count}/{len(split_info_files)}")
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--merge", action="store_true", help="合并文件")
    args = parser.parse_args()
    
    merge_split_files_on_setup()