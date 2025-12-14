import pyotp
import qrcode
import os
from logger import logger

def generate_totp_config():
    # 生成一个新的 TOTP 密钥
    secret = pyotp.random_base32()
    logger.info(f"你的TOTP密钥: {secret}, 不要告诉其他人哦!")
    logger.info("请妥善保存此密钥！你需要将其放入服务器配置中。")
    
    # 为认证器应用创建一个URI
    # 这将在你的应用中显示为 "TomatOS:admin"
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name="admin", issuer_name="TomatOS")
    
    # 生成二维码
    qr = qrcode.QRCode()
    qr.add_data(uri)
    qr.make(fit=True)
    
    logger.info("\n请使用你的认证器应用（Google/Microsoft 认证器）扫描此二维码：")
    # Print QR code to terminal (using ASCII)
    qr.print_ascii(invert=True)
    
    # Also save as image just in case
    img = qr.make_image(fill_color="black", back_color="white")
    img.save("totp_qr.png")
    logger.info("\n二维码也已保存为 'totp_qr.png'")

if __name__ == "__main__":
    generate_totp_config()
