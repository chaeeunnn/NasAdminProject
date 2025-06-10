## NasAdminProject
### 프로젝트 소개
NAS 관리자 웹 시스템은 Python과 Flask를 기반으로 개발된 웹 기반 NAS 관리 도구입니다.
ZFS, NFS, Linux 환경과의 연동을 통해 스토리지 관리, 데이터 복구, NFS 공유 설정 등 NAS 운영에 필요한 핵심 기능을 직관적인 웹 인터페이스로 제공합니다.
관리자가 복잡한 명령어를 직접 입력하지 않아도, 다양한 NAS 자원과 서비스를 쉽고 효율적으로 관리할 수 있습니다.

### 주요 기능
* 스토리지 관리
* 데이터 복구 (스냅샷)
* NFS 공유 관리
* 사용자 인증 및 관리
* 시스템 상태 모니터링 및 로그
* Swagger 기반 API 명세 제공

### 사전 요구사항
* Python 3.9 이상
* pip 패키지 매니저
* Linux 서버 (Rocky Linux 8.10 minimal 등)
* root 권한 (ZFS, NFS 명령 실행)
* ZFS, NFS 패키지 설치 및 활성화
* 최소 8GB RAM, 4개 이상의 디스크 권장
* 웹 브라우저 (관리자 페이지 접근용)
* (권장) Python 가상환경

### 설치 및 실행 방법
* 저장소 클론
```bash
git clone https://github.com/chaeeunnn/NasAdminProject.git
cd NasAdminProject
```
* 가상환경
```bash
python -m venv venv
source venv/bin/activate
```
* 필수 패키지 설치
```bash
pip install -r requirements.txt
```
* 환경 변수 및 초기 설정

  .env 파일 생성 후 JWT 등 환경 변수 입력

  예시:
  ```
  JWT_SECRET_KEY=your-very-secret-key
  ```
* 실행
```bash
python app.py
```
  * 기본 포트(5000)에서 서비스 시작
  * 웹 브라우저에서 http://localhost:5000 접속
