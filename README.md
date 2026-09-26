# Vlab Studio

VOID EYE PC의 Windows 설치 파일을 배포하는 저장소입니다.

## PC 다운로드

[Releases에서 설치 파일 받기](https://github.com/yun2985-lab/Vlab-Studio/releases)

| 파일 | 선택 기준 |
| --- | --- |
| `VoidEye-PC-0.31-Full-x64-Fast-Setup.exe` | 압축 해제 속도 우선, 약 166.1MB |
| `VoidEye-PC-0.31-Full-x64-Setup.exe` | 다운로드 용량 우선, 약 121.1MB |

둘 중 하나만 설치하세요. 프로그램 내용은 같습니다. Windows x64용이며 Python 실행 환경, FFmpeg, FFplay가 포함되어 있습니다. 설치 후 약 398MiB가 필요하고 녹화 영상 용량은 별도입니다. GitHub의 자동 생성 Source code ZIP은 설치 파일이 아닙니다.

## 설치와 사용

1. 실행 중인 VOID EYE를 종료합니다.
2. 선택한 전체 설치 EXE를 실행합니다.
3. VOID EYE에서 본인 Google 계정으로 로그인합니다.
4. 모바일에서도 같은 Google 계정을 사용합니다.

기존 설정 및 녹화 파일은 보존하도록 구성되어 있습니다. 설치에는 압축 해제, 파일 쓰기, 보안 검사가 포함되므로 PC 환경에 따라 시간이 달라집니다.

## Android

Vlab Studio Android 앱은 Google Play 배포 예정입니다. 이 저장소에는 APK/AAB를 배포하지 않습니다. 스토어 링크는 출시 후 추가합니다.

## 배포 상태

초기 시험 배포입니다. 기존 전체 설치본은 제작자 환경에서 동작했다는 보고를 받았습니다. Fast 설치본은 동일한 1,125개 구성 파일의 해시 대조를 통과했으며, 실제 Windows 설치 속도 개선 폭은 아직 측정하지 않았습니다. 코드 서명은 적용되지 않았습니다.

FFmpeg 등 포함 구성요소의 라이선스와 배포 정보는 설치 폴더의 안내 파일을 확인하세요.
