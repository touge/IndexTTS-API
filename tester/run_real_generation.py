"""
真实音频生成测试脚本
====================
此脚本会向运行中的 IndexTTS API 服务器发送真实请求并生成音频。

使用前提：
1. 确保 API 服务器已启动：python main.py 或 uvicorn app.api.main:app --reload
2. 确保 config.py 中的参考音频路径正确且文件存在
3. 确保模型文件已正确配置在 config.yaml 中

运行方式：
python tester/run_real_generation.py
"""

import requests
import time
import sys
import os

# 导入配置
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from tester.config import TEST_PAYLOAD_V1_5, TEST_PAYLOAD_V2_0
except ImportError:
    print("错误：无法导入 tester.config，请确保 config.py 存在")
    sys.exit(1)

# API 服务器地址
API_BASE_URL = "http://localhost:8000"

def test_v1_5_generation():
    """测试 V1.5 音频生成"""
    print("\n" + "="*60)
    print("测试 V1.5 音频生成")
    print("="*60)
    
    # 1. 提交任务
    print("\n[1] 提交 V1.5 生成任务...")
    print(f"文本: {TEST_PAYLOAD_V1_5['text'][:50]}...")
    print(f"参考音频: {TEST_PAYLOAD_V1_5['spk_audio_prompt']}")
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/v1.5/generate",
            json=TEST_PAYLOAD_V1_5,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        task_id = result.get('task_id')
        print(f"✓ 任务已提交，Task ID: {task_id}")
    except requests.exceptions.RequestException as e:
        print(f"✗ 提交失败: {e}")
        return None
    
    # 2. 轮询任务状态（带进度条）
    print("\n[2] 等待生成完成...")
    max_wait_time = 300  # 最多等待 5 分钟
    start_time = time.time()
    poll_interval = 2  # 每 2 秒查询一次
    
    try:
        from tqdm import tqdm
        use_tqdm = True
    except ImportError:
        use_tqdm = False
        print("提示：安装 tqdm 可获得更好的进度显示 (pip install tqdm)")
    
    if use_tqdm:
        # 使用进度条
        with tqdm(total=max_wait_time, desc="生成进度", unit="s", ncols=80) as pbar:
            last_status = None
            while time.time() - start_time < max_wait_time:
                try:
                    status_response = requests.get(f"{API_BASE_URL}/status/{task_id}")
                    status_response.raise_for_status()
                    status_data = status_response.json()
                    
                    status = status_data.get('status')
                    
                    # 更新进度条描述
                    if status != last_status:
                        if status == 'pending':
                            pbar.set_description("⏳ 排队中")
                        elif status == 'processing':
                            pbar.set_description("🔄 生成中")
                        last_status = status
                    
                    if status == 'completed':
                        pbar.set_description("✅ 完成")
                        pbar.n = max_wait_time
                        pbar.refresh()
                        result_path = status_data.get('result')
                        print(f"\n✓ 生成完成！")
                        print(f"  输出文件: {result_path}")
                        return result_path
                    elif status == 'failed':
                        pbar.set_description("❌ 失败")
                        error = status_data.get('error')
                        print(f"\n✗ 生成失败: {error}")
                        return None
                    
                    # 更新进度条
                    elapsed = int(time.time() - start_time)
                    pbar.n = min(elapsed, max_wait_time)
                    pbar.refresh()
                    
                    time.sleep(poll_interval)
                    
                except requests.exceptions.RequestException as e:
                    print(f"\n✗ 查询状态失败: {e}")
                    return None
    else:
        # 不使用进度条的简单模式
        while time.time() - start_time < max_wait_time:
            try:
                status_response = requests.get(f"{API_BASE_URL}/status/{task_id}")
                status_response.raise_for_status()
                status_data = status_response.json()
                
                status = status_data.get('status')
                elapsed = int(time.time() - start_time)
                print(f"  [{elapsed}s] 状态: {status}", end='\r')
                
                if status == 'completed':
                    result_path = status_data.get('result')
                    print(f"\n✓ 生成完成！")
                    print(f"  输出文件: {result_path}")
                    return result_path
                elif status == 'failed':
                    error = status_data.get('error')
                    print(f"\n✗ 生成失败: {error}")
                    return None
                    
                time.sleep(poll_interval)
                
            except requests.exceptions.RequestException as e:
                print(f"\n✗ 查询状态失败: {e}")
                return None
    
    print(f"\n✗ 超时：任务在 {max_wait_time} 秒内未完成")
    return None

