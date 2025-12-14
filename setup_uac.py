import json
import hashlib
import os
import getpass
import secrets
from logger import logger

def setup_secrets():
    logger.info("=== TomatOS UAC Setup ===")
    
    # 1. 用户名
    username = input("输入管理员用户名 (默认: admin): ").strip()
    if not username:
        username = "admin"
    
    # 2. 密码
    password = getpass.getpass("输入管理员密码: ").strip()
    if not password:
        print("密码不能为空!")
        return

    # 3. 获取 TOTP 密钥
    totp_secret = input("输入 TOTP 密钥 (来自 setup_totp.py): ").strip()
    if not totp_secret:
        print("TOTP 密钥不能为空!")
        return

    # 4. 生成盐值
    salt = secrets.token_hex(2048)  # 4096 字节的十六进制字符串
    
    # 5. 哈希密码 (SHA256(password + salt))
    passhash = hashlib.sha256((password + salt).encode()).hexdigest()
    
    # 6. 保存到 JSON
    secrets_data = {
        "admin_username": username,
        "admin_passhash": passhash,
        "salt": salt,
        "totp_secret": totp_secret
    }
    
    file_path = os.path.join(os.path.dirname(__file__), "TomatOS_secrets.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(secrets_data, f, indent=4)
        
    logger.info(f"\n[Success] 密钥已保存到 {file_path}")
    logger.info("你现在可以删除此脚本。")

if __name__ == "__main__":
    setup_secrets()
