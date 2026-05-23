#!/bin/bash
# ========================================
# IndexTTS API Startup Script
# ========================================
# Auto-detect Python environment and start IndexTTS API service
# Support custom IP address and port
#
# Usage:
#   ./P8001.sh
#   ./P8001.sh --port 9000
#   ./P8001.sh --host 127.0.0.1 --port 9000
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

# Check if local python3.11 directory exists
LOCAL_PYTHON_DIR="$SCRIPT_DIR/python3.11"
USE_PYTHON_CMD="python"

if [ -d "$LOCAL_PYTHON_DIR" ]; then
    echo -e "${GREEN}[INFO] Found local Python environment: $LOCAL_PYTHON_DIR${NC}"
    PYTHON_EXE="$LOCAL_PYTHON_DIR/python"
    
    if [ -x "$PYTHON_EXE" ]; then
        echo -e "${GREEN}[INFO] Using local Python: $PYTHON_EXE${NC}"
        USE_PYTHON_CMD="$PYTHON_EXE"
    else
        echo -e "${YELLOW}[WARNING] python not found in local environment, trying conda...${NC}"
        
        # Fallback to conda
        if command -v conda &> /dev/null; then
            echo -e "${YELLOW}[INFO] Activating conda environment: python3.11 ...${NC}"
            # Source conda and activate
            # Try to find conda.sh
            CONDA_SH=$(find ~/.conda ~/anaconda3 ~/miniconda3 /opt/conda /opt/anaconda3 -name "conda.sh" 2>/dev/null | head -1)
            if [ -n "$CONDA_SH" ]; then
                source "$CONDA_SH" activate python3.11
                if [ $? -ne 0 ]; then
                    echo -e "${RED}[ERROR] Failed to activate conda environment${NC}"
                    read -p "Press Enter to exit..."
                    exit 1
                fi
                echo -e "${GREEN}[SUCCESS] Conda environment activated${NC}"
            else
                echo -e "${YELLOW}[INFO] conda.sh not found, trying 'conda activate' directly...${NC}"
                eval "$(conda shell.bash hook)" 2>/dev/null
                conda activate python3.11
                if [ $? -ne 0 ]; then
                    echo -e "${RED}[ERROR] Failed to activate conda environment${NC}"
                    read -p "Press Enter to exit..."
                    exit 1
                fi
                echo -e "${GREEN}[SUCCESS] Conda environment activated${NC}"
            fi
        else
            echo -e "${RED}[ERROR] Neither local Python nor conda found${NC}"
            read -p "Press Enter to exit..."
            exit 1
        fi
    fi
else
    echo -e "${YELLOW}[INFO] Local python3.11 directory not found, using conda...${NC}"
    
    # Check if conda is available
    if ! command -v conda &> /dev/null; then
        echo -e "${RED}[ERROR] conda command not found${NC}"
        read -p "Press Enter to exit..."
        exit 1
    fi
    
    echo -e "${YELLOW}[INFO] Activating conda environment: python3.11 ...${NC}"
    # Source conda and activate
    CONDA_SH=$(find ~/.conda ~/anaconda3 ~/miniconda3 /opt/conda /opt/anaconda3 -name "conda.sh" 2>/dev/null | head -1)
    if [ -n "$CONDA_SH" ]; then
        source "$CONDA_SH" activate python3.11
        if [ $? -ne 0 ]; then
            echo -e "${RED}[ERROR] Failed to activate conda environment${NC}"
            read -p "Press Enter to exit..."
            exit 1
        fi
        echo -e "${GREEN}[SUCCESS] Conda environment activated${NC}"
    else
        echo -e "${YELLOW}[INFO] conda.sh not found, trying 'conda activate' directly...${NC}"
        eval "$(conda shell.bash hook)" 2>/dev/null
        conda activate python3.11
        if [ $? -ne 0 ]; then
            echo -e "${RED}[ERROR] Failed to activate conda environment${NC}"
            read -p "Press Enter to exit..."
            exit 1
        fi
        echo -e "${GREEN}[SUCCESS] Conda environment activated${NC}"
    fi
fi

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
            # Match host: under server: block with any leading whitespace
            sed -i '/^server:/,/^[a-zA-Z]/ s/^[[:space:]]*host:.*/  host: '"$HOST_ADDRESS"'/' config.yaml
            echo -e "${CYAN}  - Set Host: $HOST_ADDRESS${NC}"
        fi
        if [ "$PORT" -ne 0 ]; then
            # Match port: under server: block with any leading whitespace
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