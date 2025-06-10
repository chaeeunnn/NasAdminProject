from flask import request, jsonify
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import jwt_required
import subprocess, os
from utils.logger import get_logger

nfs_api = Namespace('nfs', description='NFS 관리')
logger = get_logger("nfs")

def is_zfs_exists(zfs_name: str) -> bool:
    result = subprocess.run(['zfs', 'list', '-H', '-o', 'name'], capture_output=True, text=True)
    exists = zfs_name in result.stdout.split()
    logger.debug(f"is_zfs_exists: {zfs_name} 존재여부={exists}")
    return exists

def is_already_shared(zfs_name: str, client_ip: str) -> bool:
    try:
        with open('/etc/exports', 'r') as f:
            for line in f:
                if zfs_name in line and client_ip in line:
                    logger.debug(f"is_already_shared: 이미 공유된 대상 발견 {zfs_name} -> {client_ip}")
                    return True
        return False
    except FileNotFoundError:
        logger.warning("/etc/exports 파일을 찾을 수 없습니다.")
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
            logger.info("NFS 활성화 상태 조회 요청")
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
            logger.info(f"NFS 상태 조회 결과: {status}")
            return {
                'nfs_status': status,
                'detail': result.stdout.strip().split('\n')
            }, 200

        except subprocess.CalledProcessError as e:
            logger.error(f"NFS 상태 조회 실패: {e.stderr or str(e)}", exc_info=True)
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
            logger.info("NFS 활성화 요청")
            subprocess.run(['systemctl', 'enable', '--now', 'nfs-server'], check=True)
            logger.info("NFS 서버 활성화 성공")
            return {'message': 'NFS 서버가 활성화되었습니다.'}
        except subprocess.CalledProcessError as e:
            logger.error(f"NFS 서버 활성화 실패: {e.stderr or str(e)}", exc_info=True)
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

        logger.info(f"NFS 공유 등록 요청 - ZFS: {zfs_name}, Client IP: {client_ip}, 옵션: {options}")

        if not zfs_name or not client_ip:
            logger.warning("공유 등록 실패 - zfs_name 또는 client_ip 누락")
            return {'error': 'zfs_name과 client_ip는 필수 항목입니다.'}, 400

        if not is_zfs_exists(zfs_name):
            logger.warning(f"공유 등록 실패 - 존재하지 않는 ZFS 파일시스템: {zfs_name}")
            return {'error': f'존재하지 않는 ZFS 파일시스템입니다: {zfs_name}'}, 404

        if is_already_shared(zfs_name, client_ip):
            logger.warning(f"공유 등록 실패 - 이미 공유된 대상: {zfs_name} -> {client_ip}")
            return {'error': f'이미 공유된 대상입니다: {zfs_name} -> {client_ip}'}, 409

        try:
            # exportfs 설정
            export_line = f"/{zfs_name} {client_ip}({options})\n"
            with open('/etc/exports', 'a') as f:
                f.write(export_line)

            subprocess.run(['exportfs', '-ra'], check=True)

            logger.info(f"NFS 공유 등록 성공: {zfs_name} -> {client_ip}")
            return {'message': f'{zfs_name}가 {client_ip}에 공유되었습니다.'}
        except subprocess.CalledProcessError as e:
            logger.error(f"NFS 공유 등록 실패: {e.stderr or str(e)}", exc_info=True)
            return {
                'message': '공유 대상 등록에 실패하였습니다.',
                'stderr': e.stderr,
            }, 500
        except Exception as e:
            logger.error(f"NFS 공유 등록 중 예외 발생: {str(e)}", exc_info=True)
            return {'error': '서버 내부 오류가 발생했습니다.'}, 500

# 공유 목록 조회
@nfs_api.route('/share/list')
class SharedList(Resource):
    @nfs_api.doc(description='모든 공유 목록 조회')
    @jwt_required()
    def get(self):
        try:
            logger.info("모든 NFS 공유 목록 조회 요청")
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
            logger.info(f"NFS 공유 목록 조회 성공, 총 {len(shares)}개 항목")
            return {
                'shares': shares,
                'count': len(shares)}
        except subprocess.CalledProcessError as e:
            logger.error(f"NFS 공유 목록 조회 실패: {e.stderr or str(e)}", exc_info=True)
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

        logger.info(f"특정 ZFS 공유 목록 조회 요청: {zfs_name}")

        if not zfs_name:
            logger.warning("특정 ZFS 공유 목록 조회 실패 - zfs_name 누락")
            return {'error': 'zfs_name은 필수 항목입니다.'}, 400

        if not is_zfs_exists(zfs_name):
            logger.warning(f"특정 ZFS 공유 목록 조회 실패 - 존재하지 않는 ZFS 파일시스템: {zfs_name}")
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
            logger.info(f"특정 ZFS 공유 목록 조회 성공: {zfs_name}, 총 {len(shares)}개 항목")
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
        except Exception as e:
            logger.error(f"특정 ZFS 공유 목록 조회 중 예외 발생: {str(e)}", exc_info=True)
            return {'error': '서버 내부 오류가 발생했습니다.'}, 500


# 공유 비활성화 (unshare)
@nfs_api.route('/unshare')
class NFSUnshare(Resource):
    @nfs_api.doc(description='공유 비활성화')
    @jwt_required()
    @nfs_api.expect(nfs_control_model)
    def post(self):
        try:
            data = request.get_json()
            zfs_name = data.get('zfs_name')
            client_ip = data.get('client_ip')

            logger.info(f"NFS 공유 삭제 요청 - ZFS: {zfs_name}, Client IP: {client_ip}")

            if not zfs_name or not client_ip:
                logger.warning("공유 삭제 실패 - zfs_name 또는 client_ip 누락")
                return {'error': 'zfs_name과 client_ip는 필수 항목입니다.'}, 400

            with open('/etc/exports', 'r') as f:
                lines = f.readlines()

            new_lines = []
            removed = False
            search_str = f"/{zfs_name} {client_ip}"
            for line in lines:
                if search_str in line:
                    removed = True
                    logger.debug(f"NFS 공유 삭제 대상 발견 및 제거: {line.strip()}")
                    continue
                new_lines.append(line)

            if not removed:
                logger.warning(f"공유 삭제 실패 - 공유 대상이 존재하지 않음: {search_str}")
                return {'error': '공유 대상이 존재하지 않습니다.'}, 404

            with open('/etc/exports', 'w') as f:
                f.writelines(new_lines)
            subprocess.run(['exportfs', '-ra'], check=True)

            logger.info(f"NFS 공유 삭제 성공: {zfs_name} -> {client_ip}")
            return {'message': f'{zfs_name}에 대한 {client_ip} 공유가 삭제되었습니다.'}

        except subprocess.CalledProcessError as e:
            logger.error(f"NFS 공유 삭제 실패: {e.stderr or str(e)}", exc_info=True)
            return {
                'message': '공유 대상 삭제에 실패하였습니다.',
                'stderr': e.stderr,
            }, 500
        except Exception as e:
            logger.error(f"NFS 공유 삭제 중 예외 발생: {str(e)}", exc_info=True)
            return {'error': '서버 내부 오류가 발생했습니다.'}, 500