# bootstrap.py
# coding: utf-8

"""
启动引导脚本 (Bootstrap Script)

该脚本的主要职责是：
配置 Python 的搜索路径 (sys.path)，确保项目内的模块可以被绝对路径正确引用。
注意：该文件应该在应用程序启动的最早期被调用（例如在 main.py 的第一行）。
"""

import sys
import os

# ==========================================
# 1. 环境路径配置
# ==========================================
# 获取当前文件所在的目录（即项目的根目录）
# 处理 PyInstaller 打包后的情况
if getattr(sys, 'frozen', False):
    # 如果是打包后的可执行文件，使用可执行文件所在目录
    ROOT_DIR = os.path.dirname(sys.executable)
else:
    # 开发环境，使用当前文件所在目录
    ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# 将项目根目录添加到 Python 的搜索路径中 (优先级最高)
# 这解决了 "ModuleNotFoundError: No module named 'src'" 这类导入错误
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# 将 vendor 目录添加到 Python 的搜索路径中
# 这样可以直接使用 "from indextts.xxx import xxx" 导入 vendor 中的 indextts 包
VENDOR_DIR = os.path.join(ROOT_DIR, 'vendor')
if os.path.exists(VENDOR_DIR) and VENDOR_DIR not in sys.path:
    sys.path.insert(0, VENDOR_DIR)
    print(f"[Bootstrap] Added vendor to sys.path: {VENDOR_DIR}")
elif not os.path.exists(VENDOR_DIR):
    print(f"[Bootstrap] Warning: vendor directory not found: {VENDOR_DIR}")


print(f"[Bootstrap] Project root set to: {ROOT_DIR}")
