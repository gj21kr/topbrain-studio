# TopBrain Studio

개인용 해부학 탐색 Studio. 공개 첫 화면에는 BodyParts3D 참조 아틀라스를 표시하고, 사용자가 가져온 TopBrain 혈관과 같은 사례의 TotalSegmentator 마스크도 탐색할 수 있습니다. 구조 선택, 검색, 그룹별 숨김/표시·투명도, 단독 보기, 카메라 프리셋, 구조 분해, 라벨, 단계별 학습을 제공합니다. 참조 아틀라스와 사례별 데이터는 출처와 좌표계를 구분합니다.

**이 GitHub 저장소는 코드와 명시적으로 허용된 BodyParts3D 4.0 참조 아틀라스만 공개합니다.** TopBrain 원본 영상·분할 데이터와 파생 GLB·JSON manifest·사례별 공간 메타데이터는 배포하지 않습니다. 사용자가 별도로 준비한 사례 데이터는 로컬에서만 처리합니다.

## 실행

Node.js 22.12 이상에서:

```powershell
npm ci
npm run dev
```

로컬 주소: http://127.0.0.1:5181 . `npm run build` 후 `npm run preview`로 빌드 결과를 확인합니다. `npm test`는 데이터 계약과 외부 리소스 차단을 검증합니다.

## 공개 데모 게시

