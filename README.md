# TopBrain Studio

개인용 혈관 해부학 탐색 Studio. 구조 선택, 검색, 필터, 숨김/표시, 단독 보기, 카메라 프리셋, 구조 분해, 투명도, 라벨, 단계별 학습을 제공합니다. 실제 TopBrain 데이터와 첫 화면의 모식도는 별도로 표시합니다.

**이 GitHub 저장소는 코드만 공개합니다.** TopBrain 원본 영상·분할 데이터와 파생 GLB·JSON manifest·공간 메타데이터는 배포하지 않습니다. 사용자가 별도로 준비한 데이터는 로컬에서만 처리합니다.

## 실행

Node.js 22.12 이상에서:

```powershell
npm ci
npm run dev
```

로컬 주소: http://127.0.0.1:5181 . `npm run build` 후 `npm run preview`로 빌드 결과를 확인합니다. `npm test`는 데이터 계약과 외부 리소스 차단을 검증합니다.

## 실제 TopBrain 열기

사용 권한을 갖춘 TopBrain 데이터를 로컬 폴더에 별도로 준비하세요. 원본을 수정하지 않고 별도 변환하며, 절차는 [로컬 데이터 변환 안내](docs/TOPBRAIN_DATA.md)를 참조하세요. 변환한 `private-assets/topbrain-cta-001.glb`와 `.json`이 있으면 **Open local TopBrain case**로 로드합니다. 이 이름은 앱이 찾는 로컬 출력 이름이며 원본 사례 식별자가 아닙니다. 이 두 파일은 Git과 정적 배포 빌드에 포함하지 않습니다. 로컬 개발/preview 서버만 지정된 두 경로로 제공합니다.

다른 사례는 **Import GLB + manifest**에서 파일 두 개를 함께 선택합니다. 브라우저 메모리에서 처리하며 업로드하지 않습니다. GLB는 모든 geometry/buffer가 내장된 정적 모델이어야 하고, URI·압축 확장·animation·skin은 거부합니다. GLB ≤150 MB, manifest ≤2 MB, 1–500개 고유 구조를 허용합니다. 구조별 mesh 이름은 manifest와 정확히 일치해야 합니다.

## 범위와 출처

- TopBrain은 CTA/MRA 혈관 segmentation이며 머리·목의 모든 뼈·근육·신경을 제공하지 않습니다. 원 TopCoW 영상은 얼굴을 제거하고 braincase로 crop되어 있어 목 전체를 재현한다고 말할 수 없습니다.
- 첫 화면은 코드로 만든 모식도이며 TopBrain 데이터나 검증된 해부학이 아닙니다. 분해 모드는 원래 위치를 변경합니다.
- 데이터는 저장소에 포함되지 않습니다. 사용한 release와 출처는 로컬 manifest에 기록합니다.
- 비상업적 개인 학습 목적. TopBrain의 저자·제목·출처 링크를 유지하고, 사용한 release의 라이선스 원문을 확인하세요. 원문과 attribution은 로컬 manifest에 기록합니다. 데이터 이용 조건은 프로젝트 코드의 공개 여부와 별개입니다.
- 진단·치료·시술 계획에 사용하지 않습니다.

공식 자료: [TopBrain data](https://topbrain2025.grand-challenge.org/data/), [TopBrain v3](https://zenodo.org/records/21972006), [TopCoW preprocessing](https://topcow23.grand-challenge.org/data/).

## 독립성

[Model X Studio](https://github.com/ashemag/model-x-studio)의 부품 탐색 UI를 참고한 독립 구현입니다. 원 저장소의 코드·차량 모델은 포함하지 않습니다. 회사의 코드·설계 자산은 이 저장소에 포함하지 않습니다.

## 현재 한계

학습 문구는 구조 이름과 출처를 중심으로 한 초기 콘텐츠입니다. 해부학 설명·퀴즈 검수, 여러 사례 탐색, CT slice와 mesh overlay 비교, 뼈/신경 등 보조 atlas 연결은 후속 작업입니다. 정적 빌드에는 데이터가 없으며 이 프로젝트에서는 원본·파생 데이터를 배포하지 않습니다. 구현 검증 범위는 [검증 기록](docs/VALIDATION_2026-09-08.md)을 참조하세요.
