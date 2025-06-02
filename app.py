from flask import Flask
from flask_restx import Api
from api.zpool import zpool_api
from api.zfs import zfs_api
from api.nfs import nfs_api
from api.snapshot import snapshot_api
from api.user import user_api
from flask_jwt_extended import JWTManager
from datetime import timedelta

app = Flask(__name__)

jwt = JWTManager(app)

app.config['JWT_SECRET_KEY'] = 'your-secret-key'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(minutes=30)
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(hours=1)
app.config['ALLOWED_IP_RANGES'] = ['192.168.20.0/24','192.168.20.0/24','192.168.50.0/24','127.0.0.1/32']

# Api 인스턴스 생성
authorizations = {
    'jwt': {
        'type': 'apiKey',
        'in': 'header',
        'name': 'Authorization',
        'description': "JWT Authorization header using the Bearer scheme. Example: 'Bearer {token}'"
    }
}

api = Api(app,
          version='1.0',
          title='NAS 관리자 API',
          description='ZFS/NFS 기반 NAS 관리',
          authorizations=authorizations,
          security='jwt'  # 기본 적용할 보안 스키마명
)

api.add_namespace(zpool_api, path='/zpool')
api.add_namespace(zfs_api, path='/zfs')
api.add_namespace(nfs_api, path='/nfs')
api.add_namespace(snapshot_api, path='/snapshot')
api.add_namespace(user_api, path='/user')

if __name__ == '__main__':
    app.run(debug=True, port=5000)