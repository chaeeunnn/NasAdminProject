from flask import request
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import jwt_required
import subprocess

zfs_api = Namespace('zfs', description='ZFS 관련 API')

get_zfs_model = zfs_api.model('ZFSList', {
    'pool_name': fields.String(required=True, description='Zpoool 이름'),
    'zfs_name' : fields.String(required=True, description='Zfs 이름'),
})

create_zfs_model = zfs_api.model('CreateZFS', {
    'pool_name': fields.String(required=True, description='Zpool 이름'),
    'zfs_name': fields.String(required=True, description='ZFS 파일시스템 이름'),
    'quota': fields.String(required=False, description='용량 제한 (예: 2G, 500M)'),
    'compression': fields.String(required=False, description='압축 설정 (예: on, off, lz4)'),
    'readonly': fields.String(required=False, description='읽기전용 여부 (예: on, off)'),
    'mountpoint': fields.String(required=False, description='마운트 지점 (예: /my/zfs)'),
})

# zfs 전체 조회
@zfs_api.route('/list')
class ZFS_list(Resource):
    @zfs_api.doc(description='zfs 전체 조회')
    @jwt_required()
    def get(self):
        columns = ['NAME', 'USED', 'AVAIL', 'REFER', 'MOUNTPOINT']
        result = subprocess.run(['zfs', 'list', '-H', '-o', 'name,used,avail,refer,mountpoint'], capture_output=True, encoding='utf-8')
        lines = result.stdout.strip().split('\n')

        zfs_list = []
        for line in lines:
            values = line.split('\t')
            zfs_list.append(dict(zip(columns, values)))

        response = {
            'zfs': zfs_list,
            'stderr': result.stderr,
            'returncode': result.returncode
        }
        
        return response

# zfs 상세 조회 (속성)
@zfs_api.route('/properties')
class ZFS_Status(Resource):
    @zfs_api.doc(description='zfs 속성 조회')
    @jwt_required()
    @zfs_api.expect(get_zfs_model)
    def post(self):
        data = request.get_json()

        if not data:
            return {'error': 'No input data provided'}, 400
        
        pool_name = data.get('pool_name')
        zfs_name = data.get('zfs_name')
        
        key_props = [
            "type", "creation", "used", "available", "referenced", "mounted", "mountpoint",
            "compression", "quota", "readonly", "sharenfs", "checksum", "atime", "recordsize", "refreservation"
        ]

        cmd = ["zfs", "get", ",".join(key_props), f'{pool_name}/{zfs_name}']
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)

            lines = result.stdout.strip().split("\n")
            # 첫 줄은 헤더이므로 제외하고 파싱
            response = []
            for line in lines[1:]:
                parts = line.split(None, 3)  # 최대 4개 컬럼 분리
                if len(parts) == 4:
                    name, prop, value, source = parts
                    response.append({prop: value})
                
            response = {
                'zfs': response,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        
            return response
        except subprocess.CalledProcessError as e:
            return {'error': str(e)}, 500

# zfs 생성
@zfs_api.route('/create')
class ZFSCreate(Resource):
    @zfs_api.doc(description='zfs 생성')
    @jwt_required()
    @zfs_api.expect(create_zfs_model)
    def post(self):
        data = request.json
        pool = data.get('pool_name')
        zfs = data.get('zfs_name')
        full_name = f"{pool}/{zfs}"

        try:
            # 중복 여부 확인
            check = subprocess.run(['zfs', 'list', full_name], capture_output=True, text=True)
            if check.returncode == 0:
                return {'error': f'ZFS {full_name} already exists'}, 409
            
            # 1. 파일시스템 생성
            subprocess.run(['zfs', 'create', full_name], check=True)

            # 2. 권한 설정 (기본값: 775)
            mount_path = f"/{full_name}"
            subprocess.run(['chmod', '775', mount_path], check=True)

            # 3. 속성 설정 (있을 때만)
            if data.get('quota'):
                subprocess.run(['zfs', 'set', f"quota={data['quota']}G", full_name], check=True)
            if data.get('compression'):
                subprocess.run(['zfs', 'set', f"compression={data['compression']}", full_name], check=True)
            if data.get('readonly'):
                subprocess.run(['zfs', 'set', f"readonly={data['readonly']}", full_name], check=True)
            if data.get('mountpoint'):
                subprocess.run(['zfs', 'set', f"mountpoint={data['mountpoint']}", full_name], check=True)

            return {
                'message': f'{full_name} 생성 및 설정 완료'
                }, 201

        except subprocess.CalledProcessError as e:
            return {'error': str(e)}, 500

# zfs 삭제
@zfs_api.route('/delete/<pool_name>/<zfs_name>')
class DeleteZFS(Resource):
    @zfs_api.doc(description='zfs 삭제')
    @jwt_required()
    def delete(self, pool_name, zfs_name):
        full_name = f'{pool_name}/{zfs_name}'
        try:
            result = subprocess.run(
                ['zfs', 'destroy', full_name],
                capture_output=True,
                encoding='utf-8',
                check=True
            )
            
            return {
                'message': f'ZFS: {full_name} deleted successfully',
                'stdout': result.stdout.strip().split('\n'),
                'stderr': result.stderr,
                'returncode': result.returncode
            }
            
        except subprocess.CalledProcessError as e:
            return {
                'error': f'Failed to delete ZFS {full_name}',
                'stdout': e.stdout,
                'stderr': e.stderr,
                'returncode': e.returncode
            }, 500