"""
批量队列测试脚本
================
用于测试 IndexTTS API 的队列管理和智能模型缓存功能。

测试场景：
1. 连续提交多个 V1.5 任务（测试模型复用）
2. 提交 V2.0 任务（测试模型切换）
3. 再提交 V1.5 任务（测试再次切换）
4. 等待所有任务完成（测试自动释放）
"""

import requests
import time
import sys
import os

# 导入配置
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

API_BASE_URL = "http://localhost:8000"

# 定义测试任务
TEST_TASKS = [
    {
        "name": "任务1 - V1.5 短文本",
        "version": "v1.5",
        "payload": {
            "text": "这是第一个测试任务。",
            "spk_audio_prompt": "voices/ref_audios/常用/ref_1766279369751.wav",
            "output_path": "output/queue_test_1_v15.wav",
            "verbose": True
        }
    },
    {
        "name": "任务2 - V1.5 短文本",
        "version": "v1.5",
        "payload": {
            "text": "这是第二个测试任务，应该复用已加载的模型。",
            "spk_audio_prompt": "voices/ref_audios/常用/ref_1766279369751.wav",
            "output_path": "output/queue_test_2_v15.wav",
            "verbose": True
        }
    },
    {
        "name": "任务3 - V2.0 切换",
        "version": "v2.0",
        "payload": {
            "text": "现在切换到 V2.0 模型，应该会卸载 V1.5。",
            "spk_audio_prompt": "voices/ref_audios/常用/ref_1766279369751.wav",
            "output_path": "output/queue_test_3_v20.wav",
            "verbose": True
        }
    },
    {
        "name": "任务4 - V2.0 复用",
        "version": "v2.0",
        "payload": {
            "text": "继续使用 V2.0，应该复用已加载的模型。",
            "spk_audio_prompt": "voices/ref_audios/常用/ref_1766279369751.wav",
            "output_path": "output/queue_test_4_v20.wav",
            "verbose": True
        }
    },
    {
        "name": "任务5 - 再次切换到 V1.5",
        "version": "v1.5",
        "payload": {
            "text": "再次切换回 V1.5，测试模型切换。",
            "spk_audio_prompt": "voices/ref_audios/常用/ref_1766279369751.wav",
            "output_path": "output/queue_test_5_v15.wav",
            "verbose": True
        }
    }
]

def submit_tasks():
    """批量提交任务"""
    print("="*80)
    print("IndexTTS API 队列批量测试")
    print("="*80)
    
    # 检查服务器
    print("\n检查 API 服务器连接...")
    try:
        response = requests.get(f"{API_BASE_URL}/", timeout=5)
        response.raise_for_status()
        print(f"✓ API 服务器运行正常: {API_BASE_URL}")
    except requests.exceptions.RequestException as e:
        print(f"✗ 无法连接到 API 服务器: {e}")
        print("\n请先启动服务器：python main.py")
        sys.exit(1)
    
    # 提交所有任务
    task_ids = []
    print(f"\n开始提交 {len(TEST_TASKS)} 个任务到队列...")
    print("-"*80)
    
    for i, task in enumerate(TEST_TASKS, 1):
        print(f"\n[{i}/{len(TEST_TASKS)}] {task['name']}")
        print(f"  版本: {task['version'].upper()}")
        print(f"  文本: {task['payload']['text'][:40]}...")
        
        try:
            response = requests.post(
                f"{API_BASE_URL}/{task['version']}/generate",
                json=task['payload'],
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            task_id = result.get('task_id')
            task_ids.append({
                'id': task_id,
                'name': task['name'],
                'version': task['version']
            })
            print(f"  ✓ 已提交，Task ID: {task_id}")
            
        except requests.exceptions.RequestException as e:
            print(f"  ✗ 提交失败: {e}")
            continue
        
        # 短暂延迟，避免请求过快
        time.sleep(0.5)
    
    print("\n" + "="*80)
    print(f"所有任务已提交！共 {len(task_ids)} 个任务在队列中")
    print("="*80)
    
    return task_ids

def monitor_tasks(task_ids):
    """监控所有任务的执行状态"""
    print("\n开始监控任务执行...")
    print("-"*80)
    
    try:
        from tqdm import tqdm
        use_tqdm = True
    except ImportError:
        use_tqdm = False
        print("提示：安装 tqdm 可获得更好的进度显示 (pip install tqdm)")
    
    completed = []
    failed = []
    
    if use_tqdm:
        with tqdm(total=len(task_ids), desc="总体进度", unit="task", ncols=100) as pbar:
            while len(completed) + len(failed) < len(task_ids):
                for task_info in task_ids:
                    task_id = task_info['id']
                    
                    # 跳过已完成或失败的任务
                    if task_id in completed or task_id in failed:
                        continue
                    
                    try:
                        response = requests.get(f"{API_BASE_URL}/status/{task_id}")
                        response.raise_for_status()
                        status_data = response.json()
                        status = status_data.get('status')
                        
                        if status == 'completed':
                            completed.append(task_id)
                            pbar.update(1)
                            pbar.set_postfix_str(f"✅ {task_info['name']}")
                        elif status == 'failed':
                            failed.append(task_id)
                            pbar.update(1)
                            error = status_data.get('error', 'Unknown error')
                            pbar.set_postfix_str(f"❌ {task_info['name']}: {error[:30]}")
                        elif status == 'processing':
                            pbar.set_postfix_str(f"🔄 {task_info['name']}")
                        
                    except requests.exceptions.RequestException as e:
                        print(f"\n✗ 查询状态失败: {e}")
                
                time.sleep(2)
    else:
        # 简单文本模式
        while len(completed) + len(failed) < len(task_ids):
            print(f"\r进度: {len(completed)}/{len(task_ids)} 完成, {len(failed)} 失败", end='')
            
            for task_info in task_ids:
                task_id = task_info['id']
                if task_id in completed or task_id in failed:
                    continue
                
                try:
                    response = requests.get(f"{API_BASE_URL}/status/{task_id}")
                    response.raise_for_status()
                    status_data = response.json()
                    status = status_data.get('status')
                    
                    if status == 'completed':
                        completed.append(task_id)
                        print(f"\n✓ {task_info['name']} 完成")
                    elif status == 'failed':
                        failed.append(task_id)
                        error = status_data.get('error', 'Unknown error')
                        print(f"\n✗ {task_info['name']} 失败: {error}")
                
                except requests.exceptions.RequestException:
                    pass
            
            time.sleep(2)
    
    # 显示最终结果
    print("\n" + "="*80)
    print("测试完成！")
    print("="*80)
    print(f"✅ 成功: {len(completed)}/{len(task_ids)}")
    print(f"❌ 失败: {len(failed)}/{len(task_ids)}")
    
    if failed:
        print("\n失败的任务：")
        for task_info in task_ids:
            if task_info['id'] in failed:
                print(f"  - {task_info['name']}")
    
    print("\n" + "="*80)
    print("观察要点：")
    print("1. 查看服务器日志，确认模型复用（连续相同版本任务）")
    print("2. 查看服务器日志，确认模型切换（V1.5 ↔ V2.0）")
    print("3. 等待约 1 秒后，查看是否自动释放了最后使用的模型")
    print("="*80)

def main():
    # 提交任务
    task_ids = submit_tasks()
    
    if not task_ids:
        print("没有任务成功提交")
        return
    
    # 监控任务
    monitor_tasks(task_ids)

if __name__ == "__main__":
    main()
