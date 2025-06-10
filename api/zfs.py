from flask import request
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import jwt_required
import subprocess
from utils.zpool_utils import is_pool_name_exists
from utils.logger import get_logger

zfs_api = Namespace('zfs', description='ZFS 관련 API')
logger = get_logger("zfs")

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
        logger.info("zfs 전체 조회 요청")
        try: 
            columns = ['NAME', 'USED', 'AVAIL', 'REFER', 'MOUNTPOINT']
            result = subprocess.run(['zfs', 'list', '-H', '-o', 'name,used,avail,refer,mountpoint'], capture_output=True, encoding='utf-8')
            lines = result.stdout.strip().split('\n')

            zfs_list = []
            for line in lines:
                values = line.split('\t')
                zfs_list.append(dict(zip(columns, values)))
            logger.info(f"zfs 전체 조회 성공: {len(zfs_list)}개 항목 반환")
            return {
                'zfs': zfs_list,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except subprocess.CalledProcessError as e:
            logger.error(f"zfs 전체 조회 실패: {str(e)}")
            return {'error': str(e)}, 500    
        
# zfs 상세 조회 (속성)
@zfs_api.route('/properties')
class ZFS_Status(Resource):
    @zfs_api.doc(description='zfs 속성 조회')
    @jwt_required()
    @zfs_api.expect(get_zfs_model)
    def post(self):
        logger.info("zfs 속성 조회 요청")
        data = request.get_json()

        if not data:
            logger.warning("zfs 속성 조회 요청 실패: 입력된 데이터가 없습니다.")
            return {'error': '입력된 데이터가 없습니다.'}, 400
        
        pool_name = data.get('pool_name')
        zfs_name = data.get('zfs_name')
        full_name = f'{pool_name}/{zfs_name}'

        try:
            # 존재하는 pool인지 확인
            if not is_pool_name_exists(pool_name):
                logger.warning(f"zfs 속성 조회 실패: 존재하지 않는 pool {pool_name}")
                return {'error': f'해당 pool을 찾을 수 없습니다. : {pool_name}'}
            # 존재하는 zfs인지 확인
            check = subprocess.run(['zfs', 'list', full_name], capture_output=True, text=True)
            if check.returncode != 0:
                logger.warning(f"zfs 속성 조회 실패: 존재하지 않는 ZFS {full_name}, stderr: {check.stderr}")
                return {'error': f'해당 ZFS를 찾을 수 없습니다. : {full_name}', 'stderr':check.stderr}, 400
            
            key_props = [
                "type", "creation", "used", "available", "referenced", "mounted", "mountpoint",
                "compression", "quota", "readonly", "sharenfs", "checksum", "atime", "recordsize", "refreservation"
            ]

            cmd = ["zfs", "get", ",".join(key_props), full_name]
        
            result = subprocess.run(cmd, capture_output=True, text=True)

            lines = result.stdout.strip().split("\n")
            # 첫 줄은 헤더이므로 제외하고 파싱
            response = []
            for line in lines[1:]:
                parts = line.split(None, 3)  # 최대 4개 컬럼 분리
                if len(parts) == 4:
                    name, prop, value, source = parts
                    response.append({prop: value})
                
            logger.info(f"zfs 속성 조회 성공: {full_name}")
            return {
                'zfs': response,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except subprocess.CalledProcessError as e:
            logger.error(f"zfs 속성 조회 중 오류 발생: {str(e)}")
            return {'error': f'속성 조회 중 오류가 발생했습니다: {str(e)}'}, 500

# zfs 생성
@zfs_api.route('/create')
class ZFSCreate(Resource):
    @zfs_api.doc(description='zfs 생성')
    @jwt_required()
    @zfs_api.expect(create_zfs_model)
    def post(self):
        logger.info("zfs 생성 요청")
        data = request.json
        pool_name = data.get('pool_name')
        zfs_name = data.get('zfs_name')
        full_name = f"{pool}/{zfs}"

        # zfs 이름 규칙
        # 허용 문자 : 영문자, 숫자, -, _, .
        # 슬래시(/), 공백, 탭, 특수문자 불가 (pool 이름을 따로 받기 때문에 슬래시 허용 안 하는 걸로)
        # 대소문자 구분
        if not bool(re.fullmatch(r'^[a-zA-Z0-9_.-]+$', zfs_name)):
            logger.warning(f"zfs 생성 실패: 이름 규칙 위반 - {zfs_name}")
            return {'error': 'zfs 이름은 영문자, 숫자, "_", "-", "."만 사용할 수 있습니다.'}, 400

        try:
            # 존재하는 pool인지 확인
            if not is_pool_name_exists(pool_name):
                logger.warning(f"zfs 생성 실패: 존재하지 않는 pool {pool_name}")
                return {'error': f'해당 pool을 찾을 수 없습니다. : {pool_name}'}
            # 중복 여부 확인
            check = subprocess.run(['zfs', 'list', full_name], capture_output=True, text=True)
            if check.returncode == 0:
                logger.warning(f"zfs 생성 실패: 이미 존재하는 ZFS {full_name}")
                return {'error': f'ZFS {full_name}은(는) 이미 존재합니다.'}, 400
            
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
            logger.info(f"zfs 생성 성공: {full_name}")
            return {
                'message': f'{full_name} 생성 및 설정이 완료되었습니다.'
                }, 201

        except subprocess.CalledProcessError as e:
            logger.error(f"zfs 생성 중 오류 발생: {str(e)}")
            return {'error': f'ZFS 생성 중 오류가 발생했습니다: {str(e)}'}, 500

# zfs 삭제
@zfs_api.route('/delete/<pool_name>/<zfs_name>')
class DeleteZFS(Resource):
    @zfs_api.doc(description='zfs 삭제')
    @jwt_required()
    def delete(self, pool_name, zfs_name):
        full_name = f'{pool_name}/{zfs_name}'
        logger.info(f"zfs 삭제 요청: {full_name}")
        try:
            # 존재하는 pool인지 확인
            if not is_pool_name_exists(pool_name):
                logger.warning(f"zfs 삭제 실패: 존재하지 않는 pool {pool_name}")
                return {'error': f'해당 pool을 찾을 수 없습니다. : {pool_name}'}
            # 존재하는 zfs인지 확인
            check = subprocess.run(['zfs', 'list', full_name], capture_output=True, text=True)
            if check.returncode != 0:
                logger.warning(f"zfs 삭제 실패: 존재하지 않는 ZFS {full_name}, stderr: {check.stderr}")
                return {'error': f'해당 ZFS를 찾을 수 없습니다. : {full_name}', 'stderr':check.stderr}, 400

            result = subprocess.run(
                ['zfs', 'destroy', full_name],
                capture_output=True,
                encoding='utf-8',
                check=True
            )
            logger.info(f"zfs 삭제 성공: {full_name}")
            return {
                'message': f'ZFS {full_name}가 삭제되었습니다.',
                'stdout': result.stdout.strip().split('\n'),
                'stderr': result.stderr,
                'returncode': result.returncode
            }
            
        except subprocess.CalledProcessError as e:
            logger.error(f"zfs 삭제 실패: {full_name}, error: {str(e)}")
            return {
                'error': f'ZFS {full_name} 삭제에 실패하였습니다.',
                'stdout': e.stdout,
                'stderr': e.stderr,
                'returncode': e.returncode
            }, 500