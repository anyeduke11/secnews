"""应用版本号单一来源 (Single Source of Truth)。

所有需要展示应用版本的地方 (main.py FastAPI(version=...)、
exceptions.py 错误响应体、/api/health 等) 一律从这里 import,
禁止在别处再硬编码应用版本号。

注意: API 响应体内的 ``version`` 字段若表示 *数据格式/协议版本*
(如 export envelope、sync bundle), 与应用版本无关, 不受此约束。
"""

APP_VERSION = "1.8.0"
