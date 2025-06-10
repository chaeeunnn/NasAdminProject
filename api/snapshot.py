from flask import request
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import jwt_required
from utils.zpool_utils import is_pool_name_exists
import subprocess, re
from datetime import datetime
from utils.logger import get_logger

snapshot_api = Namespace('snapshot', description='스냅샷 관련 API')
logger = get_logger("snapshot")

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
        logger.info("스냅샷 생성 요청 시작")
        data = request.json
        pool_name = data.get('pool_name')
        zfs_name = data.get('zfs_name')
        full_name = f'{pool_name}/{zfs_name}'
        timestamp = datetime.now().strftime('%y%m%d-%H%M%S')
        snapshot_name = f'{full_name}@{timestamp}'
        
        try:
            # 존재하는 pool인지 확인
            if not is_pool_name_exists(pool_name):
                logger.warning(f"존재하지 않는 pool 요청: {pool_name}")
                return {'error': f'해당 pool을 찾을 수 없습니다. : {pool_name}'}
            # 존재하는 zfs인지 확인
            check = subprocess.run(['zfs', 'list', full_name], capture_output=True, text=True)
            if check.returncode != 0:
                logger.warning(f"존재하지 않는 ZFS 요청: {full_name}, stderr: {check.stderr.strip()}")
                return {'error': f'해당 ZFS를 찾을 수 없습니다. : {full_name}', 'stderr':check.stderr}, 400

            result = subprocess.run(['zfs', 'snapshot', snapshot_name], check=True)
            logger.info(f"스냅샷 생성 성공: {snapshot_name}")
            return {
                'message': f'Snapshot 생성 완료: {snapshot_name}',
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }, 201
        except subprocess.CalledProcessError as e:
            logger.error(f"스냅샷 생성 실패: {snapshot_name}, stderr: {e.stderr}", exc_info=True)
            return {
                'error': '스냅샷 생성 실패',
                'stderr': e.stderr,
                'returncode': e.returncode
            }, 500
        except Exception as e:
            logger.error(f"스냅샷 생성 중 예외 발생: {str(e)}", exc_info=True)
            return {'error': '서버 내부 오류가 발생했습니다.'}, 500

