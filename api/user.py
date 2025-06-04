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

user_api = Namespace('user', description='USER 연관 API')

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
    @user_api.expect(login_model)
    def post(self):
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        client_ip = request.remote_addr

        if not is_ip_allowed(client_ip):
            return {'error': '접근이 허용되지 않은 IP입니다.'}, 403

        if not authenticate_user(username, password):
            return {'error': '잘못된 사용자 이름 또는 비밀번호입니다.'}, 401

        access_token = create_access_token(identity=username, expires_delta=datetime.timedelta(minutes=30))
        refresh_token = create_refresh_token(identity=username)

        return {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_in_minutes': 30
        }, 200

# 로그아웃
@user_api.route('/logout')
class UserLogout(Resource):
    @jwt_required()
    def post(self):
        jti = get_jwt()['jti']
        add_to_blocklist(jti)
        return {'message': '로그아웃 완료'}, 200

# 로그인 연장 (refresh 토큰 발급)
@user_api.route('/refresh')
class UserTokenRefresh(Resource):
    @user_api.doc(security='refresh_jwt')
    @jwt_required(refresh=True)
    def post(self):
        identity = get_jwt_identity()
        new_token = create_access_token(identity=identity, expires_delta=datetime.timedelta(minutes=30))
        return {
            'access_token': new_token,
            'expires_in_minutes': 60
        }, 200

# 사용자 등록
@user_api.route('/register')
class UserRegister(Resource):
    @user_api.expect(register_model)
    @jwt_required()
    def post(self):
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        users = load_users()
        if username in users:
            return {'error': '이미 존재하는 사용자 ID입니다.'}, 400

        users[username] = {
            'password': generate_password_hash(password)
        }
        save_users(users)

        return {'message': f'사용자 {username} 등록 완료'}, 201
