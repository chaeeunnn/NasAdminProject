# user.py
from flask import request, jsonify
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)
from utils.blocklist import BLOCKLIST
from utils.jwt_utils import (
    load_users, save_users, authenticate_user, is_ip_allowed
)
import datetime
from werkzeug.security import generate_password_hash
from utils.logger import get_logger

user_api = Namespace('user', description='USER 연관 API')
logger = get_logger("user") 

login_model = user_api.model('Login', {
    'username': fields.String(required=True, description='사용자 ID'),
    'password': fields.String(required=True, description='비밀번호')
})

register_model = user_api.model('Register', {
    'username': fields.String(required=True, description='등록할 사용자 ID'),
    'password': fields.String(required=True, description='비밀번호')
})

# 로그인
@user_api.route('/login')
class UserLogin(Resource):
    @user_api.doc(description='로그인')
    @user_api.expect(login_model)
    def post(self):
        try:
            data = request.get_json()
            if not data:
                logger.info("로그인 실패 - 요청 데이터 없음")
                return {'error': '요청 데이터가 없습니다.'}, 400

            username = data.get('username')
            password = data.get('password')
            client_ip = request.remote_addr

            if not username or not password:
                logger.info(f"로그인 실패 - 입력 누락 (username: {username}, password: {'있음' if password else '없음'})")
                return {'error': '아이디와 비밀번호를 모두 입력하세요.'}, 400

            logger.info(f"로그인 시도 - 사용자: {username}, IP: {client_ip}")

            if not is_ip_allowed(client_ip):
                logger.info(f"접근 차단 - 허용되지 않은 IP: {client_ip}")
                return {'error': '접근이 허용되지 않은 IP입니다.'}, 403

            if not authenticate_user(username, password):
                logger.info(f"로그인 실패 - 사용자: {username}, 잘못된 아이디 또는 비밀번호")
                return {'error': '잘못된 사용자 이름 또는 비밀번호입니다.'}, 401

            access_token = create_access_token(identity=username, expires_delta=datetime.timedelta(minutes=30))
            refresh_token = create_refresh_token(identity=username)

            logger.info(f"로그인 성공 - 사용자: {username}")

            return {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'expires_in_minutes': 30
            }, 200

        except Exception as e:
            logger.error(f"로그인 처리 중 예외 발생: {e}", exc_info=True)
            return {'error': '서버 내부 오류가 발생했습니다.'}, 500

# 로그아웃
@user_api.route('/logout')
class UserLogout(Resource):
    @user_api.doc(description='로그아웃')
    @jwt_required()
    def post(self):
        try:
            jti = get_jwt()['jti']
            username = get_jwt_identity()
            add_to_blocklist(jti)
            logger.info(f"로그아웃 - 사용자: {username}, 토큰 JTI: {jti}")
            return {'message': '로그아웃 완료'}, 200

        except Exception as e:
            logger.error(f"로그아웃 처리 중 예외 발생: {e}", exc_info=True)
            return {'error': '서버 내부 오류가 발생했습니다.'}, 500

# 로그인 연장 (refresh 토큰 발급)
@user_api.route('/refresh')
class UserTokenRefresh(Resource):
    @user_api.doc(security='refresh_jwt', description='로그인 연장 (refresh 토큰 필요)')
    @jwt_required(refresh=True)
    def post(self):
        try:
            identity = get_jwt_identity()
            new_token = create_access_token(identity=identity, expires_delta=datetime.timedelta(minutes=30))
            logger.info(f"토큰 갱신 - 사용자: {identity}")
            return {
                'access_token': new_token,
                'expires_in_minutes': 60
            }, 200

        except Exception as e:
            logger.error(f"토큰 갱신 중 예외 발생: {e}", exc_info=True)
            return {'error': '서버 내부 오류가 발생했습니다.'}, 500

# 사용자 등록
@user_api.route('/register')
class UserRegister(Resource):
    @user_api.doc(description='사용자 등록')
    @user_api.expect(register_model)
    @jwt_required()
    def post(self):
        try:
            data = request.get_json()
            if not data:
                logger.info("사용자 등록 실패 - 요청 데이터 없음")
                return {'error': '요청 데이터가 없습니다.'}, 400

            username = data.get('username')
            password = data.get('password')

            if not username or not password:
                logger.info(f"사용자 등록 실패 - 입력 누락 (username: {username}, password: {'있음' if password else '없음'})")
                return {'error': '아이디와 비밀번호를 모두 입력하세요.'}, 400

            logger.info(f"사용자 등록 시도 - 사용자: {username}")

            users = load_users()
            if username in users:
                logger.info(f"사용자 등록 실패 - 이미 존재하는 ID: {username}")
                return {'error': '이미 존재하는 사용자 ID입니다.'}, 400

            users[username] = {
                'password': generate_password_hash(password)
            }
            save_users(users)

            logger.info(f"사용자 등록 성공 - 사용자: {username}")
            return {'message': f'사용자 {username} 등록 완료'}, 201

        except Exception as e:
            logger.error(f"사용자 등록 처리 중 예외 발생: {e}", exc_info=True)
            return {'error': '서버 내부 오류가 발생했습니다.'}, 500
