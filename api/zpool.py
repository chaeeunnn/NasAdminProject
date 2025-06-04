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
    @jwt_required()
    def get(self):
        # 이름, 사이즈(GB), 모델명, 타입 출력
        result = subprocess.run("lsblk -dn -o NAME,SIZE,MODEL,TYPE -P", shell=True, capture_output=True, encoding='utf-8')
        
        lines = result.stdout.strip().split('\n')
        print(lines)
        disks = []
        
        for line in lines:
            fields = dict(re.findall(r'(\w+)="(.*?)"', line))
            print(fields)
            if fields.get('TYPE') != 'disk':
                continue
            
            dev_path = f"/dev/{fields['NAME']}"
            disks.append({
                'name': fields['NAME'],
                'path': dev_path,
                'size': fields.get('SIZE'),
                'model': fields.get('MODEL'),
                'in_use': True if is_device_in_use(dev_path) else False,
                'health': get_smart_health(dev_path)
            })

        response = {
            'disks': disks,
            'stderr': result.stderr,
            'returncode': result.returncode
        }
        
        return jsonify(response)

# zpool 전체 목록 조회
# @zpool_bp.route('/list', methods=['GET'])
@zpool_api.route('/list')
class ZpoolList(Resource):
    @jwt_required()
    def get(self):
        
        result = subprocess.run('zpool list', capture_output=True, shell=True, encoding='UTF-8')
        lines = result.stdout.strip().split('\n')
        
        zpool_list = []
        column_names = lines[0].split()
        
        print(lines)

        for line in lines[1:]:
            fields = line.split() # -H 옵션은 tab 구분자 사용
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
    @jwt_required()
    @zpool_api.expect(zpool_create_model)
    def post(self):
        data = request.get_json()

        if not data:
            return {'error': 'No input data provided'}, 400
        
        pool_name = data.get('pool_name')
        raid_mode = data.get('raid_mode')
        devices = data.get('devices')
        spares = data.get('spares', [])

        raid_mode = raid_mode.lower()

        if is_pool_name_exists(pool_name):
            return {'error': f'Pool name <{pool_name}> already exists'}, 400

        if not pool_name or not raid_mode or not devices or not isinstance(devices, list):
            return {'error': 'Invalid input data'}, 400

        used_devices = [d for d in devices + spares if is_device_in_use(d)]
        if used_devices:
            return {
                'error': 'Some devices are already in use by other zpools',
                'used_devices': used_devices
            }, 400

        cmd = ['zpool', 'create', pool_name]

        if raid_mode == 'stripe':
            min_disks = 2
            cmd += devices
        elif raid_mode == 'mirror':
            min_disks = 2
            cmd += ['mirror'] + devices
        elif raid_mode == 'raidz1':
            min_disks = 3
            cmd += ['raidz'] + devices
        elif raid_mode == 'raidz2':
            min_disks = 4
            cmd += ['raidz2'] + devices
        elif raid_mode == 'raidz3':
            min_disks = 4
            cmd += ['raidz3'] + devices
        else:
            return {'error': 'Unknown raid_mode'}, 400

        if len(devices) < min_disks:
            return {'error': f'{raid_mode} requires at least {min_disks} devices'}, 400

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
                'error': 'Failed to create zpool',
                'stdout': e.stdout,
                'stderr': e.stderr,
                'returncode': e.returncode
            }, 500
            
# zpool 상세 조회 (속성 전체 조회)
# @zpool_bp.route('/status/<pool_name>', methods=['GET'])
@zpool_api.route('/properties/<pool_name>')
class ZpoolStatus(Resource):
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
                'error': f'Failed to get properties for zpool {pool_name}',
                'stdout': e.stdout,
                'stderr': e.stderr,
                'returncode': e.returncode
            }, 500
        
# zpool 삭제
# @zpool_bp.route('/delete/<pool_name>', methods=['DELETE'])
@zpool_api.route('/delete/<pool_name>')
class DeleteZpool(Resource):
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
                'message': f'Zpool {pool_name} deleted successfully',
                'stdout': result.stdout.strip().split('\n'),
                'stderr': result.stderr,
                'returncode': result.returncode
            })
            
        except subprocess.CalledProcessError as e:
            return jsonify({
                'error': f'Failed to delete zpool {pool_name}',
                'stdout': e.stdout,
                'stderr': e.stderr,
                'returncode': e.returncode
            }), 500


@zpool_api.route('/status/<pool_name>')
class ZpoolStatus(Resource):
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
                'error': f'Failed to get status for zpool {pool_name}',
                'stdout': e.stdout,
                'stderr': e.stderr,
                'returncode': e.returncode
            }), 500