# 스냅샷 목록 조회
@snapshot_api.route('/list')
class ListSnapshots(Resource):
    @snapshot_api.doc(description='스냅샷 목록 조회')
    @jwt_required()
    def get(self):
        logger.info("스냅샷 목록 조회 요청 시작")
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
            logger.info(f"스냅샷 목록 조회 성공: {len(snapshots)}개")
            return {
                'snapshots': snapshots,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except subprocess.CalledProcessError as e:
            logger.error(f"스냅샷 목록 조회 실패: stderr: {e.stderr}", exc_info=True)
            return {
                'error': '스냅샷 목록 조회 실패',
                'stderr': e.stderr,
                'returncode': e.returncode
            }, 500
        except Exception as e:
            logger.error(f"스냅샷 목록 조회 중 예외 발생: {str(e)}", exc_info=True)
            return {'error': '서버 내부 오류가 발생했습니다.'}, 500

# 스냅샷 롤백
@snapshot_api.route('/rollback')
class RollbackSnapshot(Resource):
    @snapshot_api.doc(description='스냅샷 롤백')
    @jwt_required()
    @snapshot_api.expect(snapshot_rollback_model)
    def post(self):
        logger.info("스냅샷 롤백 요청 시작")
        data = request.get_json()
        snapshot_name = data['snapshot_name']

        # pool/zfs@snapshot 형식 검증 및 분리
        match = re.match(r'^([\w\-./]+)@([\w\-]+)$', snapshot_name)
        if not match:
            logger.warning(f"잘못된 스냅샷 이름 형식 요청: {snapshot_name}")
            return {'error': '스냅샷 이름 형식이 잘못되었습니다. 예: pool/zfs@20240609-153000'}, 400

        zfs_full_name = match.group(1)
        pool_name = zfs_full_name.split('/')[0]

        try:
            # pool 존재 확인
            if not is_pool_name_exists(pool_name):
                logger.warning(f"존재하지 않는 pool 롤백 요청: {pool_name}")
                return {'error': f'해당 pool을 찾을 수 없습니다: {pool_name}'}, 400

            # zfs 존재 여부 확인
            check = subprocess.run(['zfs', 'list', zfs_full_name], capture_output=True, text=True)
            if check.returncode != 0:
                logger.warning(f"존재하지 않는 ZFS 롤백 요청: {zfs_full_name}")
                return {'error': f'ZFS 파일시스템이 존재하지 않습니다: {zfs_full_name}'}, 400

            # 스냅샷 존재 여부 확인
            snapshot_check = subprocess.run(
                ['zfs', 'list', '-t', 'snapshot', '-H', '-o', 'name'],
                capture_output=True, text=True
            )
            snapshot_names = snapshot_check.stdout.strip().split('\n')
            if snapshot_name not in snapshot_names:
                # 해당 ZFS의 스냅샷 목록 필터링
                related = [s for s in snapshot_names if s.startswith(f'{zfs_full_name}@')]
                logger.warning(f"존재하지 않는 스냅샷 롤백 요청: {snapshot_name}")
                return {
                    'error': f'해당 스냅샷이 존재하지 않습니다: {snapshot_name}',
                    '해당 ZFS의 스냅샷 목록': related
                }, 404
            
            # 롤백
            result = subprocess.run(['zfs', 'rollback', '-r', snapshot_name],
                                    capture_output=True, text=True, check=True)
            logger.info(f"스냅샷 롤백 성공: {snapshot_name}")
            return {
                'message': f'롤백 완료: {snapshot_name}',
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except subprocess.CalledProcessError as e:
            logger.error(f"스냅샷 롤백 실패: {snapshot_name}, stderr: {e.stderr}", exc_info=True)
            return {
                'error': f'롤백 실패: {snapshot_name}',
                'stderr': e.stderr,
                'returncode': e.returncode
            }, 500
        except Exception as e:
            logger.error(f"스냅샷 롤백 중 예외 발생: {str(e)}", exc_info=True)
            return {'error': '서버 내부 오류가 발생했습니다.'}, 500

# 스냅샷 삭제
@snapshot_api.route('/delete')
class DeleteSnapshot(Resource):
    @snapshot_api.doc(description='스냅샷 삭제')
    @jwt_required()
    @snapshot_api.expect(snapshot_delete_model)
    def delete(self):
        logger.info("스냅샷 삭제 요청 시작")
        data = request.get_json()
        snapshot_name = data['snapshot_name']

        match = re.match(r'^([\w\-./]+)@([\w\-]+)$', snapshot_name)
        if not match:
            logger.warning(f"잘못된 스냅샷 이름 형식 삭제 요청: {snapshot_name}")
            return {'error': '스냅샷 이름 형식이 잘못되었습니다. 예: pool/zfs@20240609-153000'}, 400

        zfs_full_name = match.group(1)
        pool_name = zfs_full_name.split('/')[0]

        try:
            # pool 존재 확인
            if not is_pool_name_exists(pool_name):
                logger.warning(f"존재하지 않는 pool 삭제 요청: {pool_name}")
                return {'error': f'해당 pool을 찾을 수 없습니다: {pool_name}'}, 400

            # zfs 존재 여부 확인
            check = subprocess.run(['zfs', 'list', zfs_full_name], capture_output=True, text=True)
            if check.returncode != 0:
                logger.warning(f"존재하지 않는 ZFS 삭제 요청: {zfs_full_name}")
                return {'error': f'ZFS 파일시스템이 존재하지 않습니다: {zfs_full_name}'}, 400

            # 스냅샷 존재 여부 확인
            snapshot_check = subprocess.run(
                ['zfs', 'list', '-t', 'snapshot', '-H', '-o', 'name'],
                capture_output=True, text=True
            )
            snapshot_names = snapshot_check.stdout.strip().split('\n')
            if snapshot_name not in snapshot_names:
                related = [s for s in snapshot_names if s.startswith(f'{zfs_full_name}@')]
                logger.warning(f"존재하지 않는 스냅샷 삭제 요청: {snapshot_name}")
                return {
                    'error': f'해당 스냅샷이 존재하지 않습니다: {snapshot_name}',
                    '해당 ZFS의 스냅샷 목록': related
                }, 404

            # 삭제
            result = subprocess.run(
                ['zfs', 'destroy', snapshot_name],
                capture_output=True,
                text=True,
                check=True
            )
            logger.info(f"스냅샷 삭제 성공: {snapshot_name}")
            return {
                'message': f'Snapshot {snapshot_name} deleted successfully',
                'stdout': result.stdout.strip(),
                'stderr': result.stderr.strip(),
                'returncode': result.returncode
            }, 200

        except subprocess.CalledProcessError as e:
            logger.error(f"스냅샷 삭제 실패: {snapshot_name}, stderr: {e.stderr}", exc_info=True)
            return {
                'error': f'Failed to delete snapshot {snapshot_name}',
                'stdout': e.stdout,
                'stderr': e.stderr,
                'returncode': e.returncode
            }, 500
        except Exception as e:
            logger.error(f"스냅샷 삭제 중 예외 발생: {str(e)}", exc_info=True)
            return {'error': '서버 내부 오류가 발생했습니다.'}, 500