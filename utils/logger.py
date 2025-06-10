import logging
from logging.handlers import RotatingFileHandler
import os
from flask_jwt_extended import get_jwt_identity, jwt_required
from functools import wraps

LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

class UserContextFilter(logging.Filter):
    """사용자 정보를 로그에 추가하는 필터"""
    def filter(self, record):
        try:
            # JWT에서 사용자 ID 추출 시도
            user_id = get_jwt_identity()
            record.user_id = f"[{user_id}]" if user_id else "[anonymous]"
        except:
            # JWT 컨텍스트가 없는 경우 (예: 시스템 로그)
            record.user_id = "[system]"
        return True

def get_logger(name):
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger  # 이미 설정된 경우 재사용
    
    logger.setLevel(logging.INFO)  # 로그 레벨 info로 설정
    
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, f"{name}.log"),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    
    # 사용자 정보를 포함한 포맷터
    formatter = logging.Formatter("[%(asctime)s] %(user_id)s %(levelname)s: %(message)s")
    file_handler.setFormatter(formatter)
    
    # 사용자 컨텍스트 필터 추가
    user_filter = UserContextFilter()
    file_handler.addFilter(user_filter)
    
    logger.addHandler(file_handler)
    return logger