정적 데모는 GitHub Pages의 프로젝트 경로 [https://gj21kr.github.io/topbrain-studio/](https://gj21kr.github.io/topbrain-studio/)에 게시할 수 있습니다. 저장소의 **Settings → Pages → Build and deployment → Source**를 **GitHub Actions**로 설정한 다음, `main` 브랜치에 변경 사항을 반영하거나 **Actions → Publish demo to GitHub Pages → Run workflow**에서 `main`을 선택하세요. 배포가 끝나면 해당 Actions 실행의 `github-pages` 환경 URL을 확인합니다. [GitHub Pages 설정 안내](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)

배포 워크플로는 `npm ci`, `npm test`, `npm run build`, `npm run check:public-build`를 통과한 `dist/`만 업로드합니다. 공개 빌드에서는 Vite의 base URL이 `/topbrain-studio/`이며, 평소 로컬 개발 빌드는 `/`를 사용합니다. 로컬에서 Pages 빌드를 점검하려면 PowerShell에서 다음을 실행하세요.

```powershell
$env:GITHUB_PAGES = 'true'
npm ci
npm test
npm run build
npm run check:public-build
Remove-Item Env:GITHUB_PAGES
```

**게시 경계:** Pages는 공개 서비스입니다. `public/`과 `dist/`에는 데모 코드·파비콘과 `reference/bodyparts3d.glb`, `reference/bodyparts3d.json`, `reference/ATTRIBUTION.txt`만 허용하며 세 참조 파일이 모두 있어야 배포합니다. 빌드 검사는 그 외 파일·디렉터리·심볼릭 링크·하드 링크·대용량 번들을 거부합니다. 파일명과 manifest의 출처 표기는 TopBrain 파생물이 아닌지 증명하지 못하므로 공개 참조 모델의 원본과 변환 내역을 별도로 검토해야 합니다. TopBrain 원본·파생물과 사례별 좌표 정보는 저장소, `public/`, Pages artifact 어디에도 넣지 마세요. 공개 페이지에는 로컬 개발 서버의 **Open local TopBrain case** 기능이 없습니다. 실제 사례는 각 방문자가 **Import GLB + manifest**로 자신의 브라우저에서 직접 선택하며, 이 과정에서 파일은 서버로 업로드되지 않습니다.

## 공개 BodyParts3D 참조 아틀라스

첫 방문 시 공개 참조 모델이 자동으로 로드됩니다. 요청이 실패하면 코드로 만든 모식도가 표시되며, 화면에서 모식도로 전환하거나 BodyParts3D를 다시 열 수 있습니다. 게시 후 정적 파일의 주소는 [bodyparts3d.glb](https://gj21kr.github.io/topbrain-studio/reference/bodyparts3d.glb), [bodyparts3d.json](https://gj21kr.github.io/topbrain-studio/reference/bodyparts3d.json), [ATTRIBUTION.txt](https://gj21kr.github.io/topbrain-studio/reference/ATTRIBUTION.txt)입니다.

공개 모델은 [BodyParts3D 4.0 PART-OF 축소 OBJ 아카이브](https://dbarchive.biosciencedbc.jp/data/bodyparts3d/20130619/partof_BP3D_4.0_obj_99.zip)의 24개 선택 구조를 웹 표시용 GLB로 변환한 참조 해부학입니다. 뇌혈관·두개골·뇌와 근위부 혈관인 상행대동맥, 대동맥활, 팔머리동맥, 좌우 총경동맥·쇄골하동맥이 포함됩니다. 복부까지 이어지는 전체 대동맥은 포함하지 않습니다. 원본 좌표의 mm/Z-up을 glTF의 m/Y-up으로 바꾸며, 정확한 구조별 출처와 변환 내역은 공개 manifest와 `ATTRIBUTION.txt`에 기록합니다. 필수 표기: **“BodyParts3D, © The Database Center for Life Science licensed under CC Attribution 4.0 International”**. [공식 다운로드 목록](https://dbarchive.biosciencedbc.jp/en/bodyparts3d/download.html), [공식 데이터 이용 허락](https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html), [CC BY 4.0 약관](https://creativecommons.org/licenses/by/4.0/)을 함께 확인하세요. 이 공개 데이터의 CC BY 4.0은 프로젝트 코드의 라이선스를 정하지 않습니다.

공식 아카이브에는 좌우 총경동맥과 내경동맥 사이, 좌우 쇄골하동맥과 척추동맥 사이의 목 구간을 잇는 메시가 없습니다. 화면의 점선 네 개는 가장 가까운 원본 메시 꼭짓점 사이를 잇는 **모식적 위치 안내선**입니다. 공식 BodyParts3D 혈관 메시나 검증된 혈관 주행·길이로 해석하지 마세요. 이 구분과 간격은 공개 manifest의 `connectionGuides` 및 `ATTRIBUTION.txt`에 기록합니다.

[공식 데이터베이스 설명](https://dbarchive.biosciencedbc.jp/en/bodyparts3d/desc.html)에 따르면 BodyParts3D는 성인 남성의 **참조 아틀라스**입니다. 가져온 TopBrain 영상이나 같은 사례의 TotalSegmentator 마스크와 동일한 피험자 데이터가 아니며, 사례 간 정합도 수행하지 않습니다. 따라서 참조 모델과 가져온 분할을 동일 공간에 맞는 것으로 해석하거나 임상적 비교에 사용하지 마세요.

## BP/HR 맥동 미리보기의 범위

심박수(HR)는 화면의 박동 주기만, 수축기·이완기 혈압(SBP/DBP)은 표시 압력 범위를 정합니다. 맥압(SBP−DBP)에 따른 3D 동맥의 발광 대비 변화는 ±10% 이내이며, 그래프 파형은 모식적 보간으로 측정된 압력·혈류 파형이 아닙니다. [AHA의 혈압 설명](https://www.heart.org/en/health-topics/high-blood-pressure/blood-pressure-explained)과 [심박수 설명](https://www.heart.org/en/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure/all-about-heart-rate-pulse)은 입력값의 일반적 의미를 설명합니다. [뇌혈류 자동조절 원연구](https://pubmed.ncbi.nlm.nih.gov/2492126/)는 실제 동맥압 변화와 Doppler 혈류 속도를 측정했습니다. 이 미리보기는 그런 측정이나 혈역학 계산을 하지 않으므로 혈류 속도·방향·유량·국소 관류 또는 개인별 뇌혈류 자동조절을 추정하지 않습니다.

## 실제 TopBrain 열기

사용 권한을 갖춘 TopBrain 데이터를 로컬 폴더에 별도로 준비하세요. 원본을 수정하지 않고 별도 변환하며, 절차는 [로컬 데이터 변환 안내](docs/TOPBRAIN_DATA.md)를 참조하세요. 변환한 `private-assets/topbrain-cta-001.glb`와 `.json`이 있으면 로컬 개발 화면의 **Open local TopBrain case**로 로드합니다. 이 이름은 앱이 찾는 로컬 출력 이름이며 원본 사례 식별자가 아닙니다. 이 두 파일은 Git과 정적 배포 빌드에 포함하지 않습니다. 로컬 개발/preview 서버가 루프백에서 지정된 두 경로를 제공하지만, **Open local TopBrain case** 버튼은 개발 화면에서만 표시됩니다. 빌드 미리보기와 공개 Pages 화면에서는 **Import GLB + manifest**를 사용하세요. 공개 Pages에는 이 로컬 경로가 없습니다.

다른 사례는 **Import GLB + manifest**에서 파일 두 개를 함께 선택합니다. 브라우저 메모리에서 처리하며 업로드하지 않습니다. GLB는 모든 geometry/buffer가 내장된 정적 모델이어야 하고, URI·압축 확장·animation·skin은 거부합니다. GLB ≤150 MB, manifest ≤2 MB, 1–500개 고유 구조를 허용합니다. 구조별 mesh 이름은 manifest와 정확히 일치해야 합니다.

TotalSegmentator 결과도 사용하려면 변환 명령에 `--total-masks '<동일 사례의 마스크 폴더>'`를 추가하세요. 0/1 NIfTI 마스크를 검사하여 비어 있는 구조는 제외하고, 뇌·뼈·척수 등을 독립 mesh로 추가합니다. 영상 크기와 물리 좌표가 다르면 변환을 중단합니다. 추가 구조는 처음에는 숨김 상태이며, 그룹별 표시와 투명도로 혈관과의 관계를 살펴볼 수 있습니다. 구조 분해 슬라이더는 추가 구조도 혈관과 함께 이동시킵니다(좌우 구조는 옆으로, 두개골·뇌·척수·척추는 위아래로 분리). 이전에 변환한 자산은 다시 변환해야 분해됩니다. Reset은 이러한 초기 설정을 복원합니다. 자세한 예시는 [로컬 데이터 변환 안내](docs/TOPBRAIN_DATA.md)에 있습니다.

## 범위와 출처

- TopBrain은 CTA/MRA 혈관 segmentation이며 머리·목의 모든 뼈·근육·신경을 제공하지 않습니다. 원 TopCoW 영상은 얼굴을 제거하고 braincase로 crop되어 있어 목 전체를 재현한다고 말할 수 없습니다.
- 코드로 만든 혈관 모식도는 TopBrain 데이터나 검증된 해부학이 아닙니다. BodyParts3D 참조 모델도 특정 사례에 맞춘 분할이 아닙니다. 분해 모드는 원래 위치를 변경합니다.
- 저장소의 공개 데이터는 위 BodyParts3D 참조 모델로 제한합니다. 가져온 사례의 release와 출처는 로컬 manifest에 기록합니다.
- 비상업적 개인 학습 목적. TopBrain의 저자·제목·출처 링크를 유지하고, 사용한 release의 라이선스 원문을 확인하세요. 원문과 attribution은 로컬 manifest에 기록합니다. 데이터 이용 조건은 프로젝트 코드의 공개 여부와 별개입니다.
- 진단·치료·시술 계획에 사용하지 않습니다.

공식 자료: [TopBrain data](https://topbrain2025.grand-challenge.org/data/), [TopBrain v3](https://zenodo.org/records/21972006), [TopCoW preprocessing](https://topcow23.grand-challenge.org/data/).

## 독립성

[Model X Studio](https://github.com/ashemag/model-x-studio)의 부품 탐색 UI를 참고한 독립 구현입니다. 원 저장소의 코드·차량 모델은 포함하지 않습니다. 회사의 코드·설계 자산은 이 저장소에 포함하지 않습니다.

## 현재 한계

학습 문구는 구조 이름과 출처를 중심으로 한 초기 콘텐츠입니다. 해부학 설명·퀴즈 검수, 여러 사례 탐색, CT slice와 mesh overlay 비교는 후속 작업입니다. TotalSegmentator는 제공된 마스크 범위의 예측 결과이며, 빈 마스크를 해부학적 부재로 해석하지 않습니다. 서로 다른 voxel grid의 자동 정합·재표본화는 지원하지 않습니다. 정적 빌드에는 BodyParts3D 참조 아틀라스만 포함하며 TopBrain 원본·파생 데이터는 배포하지 않습니다. 초기 구현 검증 범위는 [검증 기록](docs/VALIDATION_2026-09-08.md)을 참조하세요.
