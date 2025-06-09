from flask import request, jsonify
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import jwt_required
import subprocess, os

nfs_api = Namespace('nfs', description='NFS 관리')

def is_zfs_exists(zfs_name: str) -> bool:
    result = subprocess.run(['zfs', 'list', '-H', '-o', 'name'], capture_output=True, text=True)
    return zfs_name in result.stdout.split()

def is_already_shared(zfs_name: str, client_ip: str) -> bool:
    try:
        with open('/etc/exports', 'r') as f:
            for line in f:
                if zfs_name in line and client_ip in line:
                    return True
        return False
    except FileNotFoundError:
        return False

# Model 정의
nfs_share_model = nfs_api.model('NFSShare', {
    'zfs_name': fields.String(required=True, description='공유할 ZFS 파일시스템 이름 (ex: poolname/filesystem)'),
    'client_ip': fields.String(required=True, description='공유 대상 클라이언트 IP 주소'),
    'options': fields.String(required=False, description='NFS 공유 옵션 (default: rw,sync,no_root_squash)'),
})

nfs_control_model = nfs_api.model('NFSControl', {
    'zfs_name': fields.String(required=True, description='ZFS 파일시스템 이름 (ex: poolname/filesystem)'),
    'client_ip': fields.String(required=True, description='클라이언트 IP 주소')
})

nfs_list_model = nfs_api.model('NFSList', {
    'zfs_name': fields.String(required=True, description='ZFS 파일시스템 이름 (ex: poolname/filesystem)')
})

# NFS 활성화되어있는지 확인
@nfs_api.route('/status')
class NFSStatus(Resource):
    @nfs_api.doc(description='NFS 활성화 확인')
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
                status = "active"
            else:
                status = "inactive"

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
    @nfs_api.doc(description='NFS 활성화')
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
    @nfs_api.doc(description='NFS 비활성화')
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
    @nfs_api.doc(description='공유 대상 등록')
    @jwt_required()
    @nfs_api.expect(nfs_share_model)
    def post(self):
        data = request.get_json()
        zfs_name = data['zfs_name']
        client_ip = data['client_ip']
        options = data.get('options', 'rw,sync,no_root_squash')

        if not zfs_name or not client_ip:
            return {'error': 'zfs_name과 client_ip는 필수 항목입니다.'}, 400

        if not is_zfs_exists(zfs_name):
            return {'error': f'존재하지 않는 ZFS 파일시스템입니다: {zfs_name}'}, 404

        if is_already_shared(zfs_name, client_ip):
            return {'error': f'이미 공유된 대상입니다: {zfs_name} -> {client_ip}'}, 409

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
    @nfs_api.doc(description='모든 공유 목록 조회')
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

# 특정 ZFS 기준 공유 목록 조회
@nfs_api.route('/share/list')
class ShareDetail(Resource):
    @nfs_api.doc(description='특정 ZFS 기준 공유 목록 조회')
    @nfs_api.expect(nfs_list_model)
    @jwt_required()
    def post(self):
        data = request.get_json()
        zfs_name = data.get('zfs_name')

        if not zfs_name:
            return {'error': 'zfs_name은 필수 항목입니다.'}, 400

        if not is_zfs_exists(zfs_name):
            return {'error': f'존재하지 않는 ZFS 파일시스템입니다: {zfs_name}'}, 404

        try:
            result = subprocess.run(['exportfs', '-v'], capture_output=True, encoding='utf-8', check=True)
            lines = result.stdout.strip().split('\n')
            shares = []

            expected_path = f'/{zfs_name}'

            for line in lines:
                if '(' in line and ')' in line:
                    share = line.split()
                    path = share[0]

                    if path != expected_path:
                        continue 

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
                'zfs_name': zfs_name,
                'details': shares,
                'count': len(shares)
            }

        except subprocess.CalledProcessError as e:
            return {
                'error': 'NFS 공유 목록 조회 중 오류가 발생했습니다.',
                'stderr': e.stderr or str(e)
            }, 500


# 공유 비활성화 (unshare)
@nfs_api.route('/unshare')
class NFSUnshare(Resource):
    @nfs_api.doc(description='공유 비활성화')
    @jwt_required()
    @nfs_api.expect(nfs_control_model)
    def post(self):
        data = request.get_json()
        zfs_name = data['zfs_name']
        client_ip = data['client_ip']

        if not zfs_name or not client_ip:
            return {'error': 'zfs_name과 client_ip는 필수 항목입니다.'}, 400

        if not is_zfs_exists(zfs_name):
            return {'error': f'존재하지 않는 ZFS 파일시스템입니다: {zfs_name}'}, 404

        # /etc/exports에서 해당 항목 제거
        found = False
        updated_lines = []
        with open('/etc/exports', 'r') as f:
            for line in f:
                if zfs_name in line and client_ip in line:
                    found = True
                    continue
                updated_lines.append(line)

        if not found:
            return {'error': f'{zfs_name}의 {client_ip} 공유 항목을 찾을 수 없습니다.'}, 404

        with open('/etc/exports', 'w') as f:
            f.writelines(updated_lines)

        subprocess.run(['exportfs', '-ra'], check=True)
        return {'message': f'{zfs_name}에 대한 {client_ip} 공유가 해제되었습니다.'}, 200
