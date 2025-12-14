#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from logger import logger
import asyncio
import os
import setup_totp
import setup_uac
import sys
import subprocess
from pathlib import Path

def merge_split_files():
    """合并拆分的大文件"""
    try:
        import setup_merge
        return setup_merge.merge_split_files_on_setup()
    except ImportError:
        logger.warning("未找到合并脚本 setup_merge.py，跳过合并步骤")
        return True
    except Exception as e:
        logger.exception(f"合并拆分文件时出错: {e}")
        return False

def main():
    # 初始化设置
    logger.info("TomatOS 初始化启动...")

    # 第一步：合并拆分的大文件
    merge_split_files()

    # TOTP 初始化
    try:
        setup_totp.generate_totp_config()
    except Exception as e:
        logger.exception(f"TOTP 配置失败: {e}")
    logger.info("TOTP 配置完成。")

    # UAC 初始化
    try:
        setup_uac.setup_secrets()
    except Exception as e:
        logger.exception(f"UAC 配置失败: {e}")

    logger.info("UAC 配置完成。")
    logger.info("TomatOS 初始化完成。")

    logger.info("需要在结束时运行服务器吗？ (y/n): ")
    choice_run = input().strip().lower()
    logger.info(f"需要在完成时销毁初始化脚本吗？ (y/n): ")
    choice_destroy = input().strip().lower()
    
    # 先处理服务器启动
    if choice_run == 'y':
        self_path = os.path.abspath(__file__)
        server_path = self_path.replace("setup.py", "server.py")
        logger.info(f"启动服务器，脚本路径: {server_path}")
        
        # 检查 server.py 是否存在
        if not os.path.exists(server_path):
            logger.error(f"服务器文件不存在: {server_path}")
            logger.info("请确保 server.py 文件存在于同一目录中。")
            return
        
        # 新开一个无关联的控制台进程运行服务器
        if os.name == 'nt':  # Windows
            subprocess.Popen(['start', 'cmd', '/k', f'python "{server_path}"'], shell=True)
        else:  # macOS/Linux
            subprocess.Popen(['nohup', 'python3', f'"{server_path}"', '&'])
        logger.info("服务器已启动。")
    else:
        logger.info("跳过服务器启动。")
    
    # 最后处理脚本销毁（如果用户选择）
    if choice_destroy == 'y':
        script_path = os.path.abspath(__file__)
        try:
            os.remove(script_path)
            logger.info("初始化脚本已销毁。")
        except Exception as e:
            logger.exception(f"销毁初始化脚本失败: {e}")
    else:
        logger.info("初始化脚本保留。")
if __name__ == "__main__":
    logger.info(f"{'='*10} TomatOS 初始化脚本 {'='*10}")
    sys.exit(main())