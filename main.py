import asyncio
import time
from PIL import Image
from paintboard_client import PaintboardClient
from config import print_config_summary, validate_config, IMAGE_CONFIG, ADVANCED_CONFIG

async def draw_simple_batch(client):
    """使用简化的批量绘制方法绘制任意大小图片"""
    print("🎨 开始使用简化批量绘制图片...")
    
    try:
        # 加载图片
        image_path = IMAGE_CONFIG["PATH"]
        start_x = IMAGE_CONFIG["START_X"]
        start_y = IMAGE_CONFIG["START_Y"]
        scale = IMAGE_CONFIG["SCALE"]
        
        # 使用PIL加载图片
        image = Image.open(image_path)
        image = image.convert('RGB')
        original_width, original_height = image.size
        
        print(f"📐 原始图片尺寸: {original_width}x{original_height}")
        
        # 应用缩放
        if scale != 1.0:
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            print(f"📏 缩放后尺寸: {new_width}x{new_height} (缩放比例: {scale})")
        
        width, height = image.size
        
        # 检查图片是否会超出画板边界
        if start_x + width > 1000 or start_y + height > 600:
            print("⚠️  警告: 图片部分内容可能会超出画板边界")
            # 计算实际可绘制的区域
            draw_width = min(width, 1000 - start_x)
            draw_height = min(height, 600 - start_y)
            print(f"📐 实际绘制区域: {draw_width}x{draw_height}")
        else:
            draw_width = width
            draw_height = height
        
        # 获取所有像素数据
        pixels = list(image.getdata())
        print(f"🖼️  已加载 {len(pixels)} 个像素")
        
        # 获取token数量和冷却时间
        token_count = client.get_token_count()
        cool_down_time = ADVANCED_CONFIG["COOL_DOWN_TIME"] / 1000.0
        
        print(f"🔑 可用token数量: {token_count}")
        print(f"⏱️  冷却时间: {cool_down_time}秒")
        
        # 创建像素列表
        pixel_list = []
        for y in range(draw_height):
            for x in range(draw_width):
                index = y * width + x
                if index < len(pixels):
                    r, g, b = pixels[index]
                    # 检查坐标是否在画板范围内
                    board_x = start_x + x
                    board_y = start_y + y
                    if 0 <= board_x < 1000 and 0 <= board_y < 600:
                        pixel_list.append({
                            "x": board_x,
                            "y": board_y,
                            "r": r,
                            "g": g,
                            "b": b
                        })
        
        print(f"🎯 准备绘制 {len(pixel_list)} 个像素 (位置: {start_x}, {start_y})")
        
        # 分批绘制，每批使用所有token
        completed = 0
        total = len(pixel_list)
        batch_size = min(token_count, len(pixel_list))
        
        # 计算预计时间
        estimated_batches = (total + batch_size - 1) // batch_size  # 向上取整
        estimated_time = estimated_batches * cool_down_time
        print(f"⏰ 预计需要 {estimated_batches} 批次，大约 {estimated_time:.1f} 秒")
        
        for i in range(0, total, batch_size):
            batch = pixel_list[i:i + batch_size]
            current_batch_size = len(batch)
            
            print(f"📦 发送第 {i//batch_size + 1}/{estimated_batches} 批，{current_batch_size} 个像素")
            
            try:
                # 使用简化方法发送
                result = await client.paint_batch_simple(batch)
                completed += current_batch_size
                
                progress = (completed / total) * 100
                print(f"📊 进度: {progress:.1f}% ({completed}/{total})")
                
                if result["success"]:
                    print(f"✅ 批次发送成功")
                else:
                    print(f"❌ 批次发送失败: {result['message']}")
                
                # 等待冷却时间（除了最后一批）
                if i + batch_size < total:
                    wait_time = cool_down_time
                    print(f"⏳ 等待 {wait_time} 秒冷却...")
                    await asyncio.sleep(wait_time)
                    
            except Exception as e:
                print(f"❌ 批次发送失败: {e}")
                # 继续尝试下一批
        
        print(f"🎉 图片绘制完成！总共发送 {completed} 个像素")
        return True
        
    except Exception as e:
        print(f"❌ 绘制图片失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def draw_optimized_batch(client):
    """优化的批量绘制方法，考虑性能和大图片处理"""
    print("🎨 开始使用优化批量绘制图片...")
    
    try:
        # 加载图片
        image_path = IMAGE_CONFIG["PATH"]
        start_x = IMAGE_CONFIG["START_X"]
        start_y = IMAGE_CONFIG["START_Y"]
        scale = IMAGE_CONFIG["SCALE"]
        
        # 使用PIL加载图片
        image = Image.open(image_path)
        image = image.convert('RGB')
        original_width, original_height = image.size
        
        print(f"📐 原始图片尺寸: {original_width}x{original_height}")
        
        # 应用缩放
        if scale != 1.0:
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            print(f"📏 缩放后尺寸: {new_width}x{new_height} (缩放比例: {scale})")
        
        width, height = image.size
        
        # 检查图片是否会超出画板边界
        if start_x + width > 1000 or start_y + height > 600:
            print("⚠️  警告: 图片部分内容可能会超出画板边界")
            # 计算实际可绘制的区域
            draw_width = min(width, 1000 - start_x)
            draw_height = min(height, 600 - start_y)
            print(f"📐 实际绘制区域: {draw_width}x{draw_height}")
        else:
            draw_width = width
            draw_height = height
        
        # 获取所有像素数据
        pixels = list(image.getdata())
        print(f"🖼️  已加载 {len(pixels)} 个像素")
        
        # 获取token数量和冷却时间
        token_count = client.get_token_count()
        cool_down_time = ADVANCED_CONFIG["COOL_DOWN_TIME"] / 1000.0-1.005
        
        print(f"🔑 可用token数量: {token_count}")
        print(f"⏱️  冷却时间: {cool_down_time}秒")
        
        # 创建像素列表
        pixel_list = []
        for y in range(draw_height):
            for x in range(draw_width):
                index = y * width + x
                if index < len(pixels):
                    r, g, b = pixels[index]
                    # 检查坐标是否在画板范围内
                    board_x = start_x + x
                    board_y = start_y + y
                    if 0 <= board_x < 1000 and 0 <= board_y < 600:
                        pixel_list.append({
                            "x": board_x,
                            "y": board_y,
                            "r": r,
                            "g": g,
                            "b": b
                        })
        
        print(f"🎯 准备绘制 {len(pixel_list)} 个像素 (位置: {start_x}, {start_y})")
        
        # 分批绘制，每批使用所有token
        completed = 0
        total = len(pixel_list)
        batch_size = min(token_count, len(pixel_list))
        
        # 计算预计时间
        estimated_batches = (total + batch_size - 1) // batch_size  # 向上取整
        estimated_time = estimated_batches * cool_down_time
        print(f"⏰ 预计需要 {estimated_batches} 批次，大约 {estimated_time:.1f} 秒")
        
        # 记录开始时间
        start_time = time.time()
        
        for i in range(0, total, batch_size):
            batch = pixel_list[i:i + batch_size]
            current_batch_size = len(batch)
            
            # 计算已用时间和预计剩余时间
            elapsed_time = time.time() - start_time
            if completed > 0:
                remaining_time = (elapsed_time / completed) * (total - completed)
            else:
                remaining_time = estimated_time
                
            print(f"📦 发送第 {i//batch_size + 1}/{estimated_batches} 批，{current_batch_size} 个像素")
            print(f"⏱️  已用: {elapsed_time:.1f}s, 预计剩余: {remaining_time:.1f}s")
            
            try:
                # 使用简化方法发送
                result = await client.paint_batch_simple(batch)
                completed += current_batch_size
                
                progress = (completed / total) * 100
                print(f"📊 进度: {progress:.1f}% ({completed}/{total})")
                
                if result["success"]:
                    print(f"✅ 批次发送成功")
                else:
                    print(f"❌ 批次发送失败: {result['message']}")
                
                # 等待冷却时间（除了最后一批）
                if i + batch_size < total:
                    wait_time = cool_down_time
                    print(f"⏳ 等待 {wait_time} 秒冷却...")
                    await asyncio.sleep(wait_time)
                    
            except Exception as e:
                print(f"❌ 批次发送失败: {e}")
                # 继续尝试下一批
        
        total_time = time.time() - start_time
        print(f"🎉 图片绘制完成！总共发送 {completed} 个像素，用时 {total_time:.1f} 秒")
        return True
        
    except Exception as e:
        print(f"❌ 绘制图片失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_connection(client):
    """测试连接和基本功能"""
    print("🧪 测试连接和基本功能...")
    
    # 检查连接状态
    status = client.check_websocket_connection()
    print(f"🔍 当前连接状态: {status}")
    
    if status != "已连接":
        print("❌ WebSocket 未连接，无法测试")
        return False
    
    # 测试单个像素
    print("🎯 测试绘制单个像素...")
    try:
        # 使用简化方法测试
        test_pixels = [{"x": 0, "y": 0, "r": 0, "g": 255, "b": 255}]
        result = await client.paint_batch_simple(test_pixels)
        
        if result["success"]:
            print("✅ 测试像素已发送到队列")
            # 等待一段时间让数据发送
            print("⏳ 等待数据发送...")
            await asyncio.sleep(2)
            return True
        else:
            print(f"❌ 测试失败: {result['message']}")
            return False
            
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        return False

async def main():
    print('启动画板客户端...')
    
    # 验证配置
    errors = validate_config()
    if errors:
        print('配置验证失败:')
        for error in errors:
            print(f'   {error}')
        return
    
    print_config_summary()
    
    client = PaintboardClient()
    
    try:
        print('\n🚀 初始化客户端...')
        await client.initialize()
        
        # 测试连接
        print('\n🧪 测试连接...')
        test_success = await test_connection(client)
        
        if test_success:
            print('✅ 连接测试完成')
            
            # 等待一下让测试像素有机会发送
            await asyncio.sleep(1)
            
            # 选择绘制方式
            print('\n🎨 选择绘制方式:')
            print('1. 简单批量绘制')
            print('2. 优化批量绘制（推荐，显示进度和时间）')
            
            choice = 2  # 默认选择优化批量绘制
            
            # 开始绘制图片
            print('\n🎨 开始绘制图片...')
            if choice == 1:
                draw_success = await draw_simple_batch(client)
            else:
                draw_success = await draw_optimized_batch(client)
            
            if draw_success:
                print('🎉 图像绘制完成！')
            else:
                print('❌ 图像绘制失败')
            
            # 等待所有数据发送完成
            print("⏳ 等待剩余数据发送...")
            await asyncio.sleep(5)
            
        else:
            print('❌ 连接测试失败，请检查上述错误信息')
        
    except Exception as error:
        print(f'❌ 运行失败: {error}')
        import traceback
        traceback.print_exc()
    finally:
        # 延迟关闭以便查看结果
        await asyncio.sleep(3)
        client.close()
        print('客户端已关闭')

if __name__ == "__main__":
    asyncio.run(main())