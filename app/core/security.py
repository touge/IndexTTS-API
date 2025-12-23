"""
API 安全认证模块
提供 Bearer Token 认证功能
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.utils.yaml_config_loader import yaml_config_loader
import logging

logger = logging.getLogger(__name__)

# HTTP Bearer 认证方案
security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    验证 Bearer Token
    
    从 config.yaml 中读取配置的 token 并进行验证。
    如果 token 未配置或为空，则跳过验证（开发模式）。
    
    Args:
        credentials: FastAPI 自动注入的认证凭据
        
    Returns:
        str: 验证通过的 token
        
    Raises:
        HTTPException: Token 无效或缺失时抛出 401 错误
    """
    # 从配置文件读取 token
    configured_token = yaml_config_loader.get('api.token')
    
    # 如果未配置 token，跳过验证（开发模式）
    if not configured_token:
        logger.warning("API token not configured, authentication disabled")
        return None
    
    # 验证 token
    if credentials.scheme != "Bearer" or credentials.credentials != configured_token:
        logger.warning(f"Invalid token attempt: {credentials.credentials[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.debug("Token verification successful")
    return credentials.credentials
