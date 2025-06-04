import json
import os
from flask_jwt_extended import JWTManager, create_access_token
from utils.blocklist import BLOCKLIST, add_to_blocklist
from werkzeug.security import check_password_hash
from flask import current_app, jsonify

jwt = JWTManager()

def configure_jwt(app):
  app.config["JWT_SECRET_KEY"] = "your-secret-key"

  # 토큰 만료시간
  freshness_in_minutes = 1
  app.config["JWT_ACCESS_TOKEN_EXPIRES"] = freshness_in_minutes * 30 # 30분
  jwt.init_app(app)

# 사용자 정보가 담긴 파일 경로
USERS_FILE = os.path.join(os.path.dirname(__file__), '../data/users.json')

# 사용자 정보 로딩
def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, 'r') as f:
        return json.load(f)

# 사용자 정보 저장
def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

# 사용자 인증
def authenticate_user(username, password):
    users = load_users()
    user = users.get(username) # username에 해당하는 사용자가 있고,
    if not user:
        return False
    return check_password_hash(user['password'], password) # 비밀번호 해시가 일치하면 인증 성공

# IP가 허용된 대역인지 확인인
def is_ip_allowed(ip):
    allowed_ranges = current_app.config.get('ALLOWED_IP_RANGES', ['192.168.20.0/24','192.168.25.0/24','127.0.0.1/32'])
    import ipaddress
    client_ip = ipaddress.ip_address(ip)
    for cidr in allowed_ranges:
        if client_ip in ipaddress.ip_network(cidr):
            return True
    return False


# 추가적인 정보를 토큰에 넣고 싶을 때 사용
@jwt.additional_claims_loader # @데코레이터
def add_claims_to_jwt(identity):
    if identity == 1:
        return {"is_admin": True}
    return {"is_admin": False}
    
# 토큰이 블록리스트에 있는지 확인하는 함수
# 블록리스트에 있으면 해당 토큰이 유효하지 않다고 판단
@jwt.token_in_blocklist_loader
def check_if_token_in_blocklist(jwt_header, jwt_payload):
    # jti=jwt id
    return jwt_payload["jti"] in BLOCKLIST

# 만료된 토큰이 사용되었을 때 실행되는 함수
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({"msg": "Token expired", "error": "token_expired"}), 401

# 유효하지 않은 토큰이 사용되었을 때 실행되는 함수
# 토큰의 서명이나 구조가 유효하지 않을 때 실행됩니다. 주로 토큰 자체의 문제로 발생하는 경우에 해당합니다.
@jwt.invalid_token_loader
def invalid_token_callback(error):
    return (
        jsonify(
            {"message": "Invalid token", "error": "invalid_token"}
        ),
        401,
    )

# 해당 토큰으로 접근 권한이 없는 경우
@jwt.unauthorized_loader
def missing_token_callback(error):
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
    return (
        jsonify(
            {"description": "Token is not fresh.", "error": "fresh_token_required"}
        ),
        401,
    )

# 토큰이 폐기되었을 때 실행되는 함수를
@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    return (
        jsonify(
            {"description": "Token has been revoked.", "error": "token_revoked"}
        ),
        401,
    )