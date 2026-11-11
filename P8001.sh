#!/bin/bash
# ========================================
# IndexTTS API Startup Script
# ========================================

# Default parameters
HOST_ADDRESS=""
PORT=8001

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --host)
            HOST_ADDRESS="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Fix libgomp warning when OMP_NUM_THREADS is set to an invalid value
export OMP_NUM_THREADS=1

# Color definitions
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  IndexTTS API Startup Script${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# ----------------- 优化后的环境激活逻辑 -----------------
# 寻找 Conda 初始化脚本
CONDA_SH=$(find ~/.conda ~/anaconda3 ~/miniconda3 /opt/conda /opt/anaconda3 -name "conda.sh" 2>/dev/null | head -1)

if [ -n "$CONDA_SH" ]; then
    source "$CONDA_SH"
else
    eval "$(conda shell.bash hook)" 2>/dev/null
fi

LOCAL_PYTHON_DIR="$SCRIPT_DIR/python3.11"

# 优先激活本地指定的 python3.11 文件夹环境
if [ -d "$LOCAL_PYTHON_DIR" ]; then
    echo -e "${GREEN}[INFO] Found local Conda environment directory: $LOCAL_PYTHON_DIR${NC}"
    echo -e "${YELLOW}[INFO] Activating local environment via path...${NC}"
    
    conda activate "$LOCAL_PYTHON_DIR"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}[SUCCESS] Local Conda environment activated${NC}"
        USE_PYTHON_CMD="python"
    else
        echo -e "${RED}[ERROR] Failed to activate local environment path${NC}"
        read -p "Press Enter to exit..."
        exit 1
    fi
else
    # 如果不存在局部文件夹，尝试激活名为 python3.11 的标准命名环境
    echo -e "${YELLOW}[INFO] Local directory not found, trying named environment: python3.11 ...${NC}"
    conda activate python3.11
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}[SUCCESS] Conda environment [python3.11] activated${NC}"
        USE_PYTHON_CMD="python"
    else
        echo -e "${RED}[ERROR] Failed to activate any valid python3.11 environment${NC}"
        read -p "Press Enter to exit..."
        exit 1
    fi
fi
# -----------------------------------------------------

echo ""

# Check if main.py exists
if [ ! -f "main.py" ]; then
    echo -e "${RED}[ERROR] main.py not found, please ensure you are running this script in the correct directory${NC}"
    read -p "Press Enter to exit..."
    exit 1
fi

# Build startup command
PYTHON_CMD="$USE_PYTHON_CMD main.py"

# If Host or Port is specified, temporarily modify config.yaml
CONFIG_MODIFIED=false
ORIGINAL_CONFIG=""

if [ -n "$HOST_ADDRESS" ] || [ "$PORT" -ne 0 ]; then
    echo -e "${YELLOW}[INFO] Custom parameters detected, updating config...${NC}"
    
    if [ -f "config.yaml" ]; then
        # Backup original config
        ORIGINAL_CONFIG=$(cat config.yaml)
        
        if [ -n "$HOST_ADDRESS" ]; then
            sed -i '/^server:/,/^[a-zA-Z]/ s/^[[:space:]]*host:.*/  host: '"$HOST_ADDRESS"'/' config.yaml
            echo -e "${CYAN}  - Set Host: $HOST_ADDRESS${NC}"
        fi
        if [ "$PORT" -ne 0 ]; then
            sed -i '/^server:/,/^[a-zA-Z]/ s/^[[:space:]]*port:.*/  port: '"$PORT"'/' config.yaml
            echo -e "${CYAN}  - Set Port: $PORT${NC}"
        fi

        CONFIG_MODIFIED=true
    else
        echo -e "${YELLOW}[WARNING] config.yaml not found, will use default config${NC}"
    fi
fi

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Starting service...${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# Function to restore config on exit
cleanup() {
    if [ "$CONFIG_MODIFIED" = true ] && [ -n "$ORIGINAL_CONFIG" ]; then
        echo ""
        echo -e "${YELLOW}[INFO] Restoring original config...${NC}"
        echo "$ORIGINAL_CONFIG" > config.yaml
        echo -e "${GREEN}[SUCCESS] Config restored${NC}"
    fi
    echo ""
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}  Service stopped${NC}"
    echo -e "${CYAN}========================================${NC}"
}

# Register cleanup function
trap cleanup EXIT

# Start service
eval $PYTHON_CMD
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo -e "${RED}[ERROR] Service startup failed with exit code $EXIT_CODE${NC}"
fi

exit $EXIT_CODE