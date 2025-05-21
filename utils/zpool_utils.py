import subprocess, os

# 해당 디스크가 다른 zpool에 사용 중인지 확인
def is_device_in_use(device):
   # 절대 경로 기반 (심볼릭 링크 해석 포함)
    try:
        device_realpath = os.path.realpath(device)

        result = subprocess.run(
            ['zpool', 'status', '-P'],
            capture_output=True,
            encoding='utf-8',
            check=True
        )
        lines = result.stdout.splitlines()

        for line in lines:
            if device_realpath in line:
                print("line: ", line)
                print("device_realpath: ", device_realpath)
                return device
        return False
    except subprocess.CalledProcessError:
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
        return pool_name in existing_pools
    except subprocess.CalledProcessError:
        return False  # 오류 발생 시 존재하지 않는 것으로 처리

def get_smart_health(device):
    try:
        result = subprocess.run(['smartctl', '-H', device], capture_output=True, encoding='utf-8', check=True)
        for line in result.stdout.splitlines():
            if "SMART overall-health self-assessment test result" in line:
                # 예: "SMART overall-health self-assessment test result: PASSED"
                return line.split(":")[-1].strip()
        return "UNKNOWN"
    except subprocess.CalledProcessError:
        return "UNAVAILABLE"