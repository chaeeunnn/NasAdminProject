from flask import request, jsonify
from flask_restx import Namespace, Resource, fields
import subprocess

nfs_api = Namespace('nfs', description='NFS 관리')

# Model 정의
nfs_share_model = nfs_api.model('NFSShare', {
    'zfs_name': fields.String(required=True, description='공유할 ZFS 파일시스템 이름 (ex: poolname/filesystem)'),
    'client_ip': fields.String(required=True, description='공유 대상 클라이언트 IP 주소'),
    'options': fields.String(required=False, description='NFS 공유 옵션 (default: rw,sync,no_root_squash)'),
})

nfs_control_model = nfs_api.model('NFSControl', {
    'zfs_name': fields.String(required=True, description='ZFS 파일시스템 이름'),
    'client_ip': fields.String(required=True, description='클라이언트 IP 주소')
})

# NFS 전체 활성화
@nfs_api.route('/enable')
class NFSEnable(Resource):
    def get(self):
        subprocess.run(['systemctl', 'enable', '--now', 'nfs-server'], check=True)
        return {'message': 'NFS 서버가 활성화되었습니다.'}

# NFS 전체 비활성화
@nfs_api.route('/disable')
class NFSDisable(Resource):
    def get(self):
        subprocess.run(['systemctl', 'disable', '--now', 'nfs-server'], check=True)
        return {'message': 'NFS 서버가 비활성화되었습니다.'}

# 공유 대상 등록
@nfs_api.route('/share')
class NFSShare(Resource):
    @nfs_api.expect(nfs_share_model)
    def post(self):
        data = request.get_json()
        zfs_name = data['zfs_name']
        client_ip = data['client_ip']
        options = data.get('options', 'rw,sync,no_root_squash')

        # exportfs 설정
        export_line = f"/{zfs_name} {client_ip}({options})\n"
        with open('/etc/exports', 'a') as f:
            f.write(export_line)

        subprocess.run(['exportfs', '-ra'], check=True)
        return {'message': f'{zfs_name}가 {client_ip}에 공유되었습니다.'}

# 공유 목록 조회
@nfs_api.route('/share/list')
class SharedList(Resource):
    def get(self):
        result = subprocess.run(['exportfs', '-v'], capture_output=True, encoding='utf-8', check=True)
        return {'shares': result.stdout.strip().split('\n')}

# 공유되어 있는 개수
@nfs_api.route('/share/count')
class ShareCount(Resource):
    def get(self):
        result = subprocess.run(['exportfs'], capture_output=True, encoding='utf-8', check=True)
        lines = result.stdout.strip().split('\n')
        return {'count': len(lines)}

# 상세 조회 (특정 ZFS 기준)
@nfs_api.route('/share/<string:zfs_name>')
class ShareDetail(Resource):
    def get(self, zfs_name):
        result = subprocess.run(['exportfs', '-v'], capture_output=True, encoding='utf-8', check=True)
        lines = result.stdout.strip().split('\n')
        matched = [line for line in lines if zfs_name in line]
        return {'details': matched}

#  공유 비활성화 (unshare)
@nfs_api.route('/unshare')
class NFSUnshare(Resource):
    @nfs_api.expect(nfs_control_model)
    def post(self):
        data = request.get_json()
        zfs_name = data['zfs_name']
        client_ip = data['client_ip']

        # /etc/exports에서 해당 항목 제거
        updated_lines = []
        with open('/etc/exports', 'r') as f:
            for line in f:
                if zfs_name not in line or client_ip not in line:
                    updated_lines.append(line)
        with open('/etc/exports', 'w') as f:
            f.writelines(updated_lines)

        subprocess.run(['exportfs', '-ra'], check=True)
        return {'message': f'{zfs_name}에 대한 {client_ip} 공유가 해제되었습니다.'}
