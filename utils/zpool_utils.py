import subprocess, os, re
from utils.logger import get_logger

logger = get_logger("zpool")

# 해당 디스크가 다른 zpool에 사용 중인지 확인
def is_device_in_use(device):
   # 절대 경로 기반 (심볼릭 링크 해석 포함)
    try:
        device_realpath = os.path.realpath(device)
        logger.debug(f"디바이스 경로 확인 - 원본: {device}, 실경로: {device_realpath}")
        result = subprocess.run(
            ['zpool', 'status', '-P'],
            capture_output=True,
            encoding='utf-8',
            check=True
        )
        lines = result.stdout.splitlines()

        for line in lines:
            if device_realpath in line:
                logger.info(f"디바이스 사용 중 - 경로: {device_realpath}, 관련 라인: {line.strip()}")
                return device
        logger.info(f"디바이스 미사용 - 경로: {device_realpath}")
        return False
    except subprocess.CalledProcessError:
        logger.error(f"디바이스 사용 여부 확인 실패 - 경로: {device}, 오류: {e.stderr or str(e)}", exc_info=True)
        return False
    
# 주어진 zpool 이름이 이미 존재하는지 확인
def is_pool_name_exists(pool_name):
    try:
        result = subprocess.run(
            ['zpool', 'list', '-H', '-o', 'name'],
            capture_output=True,
            encoding='utf-8',
            check=True
        )
        existing_pools = result.stdout.strip().splitlines()
        exists = pool_name in existing_pools
        logger.info(f"풀 이름 중복 확인 - 입력 이름: {pool_name}, 존재 여부: {exists}")
        return exists
    except subprocess.CalledProcessError:
        logger.error(f"풀 이름 중복 확인 실패 - 이름: {pool_name}, 오류: {e.stderr or str(e)}", exc_info=True)
        return False  # 오류 발생 시 존재하지 않는 것으로 처리

def get_smart_health(device):
    try:
        # -A 옵션으로 세부 확인 가능
        result = subprocess.run(['smartctl', '-H', device], capture_output=True, encoding='utf-8', check=True)
        for line in result.stdout.splitlines():
            if "SMART overall-health self-assessment test result" in line:
                # 예: "SMART overall-health self-assessment test result: PASSED"
                # PASSED: 디스크 정상 상태 / FAILED: 디스크 위험 상태
                logger.info(f"SMART 상태 확인 성공 - 디바이스: {device}, 상태: {health}")
                return line.split(":")[-1].strip()
        logger.warning(f"SMART 상태 결과 없음 - 디바이스: {device}")
        return "UNKNOWN" # 결과 문구를 찾을 수 없음
    except subprocess.CalledProcessError:
        logger.error(f"SMART 상태 확인 실패 - 디바이스: {device}, 오류: {e.stderr or str(e)}", exc_info=True)
        return "UNAVAILABLE" # SMART 기능이 없거나 명령 실행 실패