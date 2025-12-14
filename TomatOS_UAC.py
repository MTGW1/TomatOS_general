import os
import secrets
import json
import hashlib

class UAC:
    def __init__(self):
        self.secrets_path = os.path.join(os.path.dirname(__file__), "TomatOS_secrets.json")
        self.config = self._load_secrets()

    def _load_secrets(self):
        if not os.path.exists(self.secrets_path):
            return None
        try:
            with open(self.secrets_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading secrets: {e}")
            return None

    def verify_password(self, input_password):
        """
        验证密码。
        返回: (bool, str) -> (是否验证成功, 验证类型 'admin' | 'guest' | None)
        """
        if not self.config:
            return False, None

        stored_hash = self.config.get("admin_passhash")
        salt = self.config.get("salt")
        
        # 计算输入密码的哈希
        input_hash = hashlib.sha256((input_password + salt).encode()).hexdigest()
        
        if input_hash == stored_hash:
            return True, "admin" # 这里的 admin 只是代表密码匹配成功，具体权限还需要结合 TOTP 判断
        
        return False, None

    def get_totp_secret(self):
        if self.config:
            return self.config.get("totp_secret")
        return None

    def get_admin_username(self):
        if self.config:
            return self.config.get("admin_username")
        return "alkane2005"
