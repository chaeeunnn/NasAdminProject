from flask import Flask
from flask_restx import Api
from api.zpool import zpool_api
# from api.zfs import zfs_api
from api.nfs import nfs_api
# from api.user import user_api

app = Flask(__name__)
# Api 인스턴스 생성
api = Api(app, version='1.0', title='NAS 관리자 API', description='ZFS/NFS 기반 NAS 관리')

api.add_namespace(zpool_api, path='/zpool')
# api.add_namespace(zfs_api, path='/zfs')
api.add_namespace(nfs_api, path='/nfs')
# api.add_namespace(user_api, path='/user')


if __name__ == '__main__':
    app.run(debug=True, port=5000)