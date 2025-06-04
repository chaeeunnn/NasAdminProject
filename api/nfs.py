from flask import request, jsonify
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import jwt_required
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

# NFS 활성화되어있는지 확인
@nfs_api.route('/status')
class NFSStatus(Resource):
    @jwt_required()
    def get(self):
        try:
            result = subprocess.run(
                ['systemctl', '-l', 'status', 'nfs-server'],
                capture_output=True,
                encoding='utf-8',
                check=True
            )
            # 출력에서 활성화 상태 추출
            if "Active: active (exited)" in result.stdout:
                status = "running"
            else:
                status = "not running"

            return {
                'nfs_status': status,
                'detail': result.stdout.strip().split('\n')
            }, 200

        except subprocess.CalledProcessError as e:
            return {
                'nfs_status': 'error',
                'detail': e.stderr or str(e)
            }, 500

# NFS 전체 활성화
@nfs_api.route('/enable')
class NFSEnable(Resource):
    @jwt_required()
    def get(self):
        try:
            subprocess.run(['systemctl', 'enable', '--now', 'nfs-server'], check=True)
            return {'message': 'NFS 서버가 활성화되었습니다.'}
        except subprocess.CalledProcessError as e:
            return {
                'message': 'NFS 서버 활성화에 실패하였습니다.',
                'stderr': e.stderr,
            }, 500

# NFS 전체 비활성화
@nfs_api.route('/disable')
class NFSDisable(Resource):
    @jwt_required()
    def get(self):
        try:
            subprocess.run(['systemctl', 'disable', '--now', 'nfs-server'], check=True)
            return {'message': 'NFS 서버가 비활성화되었습니다.'}
        except subprocess.CalledProcessError as e:
            return {
                'message': 'NFS 서버 비활성화에 실패하였습니다.',
                'stderr': e.stderr,
            }, 500

# 공유 대상 등록
@nfs_api.route('/share')
class NFSShare(Resource):
    @jwt_required()
    @nfs_api.expect(nfs_share_model)
    def post(self):
        data = request.get_json()
        zfs_name = data['zfs_name']
        client_ip = data['client_ip']
        options = data.get('options', 'rw,sync,no_root_squash')

        try:
            # exportfs 설정
            export_line = f"/{zfs_name} {client_ip}({options})\n"
            with open('/etc/exports', 'a') as f:
                f.write(export_line)

            subprocess.run(['exportfs', '-ra'], check=True)
            return {'message': f'{zfs_name}가 {client_ip}에 공유되었습니다.'}
        except subprocess.CalledProcessError as e:
            return {
                'message': '공유 대상 등록에 실패하였습니다.',
                'stderr': e.stderr,
            }, 500

# 공유 목록 조회
@nfs_api.route('/share/list')
class SharedList(Resource):
    @jwt_required()
    def get(self):
        try:
            result = subprocess.run(['exportfs', '-v'], capture_output=True, encoding='utf-8', check=True)
            lines = [line for line in result.stdout.strip().split('\n') if line.strip()]
            shares = []
            for line in lines:
                if '(' in line and ')' in line:
                    # 공유 디렉토리 경로 추출
                    share = line.split()
                    path = share[0]
                    
                    # client(ip)와 옵션 추출
                    client_part = ' '.join(share[1:])
                    client, options_str = client_part.split('(')
                    client = client.strip()
                    options = options_str.strip(')').split(',')
                    
                    shares.append({
                        'path': path,
                        'client': client,
                        'options': options
                    })
            return {
                'shares': shares,
                'count': len(shares)}
        except subprocess.CalledProcessError as e:
            return {
                'message': '공유 목록 조회에 실패하였습니다.',
                'stderr': e.stderr,
            }, 500

# 상세 조회 (특정 ZFS 기준)
@nfs_api.route('/share/<string:zpool_name>/<string:zfs_name>')
class ShareDetail(Resource):
    @jwt_required()
    def get(self, zpool_name, zfs_name):
        full_name = f'{zpool_name}/{zfs_name}'
        result = subprocess.run(['exportfs', '-v'], capture_output=True, encoding='utf-8', check=True)
        lines = result.stdout.strip().split('\n')
        matched = [line for line in lines if full_name in line]
        return {
            'details': matched,
            'count': len(matched)}

#  공유 비활성화 (unshare)
@nfs_api.route('/unshare')
class NFSUnshare(Resource):
    @jwt_required()
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