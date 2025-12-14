#!/usr/bin/env python3
"""
7-Zip 管理器
自动检测、安装和使用 7-Zip 进行文件压缩/解压
"""

import os
import sys
import subprocess
import platform
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List, Tuple
import urllib.request
import zipfile
import stat

class SevenZipManager:
    """7-Zip 管理器类"""
    
    def __init__(self):
        self.system = platform.system().lower()
        self.sevenzip_path = self._find_sevenzip()
        
    def _find_sevenzip(self) -> Optional[Path]:
        """查找系统中已安装的 7-Zip"""
        
        # Windows 上的常见安装路径
        if self.system == "windows":
            possible_paths = [
                Path("C:\\Program Files\\7-Zip\\7z.exe"),
                Path("C:\\Program Files (x86)\\7-Zip\\7z.exe"),
                Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "7-Zip" / "7z.exe",
                Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "7-Zip" / "7z.exe",
            ]
            
            # 检查 PATH 环境变量
            for path_dir in os.environ.get("PATH", "").split(os.pathsep):
                possible_paths.append(Path(path_dir) / "7z.exe")
            
            for path in possible_paths:
                if path.exists():
                    return path
        
        # Linux/macOS
        elif self.system in ["linux", "darwin"]:
            # 检查是否在 PATH 中
            try:
                result = subprocess.run(["which", "7z"], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    return Path(result.stdout.strip())
            except (subprocess.SubprocessError, FileNotFoundError):
                pass
        
        return None
    
    def is_installed(self) -> bool:
        """检查 7-Zip 是否已安装"""
        return self.sevenzip_path is not None and self.sevenzip_path.exists()
    
    def install_sevenzip(self) -> bool:
        """安装 7-Zip"""
        
        print("正在安装 7-Zip...")
        
        if self.system == "windows":
            return self._install_windows()
        elif self.system == "linux":
            return self._install_linux()
        elif self.system == "darwin":
            return self._install_macos()
        else:
            print(f"不支持的操作系统: {self.system}")
            return False
    
    def _install_windows(self) -> bool:
        """在 Windows 上安装 7-Zip"""
        
        # 7-Zip 下载 URL (最新版本)
        sevenzip_url = "https://www.7-zip.org/a/7z2409-x64.exe"
        installer_name = "7z-installer.exe"
        
        try:
            print(f"下载 7-Zip 安装程序...")
            
            # 下载安装程序
            temp_dir = tempfile.gettempdir()
            installer_path = Path(temp_dir) / installer_name
            
            urllib.request.urlretrieve(sevenzip_url, installer_path)
            
            print(f"安装程序已下载到: {installer_path}")
            print("正在安装 7-Zip (静默安装)...")
            
            # 静默安装
            result = subprocess.run(
                [str(installer_path), "/S", f"/D=C:\\Program Files\\7-Zip"],
                capture_output=True,
                text=True,
                timeout=300  # 5分钟超时
            )
            
            # 清理安装程序
            installer_path.unlink(missing_ok=True)
            
            if result.returncode == 0:
                print("✓ 7-Zip 安装成功")
                # 重新查找路径
                self.sevenzip_path = self._find_sevenzip()
                return True
            else:
                print(f"✗ 7-Zip 安装失败: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"✗ 安装 7-Zip 时出错: {e}")
            return False
    
    def _install_linux(self) -> bool:
        """在 Linux 上安装 7-Zip"""
        
        print("在 Linux 上安装 p7zip...")
        
        try:
            # 检测包管理器
            if shutil.which("apt-get"):
                # Debian/Ubuntu
                subprocess.run(["sudo", "apt-get", "update"], check=True)
                subprocess.run(["sudo", "apt-get", "install", "-y", "p7zip-full"], check=True)
            elif shutil.which("yum"):
                # RHEL/CentOS
                subprocess.run(["sudo", "yum", "install", "-y", "p7zip"], check=True)
            elif shutil.which("dnf"):
                # Fedora
                subprocess.run(["sudo", "dnf", "install", "-y", "p7zip"], check=True)
            elif shutil.which("pacman"):
                # Arch Linux
                subprocess.run(["sudo", "pacman", "-S", "--noconfirm", "p7zip"], check=True)
            elif shutil.which("zypper"):
                # openSUSE
                subprocess.run(["sudo", "zypper", "install", "-y", "p7zip"], check=True)
            else:
                print("✗ 不支持的系统包管理器")
                return False
            
            print("✓ p7zip 安装成功")
            self.sevenzip_path = self._find_sevenzip()
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"✗ 安装失败: {e}")
            return False
        except Exception as e:
            print(f"✗ 安装时出错: {e}")
            return False
    
    def _install_macos(self) -> bool:
        """在 macOS 上安装 7-Zip"""
        
        print("在 macOS 上安装 7-Zip...")
        
        try:
            # 使用 Homebrew
            if shutil.which("brew"):
                subprocess.run(["brew", "install", "p7zip"], check=True)
                print("✓ 7-Zip 安装成功")
                self.sevenzip_path = self._find_sevenzip()
                return True
            else:
                print("✗ 未找到 Homebrew，请先安装 Homebrew")
                return False
                
        except subprocess.CalledProcessError as e:
            print(f"✗ 安装失败: {e}")
            return False
        except Exception as e:
            print(f"✗ 安装时出错: {e}")
            return False
    
    def compress_with_7z(self, source_path: Path, output_path: Path, 
                        split_size_mb: int = 50, password: str = None) -> bool:
        """
        使用 7-Zip 压缩文件/目录
        
        Args:
            source_path: 源文件/目录路径
            output_path: 输出文件路径（不含扩展名）
            split_size_mb: 分卷大小（MB）
            password: 密码（可选）
            
        Returns:
            是否成功
        """
        
        if not self.is_installed():
            print("错误: 7-Zip 未安装")
            return False
        
        if not source_path.exists():
            print(f"错误: 源路径不存在: {source_path}")
            return False
        
        print(f"使用 7-Zip 压缩: {source_path}")
        print(f"输出到: {output_path}.7z")
        
        # 构建 7z 命令
        cmd = [str(self.sevenzip_path), "a"]
        
        # 分卷参数
        if split_size_mb > 0:
            cmd.append(f"-v{split_size_mb}m")
        
        # 密码参数
        if password:
            cmd.extend(["-p" + password])
        
        # 压缩级别 (使用 mx5 以平衡速度和内存)
        cmd.extend(["-mx5", "-mmt=on"])
        
        # 输出文件和源文件
        # 如果 output_path 已经以 .7z 结尾，就不再添加
        output_str = str(output_path)
        if not output_str.lower().endswith(".7z"):
            output_str += ".7z"
            
        cmd.append(output_str)
        cmd.append(str(source_path))
        
        try:
            print(f"执行命令: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1小时超时
            )
            
            if result.returncode == 0:
                print("✓ 压缩成功")
                
                # 检查是否生成了分卷文件
                if split_size_mb > 0:
                    vol_files = list(output_path.parent.glob(f"{output_path.name}.7z.*"))
                    print(f"生成 {len(vol_files)} 个分卷文件")
                    for vol_file in vol_files:
                        size_mb = vol_file.stat().st_size / (1024 * 1024)
                        print(f"  {vol_file.name} - {size_mb:.2f} MB")
                
                return True
            else:
                print(f"✗ 压缩失败: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("✗ 压缩超时")
            return False
        except Exception as e:
            print(f"✗ 压缩时出错: {e}")
            return False
    
    def extract_with_7z(self, archive_path: Path, output_dir: Path, 
                       password: str = None) -> bool:
        """
        使用 7-Zip 解压文件
        
        Args:
            archive_path: 压缩文件路径（可以是分卷的第一个文件）
            output_dir: 输出目录
            password: 密码（可选）
            
        Returns:
            是否成功
        """
        
        if not self.is_installed():
            print("错误: 7-Zip 未安装")
            return False
        
        if not archive_path.exists():
            print(f"错误: 压缩文件不存在: {archive_path}")
            return False
        
        # 创建输出目录
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"使用 7-Zip 解压: {archive_path}")
        print(f"解压到: {output_dir}")
        
        # 构建 7z 命令
        cmd = [str(self.sevenzip_path), "x"]
        
        # 密码参数
        if password:
            cmd.extend(["-p" + password])
        
        # 输出目录和源文件
        cmd.extend([f"-o{output_dir}", str(archive_path)])
        
        # 覆盖所有文件
        cmd.append("-y")
        
        try:
            print(f"执行命令: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1小时超时
            )
            
            if result.returncode == 0:
                print("✓ 解压成功")
                return True
            else:
                print(f"✗ 解压失败: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("✗ 解压超时")
            return False
        except Exception as e:
            print(f"✗ 解压时出错: {e}")
            return False
    
    def create_split_archive(self, source_path: Path, chunk_size_mb: int = 50) -> Tuple[bool, Path]:
        """
        创建分卷压缩文件（用于 Git 上传）
        
        Args:
            source_path: 源文件/目录
            chunk_size_mb: 分卷大小（MB）
            
        Returns:
            (是否成功, 第一个分卷文件路径)
        """
        
        if not source_path.exists():
            print(f"错误: 源路径不存在: {source_path}")
            return False, None
        
        # 输出路径（与源文件同目录）
        output_base = source_path.parent / f"{source_path.name}.7z"
        
        success = self.compress_with_7z(
            source_path=source_path,
            output_path=output_base,
            split_size_mb=chunk_size_mb
        )
        
        if success:
            # 找到第一个分卷文件
            first_volume = output_base.with_suffix(".7z.001")
            if not first_volume.exists():
                first_volume = output_base.with_suffix(".7z")
            
            return True, first_volume
        else:
            return False, None
    
    def extract_split_archive(self, first_volume_path: Path, output_dir: Path) -> bool:
        """
        解压分卷压缩文件
        
        Args:
            first_volume_path: 第一个分卷文件路径
            output_dir: 输出目录
            
        Returns:
            是否成功
        """
        return self.extract_with_7z(first_volume_path, output_dir)

def ensure_sevenzip_installed() -> SevenZipManager:
    """
    确保 7-Zip 已安装，如果没有则自动安装
    
    Returns:
        SevenZipManager 实例
    """
    
    manager = SevenZipManager()
    
    if not manager.is_installed():
        print("7-Zip 未安装，尝试自动安装...")
        
        # 询问用户是否安装
        response = input("是否自动安装 7-Zip？(y/N): ").strip().lower()
        if response in ['y', 'yes']:
            if manager.install_sevenzip():
                print("✓ 7-Zip 安装成功")
            else:
                print("⚠ 7-Zip 安装失败，将使用备用方案")
        else:
            print("跳过 7-Zip 安装，将使用备用方案")
    
    return manager

def main():
    """测试函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="7-Zip 管理器")
    parser.add_argument("action", choices=["check", "install", "compress", "extract"],
                       help="操作类型")
    parser.add_argument("--source", type=str, help="源文件/目录")
    parser.add_argument("--output", type=str, help="输出文件/目录")
    parser.add_argument("--split-size", type=int, default=50,
                       help="分卷大小（MB，默认50）")
    parser.add_argument("--password", type=str, help="密码（可选）")
    
    args = parser.parse_args()
    
    manager = SevenZipManager()
    
    if args.action == "check":
        if manager.is_installed():
            print(f"✓ 7-Zip 已安装: {manager.sevenzip_path}")
        else:
            print("✗ 7-Zip 未安装")
            
    elif args.action == "install":
        if manager.install_sevenzip():
            print("✓ 7-Zip 安装成功")
        else:
            print("✗ 7-Zip 安装失败")
            
    elif args.action == "compress":
        if not args.source or not args.output:
            print("错误: 需要 --source 和 --output 参数")
            return
        
        source_path = Path(args.source)
        output_path = Path(args.output)
        
        success = manager.compress_with_7z(
            source_path=source_path,
            output_path=output_path,
            split_size_mb=args.split_size,
            password=args.password
        )
        
        if success:
            print("✓ 压缩完成")
        else:
            print("✗ 压缩失败")
            
    elif args.action == "extract":
        if not args.source or not args.output:
            print("错误: 需要 --source 和 --output 参数")
            return
        
        archive_path = Path(args.source)
        output_dir = Path(args.output)
        
        success = manager.extract_with_7z(
            archive_path=archive_path,
            output_dir=output_dir,
            password=args.password
        )
        
        if success:
            print("✓ 解压完成")
        else:
            print("✗ 解压失败")

if __name__ == "__main__":
    main()