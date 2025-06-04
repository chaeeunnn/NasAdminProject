from flask import request
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import jwt_required
import subprocess
from datetime import datetime

snapshot_api = Namespace('snapshot', description='스냅샷 관련 API')

create_snapshot_model = snapshot_api.model('CreateSnapshot', {
    'pool_name': fields.String(required=True, description='Zpoool 이름'),
    'zfs_name' : fields.String(required=True, description='Zfs 이름'),
})

snapshot_rollback_model = snapshot_api.model('RollbackSnapshot', {
    'snapshot_name': fields.String(required=True, description='롤백할 스냅샷 전체 이름 (예: pool/zfs@20240524-153000)'),
})

snapshot_delete_model = snapshot_api.model('DeleteSnapshot', {
    'snapshot_name': fields.String(required=True, description='삭제할 스냅샷 전체 이름 (예: pool/zfs@20240524-153000)'),
})

# 스냅샷 생성
@snapshot_api.route('/create')
class CreateSnapshot(Resource):
    @snapshot_api.doc(description='스냅샷 생성')
    @jwt_required()
    @snapshot_api.expect(create_snapshot_model)
    def post(self):
        data = request.json
        pool = data.get('pool_name')
        zfs = data.get('zfs_name')
        zfs_full_name = f'{pool}/{zfs}'
        timestamp = datetime.now().strftime('%y%m%d-%H%M%S')
        snapshot_name = f'{zfs_full_name}@{timestamp}'
        
        try:
            result = subprocess.run(['zfs', 'snapshot', snapshot_name], check=True)
            return {
                'message': f'Snapshot 생성 완료: {snapshot_name}',
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }, 201
        except subprocess.CalledProcessError as e:
            return {
                'error': '스냅샷 생성 실패',
                'stderr': e.stderr,
                'returncode': e.returncode
            }, 500

# 스냅샷 목록 조회
@snapshot_api.route('/list')
class ListSnapshots(Resource):
    @snapshot_api.doc(description='스냅샷 목록 조회')
    @jwt_required()
    def get(self):
        try:
            result = subprocess.run(['zfs', 'list', '-t', 'snapshot', '-H', '-o', 'name,used,creation'],
                                    capture_output=True, text=True, check=True)

            lines = result.stdout.strip().split('\n')
            snapshots = []
            for line in lines:
                parts = line.split('\t')
                if len(parts) == 3:
                    snapshots.append({
                        'name': parts[0],
                        'used': parts[1],
                        'creation': parts[2]
                    })

            return {
                'snapshots': snapshots,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except subprocess.CalledProcessError as e:
            return {
                'error': '스냅샷 목록 조회 실패',
                'stderr': e.stderr,
                'returncode': e.returncode
            }, 500

# 스냅샷 롤백
@snapshot_api.route('/rollback')
class RollbackSnapshot(Resource):
    @snapshot_api.doc(description='스냅샷 롤백')
    @jwt_required()
    @snapshot_api.expect(snapshot_rollback_model)
    def post(self):
        data = request.get_json()
        snapshot_name = data['snapshot_name']

        try:
            result = subprocess.run(['zfs', 'rollback', '-r', snapshot_name],
                                    capture_output=True, text=True, check=True)
            return {
                'message': f'롤백 완료: {snapshot_name}',
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except subprocess.CalledProcessError as e:
            return {
                'error': f'롤백 실패: {snapshot_name}',
                'stderr': e.stderr,
                'returncode': e.returncode
            }, 500

# 스냅샷 삭제
@snapshot_api.route('/delete')
class DeleteSnapshot(Resource):
    @snapshot_api.doc(description='스냅샷 삭제')
    @jwt_required()
    @snapshot_api.expect(snapshot_delete_model)
    def delete(self):
        data = request.get_json()
        snapshot_name = data['snapshot_name']

        try:
            result = subprocess.run(
                ['zfs', 'destroy', snapshot_name],
                capture_output=True,
                text=True,
                check=True
            )

            return {
                'message': f'Snapshot {snapshot_name} deleted successfully',
                'stdout': result.stdout.strip(),
                'stderr': result.stderr.strip(),
                'returncode': result.returncode
            }, 200

        except subprocess.CalledProcessError as e:
            return {
                'error': f'Failed to delete snapshot {snapshot_name}',
                'stdout': e.stdout,
                'stderr': e.stderr,
                'returncode': e.returncode
            }, 500