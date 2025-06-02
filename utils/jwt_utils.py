import json
import os
from flask_jwt_extended import create_access_token
from werkzeug.security import check_password_hash
from flask import current_app

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
    allowed_ranges = current_app.config.get('ALLOWED_IP_RANGES', ['192.168.20.0/24','192.168.25.0/24'])
    import ipaddress
    client_ip = ipaddress.ip_address(ip)
    for cidr in allowed_ranges:
        if client_ip in ipaddress.ip_network(cidr):
            return True
    return False

# 로그아웃 시 폐기된 토큰 정보를 담은 파일 경로 (JTI 기반)
REVOKED_TOKENS_FILE = os.path.join(os.path.dirname(__file__), '../data/revoked_tokens.json')

# 폐기된 JWT JTI 리스트 로드
def _load_revoked_tokens():
    if not os.path.exists(REVOKED_TOKENS_FILE):
        return set()
    with open(REVOKED_TOKENS_FILE, 'r') as f:
        return set(json.load(f))

# JTI 리스트를 JSON으로 저장
def _save_revoked_tokens(revoked_tokens):
    with open(REVOKED_TOKENS_FILE, 'w') as f:
        json.dump(list(revoked_tokens), f, indent=2)

# JWT 토큰의 jti를 폐기 목록에 추가
def mark_token_as_revoked(jti):
    revoked_tokens = _load_revoked_tokens()
    revoked_tokens.add(jti)
    _save_revoked_tokens(revoked_tokens)

# 주어진 jti가 폐기된 토큰인지 확인
def is_token_revoked(jti):
    revoked_tokens = _load_revoked_tokens()
    return jti in revoked_tokens

# refresh 토큰을 통해 access_token을 갱신
def refresh_access_token(identity):
    expires = current_app.config.get("JWT_REFRESH_TOKEN_EXPIRES", 3600)
    access_token = create_access_token(identity=identity, expires_delta=expires)
    return access_token