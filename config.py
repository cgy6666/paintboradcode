"""
画板客户端配置文件
请根据实际情况修改以下配置
"""

# =============================================
# Access Key 配置
# =============================================
ACCESS_KEYS = [
    # 格式：{"uid": 用户ID, "access_key": "访问密钥"}
    # 可以从洛谷绘版获取 access key ,
    {"uid": 1048914, "access_key": "6KEKa77Q"},
    {"uid": 1683526, "access_key": "UpaiUxt6"},
    # 可以继续添加更多 access key，最多建议70个
]

# =============================================
# 图像绘制配置
# =============================================
IMAGE_CONFIG = {
    "PATH": "image.png",  # 图片文件路径
    "START_X": 520,     # X坐标 (0-999)
    "START_Y": 320,     # Y坐标 (0-599)
    "SCALE": 0.3,       # 缩放比例
    "MAX_CONCURRENT_BATCHES": 3
}

# =============================================
# 连接模式配置
# =============================================
READONLY = False    # 只读模式
WRITEONLY = False   # 只写模式

# =============================================
# 高级配置
# =============================================
ADVANCED_CONFIG = {
    "BATCH_SIZE": 10,
    "COOL_DOWN_TIME": 1145,
    "SEND_INTERVAL": 0.02,  # 20毫秒
    "DEBUG": True,
    "AUTO_RECONNECT": {
        "enabled": True,
        "max_attempts": 5,
        "delay": 3
    }
}

def validate_config():
    """验证配置是否有效"""
    errors = []

    # 检查 access_keys
    if not ACCESS_KEYS or len(ACCESS_KEYS) == 0:
        errors.append("❌ 未配置 ACCESS_KEYS，请至少提供一个 access key")
    else:
        for i, key in enumerate(ACCESS_KEYS):
            if "uid" not in key or "access_key" not in key:
                errors.append(f"❌ 第 {i + 1} 个 access key 配置不完整")
            if not isinstance(key["uid"], int):
                errors.append(f"❌ 第 {i + 1} 个 UID 必须是数字")

    # 检查图片配置
    if not IMAGE_CONFIG["PATH"]:
        errors.append("❌ 未配置图片路径")

    # 检查坐标范围
    if IMAGE_CONFIG["START_X"] < 0 or IMAGE_CONFIG["START_X"] >= 1000:
        errors.append("❌ START_X 必须在 0-999 范围内")
    if IMAGE_CONFIG["START_Y"] < 0 or IMAGE_CONFIG["START_Y"] >= 600:
        errors.append("❌ START_Y 必须在 0-599 范围内")

    # 检查模式配置
    if READONLY and WRITEONLY:
        errors.append("❌ READONLY 和 WRITEONLY 不能同时为 True")

    return errors

def print_config_summary():
    """打印配置摘要"""
    print('📋 配置摘要:')
    print(f'   Token 数量: {len(ACCESS_KEYS)}')
    print(f'   图片路径: {IMAGE_CONFIG["PATH"]}')
    print(f'   起始位置: ({IMAGE_CONFIG["START_X"]}, {IMAGE_CONFIG["START_Y"]})')
    print(f'   缩放比例: {IMAGE_CONFIG["SCALE"]}')
    mode = "只读" if READONLY else "只写" if WRITEONLY else "读写"
    print(f'   模式: {mode}')
    batch_size = min(len(ACCESS_KEYS), ADVANCED_CONFIG["BATCH_SIZE"])
    print(f'   批量大小: {batch_size}')

# 启动时验证配置
if __name__ == "__main__":
    errors = validate_config()
    if errors:
        print('🚨 配置验证失败:')
        for error in errors:
            print(f'   {error}')
        print('\n💡 请修改 config.py 文件中的配置')
        exit(1)
    else:
        print('✅ 配置验证通过')
        print_config_summary()
