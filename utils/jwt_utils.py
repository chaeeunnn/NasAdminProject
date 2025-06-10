import json
import os
from flask_jwt_extended import JWTManager, create_access_token
from utils.blocklist import BLOCKLIST, add_to_blocklist
from werkzeug.security import check_password_hash
from flask import current_app, jsonify
from utils.logger import get_logger
from dotenv import load_dotenv

logger = get_logger("user")
jwt = JWTManager()
load_dotenv()

def configure_jwt(app):
  app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")

  # 토큰 만료시간
  freshness_in_minutes = 1
  app.config["JWT_ACCESS_TOKEN_EXPIRES"] = freshness_in_minutes * 30 # 30분
  jwt.init_app(app)
  logger.info("JWT 설정 완료 - 시크릿 키 및 만료 시간 설정")

# 사용자 정보가 담긴 파일 경로
USERS_FILE = os.path.join(os.path.dirname(__file__), '../data/users.json')

# 사용자 정보 로딩
def load_users():
    if not os.path.exists(USERS_FILE):
        logger.warning(f"사용자 정보 파일 없음 - 경로: {USERS_FILE}")
        return {}
    try:
        with open(USERS_FILE, 'r') as f:
            users = json.load(f)
            logger.info(f"사용자 정보 로딩 성공 - 사용자 수: {len(users)}")
            return users
    except Exception as e:
        logger.error(f"사용자 정보 로딩 실패 - 경로: {USERS_FILE}, 오류: {str(e)}", exc_info=True)
        return {}


# 사용자 정보 저장
def save_users(users):
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=2)
        logger.info(f"사용자 정보 저장 성공 - 사용자 수: {len(users)}")
    except Exception as e:
        logger.error(f"사용자 정보 저장 실패 - 경로: {USERS_FILE}, 오류: {str(e)}", exc_info=True)

# 사용자 인증
def authenticate_user(username, password):
    users = load_users()
    user = users.get(username)
    if not user:
        logger.warning(f"인증 실패 - 사용자 없음: {username}")
        return False
    if check_password_hash(user['password'], password):
        logger.info(f"인증 성공 - 사용자: {username}")
        return True
    else:
        logger.warning(f"인증 실패 - 비밀번호 불일치: {username}")
        return False

# IP가 허용된 대역인지 확인인
def is_ip_allowed(ip):
    allowed_ranges = current_app.config.get('ALLOWED_IP_RANGES', ['192.168.20.0/24','192.168.25.0/24','127.0.0.1/32'])
    import ipaddress
    try:
        client_ip = ipaddress.ip_address(ip)
        for cidr in allowed_ranges:
            if client_ip in ipaddress.ip_network(cidr):
                logger.info(f"허용된 IP 접근 - IP: {ip}, 허용 대역: {cidr}")
                return True
        logger.warning(f"차단된 IP 접근 시도 - IP: {ip}")
        return False
    except ValueError as e:
        logger.error(f"IP 형식 오류 - 입력값: {ip}, 오류: {str(e)}", exc_info=True)
        return False
    
# 토큰이 블록리스트에 있는지 확인하는 함수
# 블록리스트에 있으면 해당 토큰이 유효하지 않다고 판단
@jwt.token_in_blocklist_loader
def check_if_token_in_blocklist(jwt_header, jwt_payload):
    # jti=jwt id
    in_blocklist = jwt_payload["jti"] in BLOCKLIST
    logger.debug(f"토큰 블록리스트 확인 - JTI: {jti}, 차단 여부: {in_blocklist}")
    return in_blocklist

# 만료된 토큰이 사용되었을 때 실행되는 함수
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    logger.warning(f"만료된 토큰 사용 - JTI: {jwt_payload.get('jti')}")
    return jsonify({"msg": "Token expired", "error": "token_expired"}), 401

# 유효하지 않은 토큰이 사용되었을 때 실행되는 함수
# 토큰의 서명이나 구조가 유효하지 않을 때 실행됩니다. 주로 토큰 자체의 문제로 발생하는 경우에 해당합니다.
@jwt.invalid_token_loader
def invalid_token_callback(error):
    logger.warning(f"유효하지 않은 토큰 사용 - 오류: {error}")
    return (
        jsonify(
            {"message": "Invalid token", "error": "invalid_token"}
        ),
        401,
    )

# 해당 토큰으로 접근 권한이 없는 경우
@jwt.unauthorized_loader
def missing_token_callback(error):
    logger.warning(f"토큰 누락 - 오류: {error}")
    return (
        jsonify(
            {
                "description": "Access token required",
                "error": "access_token_required",
            }
        ),
        401,
    )

# fresh한 토큰이 필요한데 fresh하지 않은 토큰이 사용되었을 때
# 해당 응답을 반환하여 fresh한 토큰이 필요하다는 메시지를 전달
# JWT_ACCESS_TOKEN_EXPIRES으로 토큰 만료 시간 조정
@jwt.needs_fresh_token_loader
def token_not_fresh_callback(jwt_header, jwt_payload):
    logger.warning(f"Fresh 토큰 아님 - JTI: {jwt_payload.get('jti')}")
    return (
        jsonify(
            {"description": "Token is not fresh.", "error": "fresh_token_required"}
        ),
        401,
    )

# 토큰이 폐기되었을 때 실행되는 함수를
@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    logger.warning(f"폐기된 토큰 사용 - JTI: {jwt_payload.get('jti')}")
    return (
        jsonify(
            {"description": "Token has been revoked.", "error": "token_revoked"}
        ),
        401,
    )