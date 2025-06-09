from flask import jsonify, request
from flask_restx import Namespace, Resource, fields
from flask_jwt_extended import jwt_required
import subprocess, os, re
from utils.zpool_utils import is_device_in_use, is_pool_name_exists, get_smart_health

zpool_api = Namespace('zpool', description='Zpool 관련 API')

zpool_create_model = zpool_api.model('CreateZpool', {
    'pool_name': fields.String(required=True, description='Zpool 이름'),
    'raid_mode': fields.String(required=True, description='RAID 모드 : stripe, mirror, raidz1, raidz2, raidz3)'),
    'devices': fields.List(fields.String, required=True, description='디바이스 목록'),
    'spares': fields.List(fields.String, required=False, description='핫 스페어 디바이스 목록')
})
    
# 물리 디스크 목록
# @zpool_bp.route('/disks', methods=['GET'])
# 수정) osdisk 제외
@zpool_api.route('/disks')
class DiskList(Resource):
    @zpool_api.doc(description='물리 디스크 목록 조회')
    @jwt_required()
    def get(self):
        try: 
            # 루트가 마운트된 디스크명 추출
            os_disk = ''
            result = subprocess.run("findmnt -n -o SOURCE /boot", shell=True, capture_output=True, text=True)
            match = re.findall(r'/dev/([a-z]+)', result.stdout.strip())
            if match:
                os_disk = match[0]
            
            print(os_disk)

            # 이름, 사이즈(GB), 모델명, 타입 출력
            lsblk_result = subprocess.run("lsblk -dn -o NAME,SIZE,MODEL,TYPE -P", shell=True, capture_output=True, encoding='utf-8')
            lines = lsblk_result.stdout.strip().split('\n')

            disks = []
            for line in lines:
                attrs = dict(re.findall(r'(\w+)="(.*?)"', line))
                if fields.get('TYPE') != 'disk':
                    continue
                if attrs.get('NAME') == os_disk:
                    continue
                dev_path = f"/dev/{attrs['NAME']}"
                disks.append({
                    'name': attrs['NAME'],
                    'path': dev_path,
                    'size': fields.get('SIZE'),
                    'model': fields.get('MODEL'),
                    'in_use': is_device_in_use(dev_path),
                    'health': get_smart_health(dev_path)
                })

            return {
                'disks': disks,
                'stderr': lsblk_result.stderr,
                'returncode': lsblk_result.returncode
            }, 200
        except subprocess.CalledProcessError as e:
            return {
                'error': '디스크 목록 조회에 실패했습니다.',
                'stdout': e.stdout,
                'stderr': e.stderr,
                'returncode': e.returncode
            }, 500

# zpool 전체 목록 조회
# @zpool_bp.route('/list', methods=['GET'])
@zpool_api.route('/list')
class ZpoolList(Resource):
    @zpool_api.doc(description='zpool 전체 목록 조회')
    @jwt_required()
    def get(self):
        
        result = subprocess.run('zpool list', capture_output=True, shell=True, encoding='UTF-8')
        lines = result.stdout.strip().split('\n')
        if not lines:
            return {'Zpool 목록이 없습니다.'}, 200
        
        zpool_list = []
        column_names = lines[0].split()
        
        print(lines)

        for line in lines[1:]:
            fields = line.split()
            if len(fields) < len(column_names):
                continue  # 필드 누락 방지
            zpool_list.append(dict(zip(column_names, fields)))

        response = {
            'stdout': zpool_list,
            'stderr': result.stderr,
            'returncode': result.returncode
        }
        
        return jsonify(response)

# zpool 생성
@zpool_api.route('/create')
class CreateZpool(Resource):
    @zpool_api.doc(description='zpool 생성')
    @jwt_required()
    @zpool_api.expect(zpool_create_model)
    def post(self):
        data = request.get_json()

        if not data:
            return {'error': '입력 데이터가 제공되지 않았습니다.'}, 400
        
        pool_name = data.get('pool_name')
        raid_mode = data.get('raid_mode')
        devices = data.get('devices') # 예) ["/dev/sdb", "/dev/sdc", ..]
        spares = data.get('spares', [])

        raid_mode = raid_mode.lower()

        # 필수 입력값이 누락되었을 때
        if not pool_name or not raid_mode or not devices:
            return {'error': '필수 항목(pool_name, raid_mode, devices)이 누락되었습니다.'}, 400

        # devices와 spares가 리스트 형식이 아닐 때
        if not isinstance(devices, list) or not isinstance(spares, list):
            return {'error': 'devices와 spares는 리스트 형식이어야 합니다.'}, 400

        # 풀 이름 규칙
        # 허용 문자 : 영문자, 숫자, -, _, .
        # 슬래시(/), 공백, 탭, 특수문자 불가
        # 대소문자 구분
        if not re.fullmatch(r'^[a-zA-Z0-9_.-]+$', pool_name):
            return {'error': 'pool_name은 영문자, 숫자, "_", "-", "."만 사용할 수 있습니다.'}, 400

        # 풀 이름 중복 확인
        if is_pool_name_exists(pool_name):
            return {'error': f'이미 존재하는 풀 이름입니다: <{pool_name}>'}, 400

        # device가 사용 중인지 확인
        used_devices = [d for d in devices + spares if is_device_in_use(d)]
        print(used_devices)
        if used_devices:
            return {
                'error': '다른 zpool에서 사용 중인 디바이스가 있습니다.',
                'used_devices': used_devices
            }, 400

        cmd = ['zpool', 'create', pool_name]

        # 풀 생성 방식
        min_devices_required = { # 최소 디바이스 개수
            'stripe': 2,
            'mirror': 2,
            'raidz1': 3,
            'raidz2': 4,
            'raidz3': 4
        }

        if raid_mode not in min_devices_required:
            return {'error': f'알 수 없는 RAID 모드입니다: {raid_mode}'}, 400

        if len(devices) < min_devices_required[raid_mode]:
            return {'error': f'{raid_mode} 모드는 최소 {min_devices_required[raid_mode]}개의 디바이스가 필요합니다.'}, 400

        used_devices = [d for d in devices + spares if is_device_in_use(d)]
        if used_devices:
            return {'error': '일부 디바이스가 이미 사용 중입니다.', 'used_devices': used_devices}, 400

        # 예비 디스크 있으면 명령어에 추가
        if spares:
            cmd += ['spare'] + spares

        try:
            result = subprocess.run(cmd, capture_output=True, encoding='utf-8', check=True)
            return {
                'stdout': result.stdout.strip().split('\n'),
                'stderr': result.stderr,
                'returncode': result.returncode
            }, 200
        except subprocess.CalledProcessError as e:
            return {
                'error': 'Zpool 생성에 실패했습니다.',
                'stdout': e.stdout,
                'stderr': e.stderr,
                'returncode': e.returncode
            }, 500
            