def test_v2_0_generation():
    """测试 V2.0 音频生成"""
    print("\n" + "="*60)
    print("测试 V2.0 音频生成")
    print("="*60)
    
    # 1. 提交任务
    print("\n[1] 提交 V2.0 生成任务...")
    print(f"文本: {TEST_PAYLOAD_V2_0['text'][:50]}...")
    print(f"参考音频: {TEST_PAYLOAD_V2_0['spk_audio_prompt']}")
    if TEST_PAYLOAD_V2_0.get('emo_vector'):
        print(f"情感向量: {TEST_PAYLOAD_V2_0['emo_vector']}")
    
    try:
        response = requests.post(
            f"{API_BASE_URL}/v2.0/generate",
            json=TEST_PAYLOAD_V2_0,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        task_id = result.get('task_id')
        print(f"✓ 任务已提交，Task ID: {task_id}")
    except requests.exceptions.RequestException as e:
        print(f"✗ 提交失败: {e}")
        return None
    
    # 2. 轮询任务状态（带进度条）
    print("\n[2] 等待生成完成...")
    max_wait_time = 300
    start_time = time.time()
    poll_interval = 2
    
    try:
        from tqdm import tqdm
        use_tqdm = True
    except ImportError:
        use_tqdm = False
    
    if use_tqdm:
        with tqdm(total=max_wait_time, desc="生成进度", unit="s", ncols=80) as pbar:
            last_status = None
            while time.time() - start_time < max_wait_time:
                try:
                    status_response = requests.get(f"{API_BASE_URL}/status/{task_id}")
                    status_response.raise_for_status()
                    status_data = status_response.json()
                    
                    status = status_data.get('status')
                    
                    if status != last_status:
                        if status == 'pending':
                            pbar.set_description("⏳ 排队中")
                        elif status == 'processing':
                            pbar.set_description("🔄 生成中")
                        last_status = status
                    
                    if status == 'completed':
                        pbar.set_description("✅ 完成")
                        pbar.n = max_wait_time
                        pbar.refresh()
                        result_path = status_data.get('result')
                        print(f"\n✓ 生成完成！")
                        print(f"  输出文件: {result_path}")
                        return result_path
                    elif status == 'failed':
                        pbar.set_description("❌ 失败")
                        error = status_data.get('error')
                        print(f"\n✗ 生成失败: {error}")
                        return None
                    
                    elapsed = int(time.time() - start_time)
                    pbar.n = min(elapsed, max_wait_time)
                    pbar.refresh()
                    
                    time.sleep(poll_interval)
                    
                except requests.exceptions.RequestException as e:
                    print(f"\n✗ 查询状态失败: {e}")
                    return None
    else:
        while time.time() - start_time < max_wait_time:
            try:
                status_response = requests.get(f"{API_BASE_URL}/status/{task_id}")
                status_response.raise_for_status()
                status_data = status_response.json()
                
                status = status_data.get('status')
                elapsed = int(time.time() - start_time)
                print(f"  [{elapsed}s] 状态: {status}", end='\r')
                
                if status == 'completed':
                    result_path = status_data.get('result')
                    print(f"\n✓ 生成完成！")
                    print(f"  输出文件: {result_path}")
                    return result_path
                elif status == 'failed':
                    error = status_data.get('error')
                    print(f"\n✗ 生成失败: {error}")
                    return None
                    
                time.sleep(poll_interval)
                
            except requests.exceptions.RequestException as e:
                print(f"\n✗ 查询状态失败: {e}")
                return None
    
    print(f"\n✗ 超时：任务在 {max_wait_time} 秒内未完成")
    return None

def main():
    print("IndexTTS API 真实音频生成测试")
    print("="*60)
    
    # 检查服务器是否运行
    print("\n检查 API 服务器连接...")
    try:
        response = requests.get(f"{API_BASE_URL}/", timeout=5)
        response.raise_for_status()
        print(f"✓ API 服务器运行正常: {API_BASE_URL}")
    except requests.exceptions.RequestException as e:
        print(f"✗ 无法连接到 API 服务器: {e}")
        print("\n请先启动服务器：")
        print("  python main.py")
        print("  或")
        print("  uvicorn app.api.main:app --reload")
        sys.exit(1)
    
    # 选择测试版本
    print("\n请选择要测试的版本：")
    print("  1. V1.5")
    print("  2. V2.0")
    print("  3. 两者都测试")
    
    choice = input("\n请输入选项 (1/2/3): ").strip()
    
    if choice == '1':
        test_v1_5_generation()
    elif choice == '2':
        test_v2_0_generation()
    elif choice == '3':
        test_v1_5_generation()
        test_v2_0_generation()
    else:
        print("无效选项")
        sys.exit(1)
    
    print("\n" + "="*60)
    print("测试完成")
    print("="*60)

if __name__ == "__main__":
    main()
