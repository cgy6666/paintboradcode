import json
import threading
import time
import struct
import asyncio
import requests
from PIL import Image
import numpy as np
from config import ACCESS_KEYS, IMAGE_CONFIG, READONLY, WRITEONLY, ADVANCED_CONFIG

# WebSocket 导入
try:
    from websocket import WebSocketApp
except ImportError:
    try:
        import websocket
        WebSocketApp = websocket.WebSocketApp
    except ImportError:
        print("❌ 请安装 websocket-client: pip install websocket-client")
        raise

class PaintboardClient:
    def __init__(self):
        self.api_base = "https://paintboard.luogu.me"
        self.ws_url = "wss://paintboard.luogu.me/api/paintboard/ws"
        
        # Token 管理
        self.access_keys = ACCESS_KEYS
        self.tokens = []
        self.current_token_index = 0
        
        # 画板尺寸
        self.board_width = 1000
        self.board_height = 600
        
        # 批量绘制配置
        self.batch_size = ADVANCED_CONFIG["BATCH_SIZE"]
        self.cool_down_time = ADVANCED_CONFIG["COOL_DOWN_TIME"]
        self.actual_batch_size = 0
        
        # 冷却时间管理
        self.last_batch_time = 0
        self.batch_queue = []
        
        # 连接管理
        self.readonly = READONLY
        self.writeonly = WRITEONLY
        self.packet_count = 0
        self.last_reset_time = time.time()
        
        # 粘包发送队列
        self.chunks = []
        self.total_size = 0
        self.paint_id = 0
        
        # 回调函数存储
        self.paint_callbacks = {}
        
        # 图像绘制状态
        self.is_drawing_image = False
        self.draw_progress = 0
        
        # WebSocket 连接
        self.ws = None
        self.initialized = False
        self.ws_connected = False  # 新增：明确的连接状态
        
        # 线程控制
        self.running = False
        
        # 事件回调
        self.on_paint_update = None
        
        # 线程对象
        self.rate_thread = None
        self.batch_thread = None
        self.packet_thread = None
        self.ws_thread = None
    
    # ========== 初始化相关方法 ==========
    
    async def initialize(self):
        """异步初始化方法"""
        if self.initialized:
            return
        
        try:
            # 1. 从 access keys 获取 tokens
            await self.fetch_tokens_from_access_keys()
            
            # 2. 计算实际批量大小
            self.actual_batch_size = min(len(self.tokens), self.batch_size)
            print(f"✅ 成功获取 {len(self.tokens)} 个token，批量大小为 {self.actual_batch_size}")
            
            # 3. 初始化 WebSocket 连接
            await self.initialize_websocket_async()
            
            # 4. 启动各种处理器
            self.start_rate_limit_monitor()
            self.start_batch_processor()
            self.start_packet_sender()
            
            self.initialized = True
            print('✅ Paintboard客户端初始化完成')
        except Exception as error:
            print(f'❌ 初始化失败: {error}')
            raise error

    async def initialize_websocket_async(self):
        """异步初始化WebSocket连接"""
        ws_url = self.ws_url
        if self.readonly:
            ws_url += '?readonly=1'
        elif self.writeonly:
            ws_url += '?writeonly=1'
        
        print(f"🔗 连接 WebSocket: {ws_url}")
        
        # 使用事件来等待连接建立
        connected_event = threading.Event()
        
        def on_open(ws):
            print("✅ WebSocket 连接已打开。")
            self.ws_connected = True
            connected_event.set()
        
        def on_message(ws, message):
            self.on_websocket_message(ws, message)
        
        def on_error(ws, error):
            print(f"❌ WebSocket 出错: {error}")
            connected_event.set()  # 即使出错也设置事件，避免无限等待
        
        def on_close(ws, close_status_code, close_msg):
            reason = close_msg if close_msg else "Unknown"
            print(f"🔌 WebSocket 已经关闭 ({close_status_code}: {reason})")
            self.ws_connected = False
            self.handle_close_code(close_status_code, reason)
        
        self.ws = WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        # 在后台线程中运行 WebSocket
        def run_websocket():
            self.running = True
            print("🔄 启动 WebSocket 线程...")
            self.ws.run_forever()
        
        self.ws_thread = threading.Thread(target=run_websocket)
        self.ws_thread.daemon = True
        self.ws_thread.start()
        
        # 等待连接建立（最多等待5秒）
        print("⏳ 等待 WebSocket 连接建立...")
        connected = connected_event.wait(5)
        if connected and self.ws_connected:
            print("✅ WebSocket 连接成功建立")
        else:
            print("❌ WebSocket 连接建立超时或失败")
            raise Exception("WebSocket连接失败")
    
    # ========== WebSocket 相关方法 ==========
    
    def on_websocket_message(self, ws, message):
        """处理 WebSocket 消息"""
        try:
            if isinstance(message, str):
                print(f"📨 收到文本消息: {message}")
                return
            
            buffer = message
            offset = 0
            
            while offset < len(buffer):
                if offset >= len(buffer):
                    break
                    
                msg_type = buffer[offset]
                offset += 1
                
                if msg_type == 0xfa:  # 绘画消息
                    if offset + 6 <= len(buffer):
                        x = struct.unpack('<H', buffer[offset:offset+2])[0]
                        y = struct.unpack('<H', buffer[offset+2:offset+4])[0]
                        color_r = buffer[offset+4]
                        color_g = buffer[offset+5]
                        color_b = buffer[offset+6]
                        offset += 7
                        self.handle_paint_message(x, y, color_r, color_g, color_b)
                    else:
                        print("⚠️  绘画消息数据不完整")
                        break
                
                elif msg_type == 0xfc:  # 心跳 Ping
                    # 立即响应心跳
                    try:
                        pong_data = bytes([0xfb])
                        self.ws.send(pong_data, opcode=2)
                        if ADVANCED_CONFIG["DEBUG"]:
                            print("💓 发送Pong响应")
                    except Exception as e:
                        print(f"❌ 发送心跳响应失败: {e}")
                
                elif msg_type == 0xff:  # 绘画结果
                    if offset + 4 <= len(buffer):
                        paint_id = struct.unpack('<I', buffer[offset:offset+4])[0]
                        code = buffer[offset+4]
                        offset += 5
                        self.handle_paint_result(paint_id, code)
                        if ADVANCED_CONFIG["DEBUG"]:
                            status_msg = self.get_status_message(code)
                            print(f"📊 绘画结果: ID={paint_id}, 状态={status_msg['message']}")
                    else:
                        print("⚠️  绘画结果数据不完整")
                        break
                
                else:
                    print(f"❓ 未知的消息类型: {msg_type}")
        except Exception as e:
            print(f"❌ 处理WebSocket消息时出错: {e}")
            import traceback
            traceback.print_exc()

    # ========== 数据处理相关方法 ==========
    
    def create_single_paint_data(self, pixel, token_info):
        """创建单个像素的绘画数据包"""
        r, g, b, x, y = pixel["r"], pixel["g"], pixel["b"], pixel["x"], pixel["y"]
        paint_id = self.paint_id
        self.paint_id = (self.paint_id + 1) % 4294967296
        
        # Token 转换为 16 字节 UUID
        token_hex = token_info["token"].replace('-', '')
        try:
            token_bytes = bytes.fromhex(token_hex)
            if len(token_bytes) != 16:
                print(f"❌ Token长度错误: {len(token_bytes)} 字节，应为16字节")
                return None
        except Exception as e:
            print(f"❌ Token 转换失败: {e}, token: {token_info['token']}")
            return None
        
        # 构建绘画数据包 - 严格按照文档格式
        paint_data = bytearray()
        
        # 前8字节
        paint_data.append(0xfe)  # 操作码
        paint_data.extend(struct.pack('<H', x))  # x坐标，小端序
        paint_data.extend(struct.pack('<H', y))  # y坐标，小端序
        paint_data.extend([r, g, b])  # RGB值
        
        # 后23字节
        # UID 拆分为3字节（小端序，取低24位）
        uid = token_info["uid"]
        uid_bytes = struct.pack('<I', uid)[:3]  # 取前3字节（低24位）
        paint_data.extend(uid_bytes)
        
        # Token (16字节)
        paint_data.extend(token_bytes)
        
        # 绘图识别码 (4字节，小端序)
        paint_data.extend(struct.pack('<I', paint_id))
        
        # 验证数据长度
        expected_length = 31  # 1 + 2 + 2 + 3 + 3 + 16 + 4
        if len(paint_data) != expected_length:
            print(f"⚠️  数据长度异常: 期望 {expected_length} 字节，实际 {len(paint_data)} 字节")
            return None
        
        # 存储回调
        self.paint_callbacks[paint_id] = pixel.get("callback")
        
        return bytes(paint_data)
    
    def create_batch_paint_data(self, pixels):
        """创建批量绘画数据包"""
        if len(pixels) > self.actual_batch_size:
            raise Exception(f"批量像素数量超过限制: {len(pixels)} > {self.actual_batch_size}")
        
        batch_data = bytearray()
        successful_pixels = 0
        
        for pixel in pixels:
            token_info = self.get_next_token()
            paint_data = self.create_single_paint_data(pixel, token_info)
            
            if paint_data:
                batch_data.extend(paint_data)
                successful_pixels += 1
                
                if ADVANCED_CONFIG["DEBUG"]:
                    print(f"   像素 ({pixel['x']}, {pixel['y']}) -> RGB({pixel['r']}, {pixel['g']}, {pixel['b']}), UID: {token_info['uid']}")
        
        if successful_pixels == 0:
            raise Exception("所有像素数据包构建失败")
        
        print(f"📦 批量数据包构建完成: {successful_pixels} 个像素，总长度: {len(batch_data)} 字节")
        return bytes(batch_data)

    # ========== 线程管理方法 ==========
    
    def start_packet_sender(self):
        """启动包发送器"""
        def send_packets():
            while self.running:
                try:
                    if (self.chunks and self.ws_connected and 
                        self.ws and hasattr(self.ws, 'sock') and self.ws.sock):
                        
                        merged_data = self.get_merged_data()
                        if merged_data:
                            # 检查包大小限制（32KB）
                            if len(merged_data) > 32 * 1024:
                                print('❌ 包大小超过32KB限制')
                                continue
                            
                            # 检查速率限制
                            current_time = time.time()
                            if current_time - self.last_reset_time >= 1.0:
                                self.packet_count = 0
                                self.last_reset_time = current_time
                            
                            if self.packet_count >= 256:
                                print('⚠️  达到速率限制，等待下一秒')
                                time.sleep(0.1)
                                continue
                            
                            try:
                                if ADVANCED_CONFIG["DEBUG"]:
                                    print(f"📤 发送数据包，长度: {len(merged_data)} 字节")
                                
                                self.ws.send(merged_data, opcode=2)  # opcode=2 表示二进制帧
                                self.packet_count += 1
                                
                                if ADVANCED_CONFIG["DEBUG"]:
                                    print(f"✅ 数据包发送成功，当前发送计数: {self.packet_count}")
                            except Exception as e:
                                print(f"❌ 发送数据失败: {e}")
                                # 重新加入队列
                                self.append_data(merged_data)
                    
                    time.sleep(ADVANCED_CONFIG["SEND_INTERVAL"])
                    
                except Exception as e:
                    print(f"❌ 包发送器异常: {e}")
                    time.sleep(0.1)
        
        self.packet_thread = threading.Thread(target=send_packets)
        self.packet_thread.daemon = True
        self.packet_thread.start()
        print("✅ 包发送器已启动")

    def execute_batch_paint_operation(self, operation):
        """执行批量绘画操作"""
        pixels = operation["pixels"]
        callback = operation.get("callback")
        
        try:
            if not self.ws_connected:
                raise Exception("WebSocket未连接")
            
            batch_data = self.create_batch_paint_data(pixels)
            print(f"🎯 生成批量数据，包含 {len(pixels)} 个像素，数据长度: {len(batch_data)} 字节")
            
            # 调试：打印前几个字节的十六进制
            if len(batch_data) > 0 and ADVANCED_CONFIG["DEBUG"]:
                hex_str = ' '.join(f'{b:02x}' for b in batch_data[:20])
                print(f"   数据前20字节: {hex_str}...")
            
            self.append_data(batch_data)
            
            # 更新最后批量绘制时间
            self.last_batch_time = time.time() * 1000
            
            if callback:
                callback({"success": True, "message": f"批量绘制 {len(pixels)} 个像素已加入队列"})
        
        except Exception as error:
            print(f"❌ 执行批量绘制操作时出错: {error}")
            if callback:
                callback({"success": False, "message": str(error)})

    # ========== 连接状态检查 ==========
    
    def check_websocket_connection(self):
        """检查 WebSocket 连接状态"""
        if not self.ws:
            return "未初始化"
        
        if not self.ws_connected:
            return "未连接"
        
        try:
            # 简单的ping测试
            if hasattr(self.ws, 'sock') and self.ws.sock:
                return "已连接"
            else:
                return "socket不存在"
        except:
            return "连接状态未知"

    # ========== 简化的绘制方法 ==========
    
    async def paint_batch_simple(self, pixels):
        """简化的批量绘制方法，直接发送不等待响应"""
        if self.readonly:
            raise Exception('只读连接不能进行绘画操作')
        
        if not self.initialized:
            raise Exception('客户端未初始化')
        
        if not self.ws_connected:
            raise Exception('WebSocket未连接')
        
        # 检查所有坐标有效性
        for pixel in pixels:
            if not self.is_coordinate_valid(pixel["x"], pixel["y"]):
                raise Exception(f"坐标 ({pixel['x']}, {pixel['y']}) 超出画板范围")
        
        try:
            batch_data = self.create_batch_paint_data(pixels)
            self.append_data(batch_data)
            
            # 更新最后批量绘制时间
            self.last_batch_time = time.time() * 1000
            
            return {"success": True, "message": f"批量绘制 {len(pixels)} 个像素已加入队列"}
            
        except Exception as error:
            print(f"❌ 批量绘制失败: {error}")
            return {"success": False, "message": str(error)}
   
    async def fetch_tokens_from_access_keys(self):
        """从 access keys 获取 tokens"""
        if not self.access_keys:
            raise Exception('没有提供 access keys')
        
        print(f"🔄 开始从 {len(self.access_keys)} 个 access key 获取 token...")
        
        async def get_token_for_key(key):
            try:
                token = await self.get_token_from_access_key(key["uid"], key["access_key"])
                if token:
                    print(f"✅ 成功获取 UID {key['uid']} 的 token")
                    return {"uid": key["uid"], "token": token}
                else:
                    print(f"❌ 获取 UID {key['uid']} 的 token 失败")
                    return None
            except Exception as error:
                print(f"❌ 获取 UID {key['uid']} 的 token 时出错: {error}")
                return None
        
        # 由于 requests 是同步的，我们在线程中运行
        tasks = [get_token_for_key(key) for key in self.access_keys]
        results = await asyncio.gather(*tasks)
        
        self.tokens = [token for token in results if token is not None]
        
        if not self.tokens:
            raise Exception('未能获取到任何有效的 token')
    
    async def get_token_from_access_key(self, uid, access_key):
        """通过 HTTP API 获取 token"""
        url = f"{self.api_base}/api/auth/gettoken"
        data = {
            "uid": uid,
            "access_key": access_key
        }
        
        try:
            # 使用线程执行同步的 requests 调用
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(
                    url, 
                    json=data, 
                    timeout=10,
                    headers={'Content-Type': 'application/json'}
                )
            )
            
            if response.status_code != 200:
                print(f"   HTTP错误: {response.status_code} - {response.reason}")
                return None
            
            response_data = response.json()
            
            # 正确处理嵌套的数据结构
            if "data" in response_data and "token" in response_data["data"]:
                token = response_data["data"]["token"]
                return token
            else:
                # 检查是否有错误信息
                error_type = response_data.get("errorType", "UNKNOWN")
                if "data" in response_data and "errorType" in response_data["data"]:
                    error_type = response_data["data"]["errorType"]
                
                print(f"❌ 获取token失败，错误类型: {error_type}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"❌ 网络请求异常: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"❌ JSON解析异常: {e}")
            print(f"   原始响应: {response.text}")
            return None
        except Exception as e:
            print(f"❌ 未知异常: {e}")
            return None
    
    # ========== WebSocket 相关方法 ==========
    
    def initialize_websocket(self):
        """初始化 WebSocket 连接"""
        ws_url = self.ws_url
        if self.readonly:
            ws_url += '?readonly=1'
        elif self.writeonly:
            ws_url += '?writeonly=1'
        
        print(f"🔗 连接 WebSocket: {ws_url}")
        
        self.ws = WebSocketApp(
            ws_url,
            on_open=self.on_websocket_open,
            on_message=self.on_websocket_message,
            on_error=self.on_websocket_error,
            on_close=self.on_websocket_close
        )
        
        # 在后台线程中运行 WebSocket
        def run_websocket():
            self.running = True
            print("🔄 启动 WebSocket 线程...")
            self.ws.run_forever()
        
        self.ws_thread = threading.Thread(target=run_websocket)
        self.ws_thread.daemon = True
        self.ws_thread.start()
        
        # 等待连接建立
        print("⏳ 等待 WebSocket 连接建立...")
        time.sleep(2)
    
    def on_websocket_open(self, ws):
        print("✅ WebSocket 连接已打开。")
    
    def on_websocket_error(self, ws, error):
        print(f"❌ WebSocket 出错: {error}")
    
    def on_websocket_close(self, ws, close_status_code, close_msg):
        reason = close_msg if close_msg else "Unknown"
        print(f"🔌 WebSocket 已经关闭 ({close_status_code}: {reason})")
        self.handle_close_code(close_status_code, reason)
        self.running = False
    
    def handle_close_code(self, code, reason):
        """处理关闭代码"""
        if code == 1001:
            print('💓 心跳超时，请检查网络连接')
        elif code == 1002:
            print(f'📝 协议错误: {reason}')
        elif code == 1008:
            print('🚫 IP连接数超限或IP被封禁')
        elif code == 1009:
            print('📦 发送的消息过大，超过32KB限制')
        elif code == 1011:
            print('⚙️  服务器处理消息时发生错误')
        elif code == 1006:
            print('🌐 网络连接问题，可能是网络穿墙导致')
        else:
            print(f'❓ 未知关闭代码: {code}')
    
    def handle_paint_message(self, x, y, color_r, color_g, color_b):
        """处理绘画消息"""
        if self.on_paint_update:
            self.on_paint_update(x, y, color_r, color_g, color_b)
    
    def handle_paint_result(self, paint_id, code):
        """处理绘画结果"""
        if paint_id in self.paint_callbacks:
            callback = self.paint_callbacks[paint_id]
            status = self.get_status_message(code)
            
            # 添加回调函数检查
            if callback is not None:
                try:
                    callback(status)
                except Exception as e:
                    print(f"❌ 回调函数执行失败: {e}")
            else:
                # 如果没有回调函数，只是记录状态（可选）
                if ADVANCED_CONFIG["DEBUG"]:
                    print(f"📊 绘画结果 (无回调): ID={paint_id}, 状态={status['message']}")
        
        # 无论是否有回调，都要清理
        del self.paint_callbacks[paint_id]
        
        # 如果绘制成功，更新最后批量绘制时间
        if code == 0xef:
            self.last_batch_time = time.time() * 1000  # 转换为毫秒
    
    def get_status_message(self, code):
        """获取状态消息"""
        status_messages = {
            0xef: {"success": True, "message": "成功"},
            0xee: {"success": False, "message": "正在冷却"},
            0xed: {"success": False, "message": "Token无效"},
            0xec: {"success": False, "message": "请求格式错误"},
            0xeb: {"success": False, "message": "无权限"},
            0xea: {"success": False, "message": "服务器错误"}
        }
        return status_messages.get(code, {"success": False, "message": f"未知状态码: {code}"})
    
    def check_websocket_connection(self):
        """检查 WebSocket 连接状态"""
        if not self.ws:
            return "未初始化"
        
        if not hasattr(self.ws, 'sock'):
            return "无 socket 对象"
        
        if not self.ws.sock:
            return "socket 为 None"
        
        try:
            if self.ws.sock.connected:
                return "已连接"
            else:
                return "未连接"
        except:
            return "连接状态未知"
    
    # ========== 数据处理相关方法 ==========
    
    def append_data(self, paint_data):
        """粘包发送机制 - 添加数据到队列"""
        self.chunks.append(paint_data)
        self.total_size += len(paint_data)
    
    def get_merged_data(self):
        """粘包发送机制 - 获取合并的数据"""
        if self.total_size == 0:
            return None
        
        result = bytearray(self.total_size)
        offset = 0
        for chunk in self.chunks:
            result[offset:offset+len(chunk)] = chunk
            offset += len(chunk)
        
        self.total_size = 0
        self.chunks = []
        return bytes(result)
    
    def uint_to_bytes(self, value, num_bytes):
        """将整数转换为指定字节数的小端序字节"""
        result = bytearray(num_bytes)
        for i in range(num_bytes):
            result[i] = value & 0xFF
            value >>= 8
        return bytes(result)
    
    def is_batch_cooling_down(self):
        """检查批量冷却时间"""
        return (time.time() * 1000 - self.last_batch_time) < self.cool_down_time
    
    def get_remaining_batch_cool_down(self):
        """获取剩余批量冷却时间"""
        elapsed = time.time() * 1000 - self.last_batch_time
        return max(0, self.cool_down_time - elapsed)
    
    def get_next_token(self):
        """获取下一个可用的 token"""
        if not self.tokens:
            raise Exception('没有可用的 token')
        
        token = self.tokens[self.current_token_index]
        self.current_token_index = (self.current_token_index + 1) % len(self.tokens)
        return token
    
    async def paint_batch(self, pixels, callback=None):
        """批量绘制像素"""
        if self.readonly:
            raise Exception('只读连接不能进行绘画操作')
        
        if not self.initialized:
            raise Exception('客户端未初始化，请先调用 initialize() 方法')
        
        # 检查所有坐标有效性
        for pixel in pixels:
            if not self.is_coordinate_valid(pixel["x"], pixel["y"]):
                raise Exception(f"坐标 ({pixel['x']}, {pixel['y']}) 超出画板范围")
        
        # 使用 asyncio.Future 来处理异步回调
        future = asyncio.Future()
        
        def result_callback(result):
            if not future.done():
                if result["success"]:
                    future.set_result(result)
                else:
                    future.set_exception(Exception(result["message"]))
        
        batch_operation = {
            "pixels": pixels,
            "callback": result_callback
        }
        
        self.batch_queue.append(batch_operation)
        
        return await future
    
    # ========== 线程管理方法 ==========
    
    def start_rate_limit_monitor(self):
        """启动速率限制监控器"""
        def monitor_rate():
            while self.running:
                # 每秒重置包计数
                current_time = time.time()
                if current_time - self.last_reset_time >= 1.0:
                    self.packet_count = 0
                    self.last_reset_time = current_time
                time.sleep(0.1)  # 每100毫秒检查一次
        
        self.rate_thread = threading.Thread(target=monitor_rate)
        self.rate_thread.daemon = True
        self.rate_thread.start()
        print("✅ 速率限制监控器已启动")
    
    def start_batch_processor(self):
        """启动批量处理器"""
        def process_batches():
            while self.running:
                if (self.batch_queue and 
                    not self.is_batch_cooling_down() and 
                    self.ws and hasattr(self.ws, 'sock') and self.ws.sock and self.ws.sock.connected):
                    
                    operation = self.batch_queue.pop(0)
                    self.execute_batch_paint_operation(operation)
                
                time.sleep(0.01)  # 10毫秒检查一次
        
        self.batch_thread = threading.Thread(target=process_batches)
        self.batch_thread.daemon = True
        self.batch_thread.start()
        print("✅ 批量处理器已启动")
    
    def start_packet_sender(self):
        """启动包发送器"""
        def send_packets():
            while self.running:
                if (self.chunks and 
                    self.ws and hasattr(self.ws, 'sock') and self.ws.sock and self.ws.sock.connected):
                    
                    merged_data = self.get_merged_data()
                    if merged_data:
                        # 检查包大小限制（32KB）
                        if len(merged_data) > 32 * 1024:
                            print('❌ 包大小超过32KB限制')
                            continue
                        
                        try:
                            print(f"📤 准备发送数据包，长度: {len(merged_data)} 字节")
                            self.ws.send(merged_data, opcode=2)  # opcode=2 表示二进制帧
                            self.packet_count += 1
                            print(f"✅ 数据包发送成功，当前发送计数: {self.packet_count}")
                        except Exception as e:
                            print(f"❌ 发送数据失败: {e}")
                
                time.sleep(ADVANCED_CONFIG["SEND_INTERVAL"])  # 20毫秒发送一次
        
        self.packet_thread = threading.Thread(target=send_packets)
        self.packet_thread.daemon = True
        self.packet_thread.start()
        print("✅ 包发送器已启动")
    
    def execute_batch_paint_operation(self, operation):
        """执行批量绘画操作"""
        pixels = operation["pixels"]
        callback = operation["callback"]
        
        try:
            batch_data = self.create_batch_paint_data(pixels)
            print(f"🎯 生成批量数据，包含 {len(pixels)} 个像素，数据长度: {len(batch_data)} 字节")
            
            # 调试：打印前几个字节的十六进制
            if len(batch_data) > 0:
                hex_str = ' '.join(f'{b:02x}' for b in batch_data[:20])
                print(f"   数据前20字节: {hex_str}...")
            
            self.append_data(batch_data)
            
            # 更新最后批量绘制时间
            self.last_batch_time = time.time() * 1000
            
            if callback:
                callback({"success": True, "message": f"批量绘制 {len(pixels)} 个像素已加入队列"})
        
        except Exception as error:
            print(f"❌ 执行批量绘制操作时出错: {error}")
            if callback:
                callback({"success": False, "message": str(error)})
    
    # ========== 测试和工具方法 ==========
    
    async def test_single_pixel(self, x=500, y=300, r=255, g=0, b=0):
        """测试绘制单个像素"""
        print(f"🧪 测试绘制单个像素: ({x}, {y}) -> RGB({r}, {g}, {b})")
        
        try:
            # 检查连接状态
            status = self.check_websocket_connection()
            print(f"🔍 当前连接状态: {status}")
            
            if status != "已连接":
                print("❌ WebSocket 未连接，无法测试")
                return False
            
            # 创建单个像素的批量数据
            test_pixels = [{"r": r, "g": g, "b": b, "x": x, "y": y}]
            
            result = await self.paint_batch(test_pixels)
            print(f"✅ 测试像素已发送: {result}")
            return True
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    # ========== 图像处理相关方法 ==========
    
    def is_coordinate_valid(self, x, y):
        """检查坐标是否有效"""
        return 0 <= x < self.board_width and 0 <= y < self.board_height
    
    def is_image_within_bounds(self, start_x, start_y, width, height):
        """检查图片是否在边界内"""
        return (start_x >= 0 and start_y >= 0 and 
                start_x + width <= self.board_width and 
                start_y + height <= self.board_height)
    
    def get_image_valid_region(self, start_x, start_y, width, height):
        """获取图片有效区域"""
        valid_start_x = max(0, start_x)
        valid_start_y = max(0, start_y)
        valid_end_x = min(self.board_width, start_x + width)
        valid_end_y = min(self.board_height, start_y + height)
        
        return {
            "start_x": valid_start_x,
            "start_y": valid_start_y,
            "width": valid_end_x - valid_start_x,
            "height": valid_end_y - valid_start_y
        }
    
    def load_image(self, image_path=None):
        """加载图像"""
        if image_path is None:
            image_path = IMAGE_CONFIG["PATH"]
        
        try:
            image = Image.open(image_path)
            width, height = image.size
            channels = len(image.getbands())
            
            print(f"🖼️  图像尺寸: {width}x{height}, 通道数: {channels}")
            
            # 转换为 RGB 模式（确保3通道）
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # 获取像素数据
            pixels = list(image.getdata())
            pixel_data = []
            
            for pixel in pixels:
                if len(pixel) >= 3:
                    r, g, b = pixel[0], pixel[1], pixel[2]
                else:
                    # 对于单通道图像，使用相同值
                    r = g = b = pixel[0] if isinstance(pixel, int) else pixel[0]
                
                pixel_data.append({"r": r, "g": g, "b": b})
            
            return {
                "width": width,
                "height": height,
                "channels": 3,  # 强制转换为3通道
                "pixel_data": pixel_data
            }
        except Exception as error:
            print(f'❌ 加载图像失败: {error}')
            raise error
    
    async def draw_image(self, image_path=None, start_x=None, start_y=None, options=None):
        """绘制图像"""
        if self.readonly:
            raise Exception('只读连接不能进行绘画操作')
        
        if not self.initialized:
            raise Exception('客户端未初始化，请先调用 initialize() 方法')
        
        if options is None:
            options = {}
        
        if image_path is None:
            image_path = IMAGE_CONFIG["PATH"]
        if start_x is None:
            start_x = IMAGE_CONFIG["START_X"]
        if start_y is None:
            start_y = IMAGE_CONFIG["START_Y"]
        
        scale = options.get("scale", IMAGE_CONFIG["SCALE"])
        on_progress = options.get("on_progress")
        max_concurrent_batches = options.get("max_concurrent_batches", IMAGE_CONFIG["MAX_CONCURRENT_BATCHES"])
        
        # 验证起始坐标
        if not self.is_coordinate_valid(start_x, start_y):
            raise Exception(f"起始坐标 ({start_x}, {start_y}) 超出画板范围")
        
        try:
            self.is_drawing_image = True
            self.draw_progress = 0
            
            image_data = self.load_image(image_path)
            width, height, pixel_data = image_data["width"], image_data["height"], image_data["pixel_data"]
            
            scaled_width = int(width * scale)
            scaled_height = int(height * scale)
            
            # 检查图片是否超出画板范围
            if not self.is_image_within_bounds(start_x, start_y, scaled_width, scaled_height):
                valid_region = self.get_image_valid_region(start_x, start_y, scaled_width, scaled_height)
                print(f"⚠️  图片部分超出画板范围，将只绘制有效区域: ({valid_region['start_x']}, {valid_region['start_y']}) - ({valid_region['width']}x{valid_region['height']})")
                
                if valid_region["width"] <= 0 or valid_region["height"] <= 0:
                    raise Exception('图片完全超出画板范围')
            
            print(f"🎨 开始绘制图像，位置: ({start_x}, {start_y}), 缩放后尺寸: {scaled_width}x{scaled_height}")
            
            total_pixels = scaled_width * scaled_height
            completed_pixels = 0
            
            # 批量处理像素
            batch_promises = []
            
            for y in range(scaled_height):
                if not self.is_drawing_image:
                    break
                    
                for x in range(0, scaled_width, self.actual_batch_size):
                    if not self.is_drawing_image:
                        break
                    
                    batch_pixels = []
                    
                    # 收集一批像素
                    for i in range(self.actual_batch_size):
                        if x + i >= scaled_width:
                            break
                            
                        pixel_x = x + i
                        
                        # 计算在原始图像中的位置
                        orig_x = int(pixel_x / scale)
                        orig_y = int(y / scale)
                        orig_index = orig_y * width + orig_x
                        
                        if orig_index < len(pixel_data):
                            pixel = pixel_data[orig_index]
                            board_x = start_x + pixel_x
                            board_y = start_y + y
                            
                            # 检查坐标是否在画板范围内
                            if self.is_coordinate_valid(board_x, board_y):
                                batch_pixels.append({
                                    "r": pixel["r"],
                                    "g": pixel["g"], 
                                    "b": pixel["b"],
                                    "x": board_x,
                                    "y": board_y
                                })
                
                    if batch_pixels:
                        try:
                            await self.paint_batch(batch_pixels)
                            completed_pixels += len(batch_pixels)
                            self.draw_progress = completed_pixels / total_pixels
                            
                            if on_progress:
                                on_progress(self.draw_progress, completed_pixels, total_pixels)
                            
                        except Exception as error:
                            print(f"批量绘制失败: {error}")
                    
                    # 控制并发批次数
                    if len(batch_promises) >= max_concurrent_batches:
                        await asyncio.sleep(0.01)
                        batch_promises = []
                        
                        # 如果还在冷却中，等待剩余时间
                        if self.is_batch_cooling_down():
                            wait_time = self.get_remaining_batch_cool_down() / 1000  # 转换为秒
                            await asyncio.sleep(wait_time)
            
            print('✅ 图像绘制完成')
            self.is_drawing_image = False
            
        except Exception as error:
            print(f'❌ 绘制图像失败: {error}')
            self.is_drawing_image = False
            raise error
    
    async def draw_image_with_constants(self, options=None):
        """使用常量配置绘制图像"""
        if options is None:
            options = {}
        
        return await self.draw_image(
            IMAGE_CONFIG["PATH"],
            IMAGE_CONFIG["START_X"],
            IMAGE_CONFIG["START_Y"],
            {
                "scale": IMAGE_CONFIG["SCALE"],
                **options
            }
        )
    
    # ========== 状态查询方法 ==========
    
    def get_draw_progress(self):
        """获取绘制进度"""
        return self.draw_progress
    
    def is_drawing(self):
        """检查是否正在绘制"""
        return self.is_drawing_image
    
    def get_current_rate(self):
        """获取当前发送速率"""
        return self.packet_count
    
    def get_batch_queue_length(self):
        """获取批量队列长度"""
        return len(self.batch_queue)
    
    def get_token_count(self):
        """获取 token 数量"""
        return len(self.tokens)
    
    def get_actual_batch_size(self):
        """获取实际批量大小"""
        return self.actual_batch_size
    
    # ========== 管理方法 ==========
    
    def cancel_image_draw(self):
        """取消图像绘制"""
        self.is_drawing_image = False
        self.batch_queue = []
        print('🛑 图像绘制已取消')
    
    def add_access_key(self, uid, access_key):
        """添加 access key"""
        self.access_keys.append({"uid": uid, "access_key": access_key})
        print(f"✅ 已添加 access key，UID: {uid}")
    
    async def refresh_tokens(self):
        """刷新 tokens"""
        await self.fetch_tokens_from_access_keys()
        self.actual_batch_size = min(len(self.tokens), self.batch_size)
        print(f"🔄 刷新 token 完成，当前 token 数量: {len(self.tokens)}，批量大小: {self.actual_batch_size}")
    
    def close(self):
        """关闭客户端"""
        self.is_drawing_image = False
        self.batch_queue = []
        self.running = False
        
        if self.ws:
            self.ws.close()