# zpool 상세 조회 (속성 전체 조회)
# @zpool_bp.route('/status/<pool_name>', methods=['GET'])
@zpool_api.route('/properties/<pool_name>')
class ZpoolStatus(Resource):
    @zpool_api.doc(description='zpool 속성 조회')
    @jwt_required()
    def get(self, pool_name):
        try:
            result = subprocess.run(
                ['zpool', 'get', 'all', pool_name],
                capture_output=True,
                encoding='utf-8',
                check=True
            )
            
            lines = result.stdout.strip().split('\n')
            # 첫 줄은 헤더(NAME PROPERTY VALUE SOURCE)
            properties = []
            for line in lines[1:]:
                parts = line.split(None, 3)  # 최대 4개 컬럼 분리
                if len(parts) == 4:
                    _, prop, value, source = parts # name은 무시
                    properties.append({
                        prop: value,
                        'source': source
                    })
            
            response = {
                'pool_name': pool_name,
                'properties': properties,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
            
            return response, 200
        
        except subprocess.CalledProcessError as e:
            return {
                'error': f'{pool_name} 풀의 속성 조회에 실패했습니다.',
                'stdout': e.stdout,
                'stderr': e.stderr,
                'returncode': e.returncode
            }, 500
        
# zpool 삭제
# @zpool_bp.route('/delete/<pool_name>', methods=['DELETE'])
@zpool_api.route('/delete/<pool_name>')
class DeleteZpool(Resource):
    @zpool_api.doc(description='zpool 삭제')
    @jwt_required()
    def delete(self, pool_name):
        try:
            result = subprocess.run(
                ['zpool', 'destroy', pool_name],
                capture_output=True,
                encoding='utf-8',
                check=True
            )
            
            return jsonify({
                'message': f'Zpool {pool_name} 삭제 완료',
                'stdout': result.stdout.strip().split('\n'),
                'stderr': result.stderr,
                'returncode': result.returncode
            })
            
        except subprocess.CalledProcessError as e:
            return jsonify({
                'error': f'{pool_name} 풀 삭제에 실패했습니다.',
                'stdout': e.stdout,
                'stderr': e.stderr,
                'returncode': e.returncode
            }), 500


@zpool_api.route('/status/<pool_name>')
class ZpoolStatus(Resource):
    @zpool_api.doc(description='zpool 상태 조회')
    def get(self, pool_name):
        try:
            # subprocess.run으로 zpool status 명령 실행
            result = subprocess.run(
                ['zpool', 'status', pool_name],
                capture_output=True,
                encoding='utf-8',
                check=True
            )
            
            lines = result.stdout.strip().split('\n')
            config = []
            spares = []
            
            parsing_section = 'config'
            for line in lines[5:]:
                if not line.strip():
                    break
                columns = line.split()
                print(columns)
                if columns[0] == 'spares':
                    parsing_section = 'spares'
                    continue
                if parsing_section == 'config':
                    config.append({
                        'NAME': columns[0],
                        'STATE': columns[1],
                        'READ': columns[2],
                        'WRITE': columns[3],
                        'CKSUM': columns[4],
                    })
                elif parsing_section == 'spares':
                    spares.append({
                        'NAME': columns[0],
                        'STATE': columns[1]
                    })
            
            zpool_status = {
                'pool': lines[0].split()[-1],
                'status': lines[1].split()[-1],
                'config': config,
                'spares': spares
                }
            
            return jsonify({
                'stdout': zpool_status,
                'stderr': result.stderr,
                'returncode': result.returncode
            })
            
        except subprocess.CalledProcessError as e:
            # 명령 실패시 오류 정보 반환
            return jsonify({
                'error': f'{pool_name} 풀의 상태 조회에 실패했습니다.',
                'stdout': e.stdout,
                'stderr': e.stderr,
                'returncode': e.returncode
            }), 500