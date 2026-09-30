# Splatomy

공개 의료영상 데이터셋에서 해부 구조를 3D로 꺼내 브라우저에서 탐색하는 개인 프로젝트입니다. Python 변환기가 한 피험자의 분할 라벨 — [TotalSegmentator](https://doi.org/10.5281/zenodo.10047292)의 전신 CT 117구조, 또는 [TopBrain](https://doi.org/10.5281/zenodo.21972006)·[TopCoW](https://doi.org/10.5281/zenodo.15692630)의 CTA/MRA 뇌혈관 36–42구조 — 를 임베디드 GLB와 JSON manifest로 바꾸고, 같은 영상의 강도(CT는 HU, MRA는 강도 백분위)를 Gaussian splat **맥락 레이어**로 만들어 메시와 같은 좌표계에 깔며, three.js + [Spark](https://sparkjs.dev) 뷰어가 둘을 함께 읽습니다. 구조 검색, 그룹별 표시·투명도, 단독 보기, 카메라 프리셋, 분해(explode), 라벨, 맥락 레이어(CT/CTA/MRA) on/off·농도를 제공합니다.

공개 데모([GitHub Pages](https://gj21kr.github.io/topbrain-studio/))의 첫 화면은 BodyParts3D 4.0 참조 아틀라스(CC BY 4.0)를 열고, 그 요청이 실패하면 코드로 그린 혈관 모식도가 나타납니다. 둘 다 특정 사례의 CT가 아닙니다. 실제 CTA 해부학과 splat 레이어는 **Open TopBrain CTA case**(승인된 공개 사례 하나, 약 38 MB)를 열거나 변환한 데이터를 가져왔을 때 나타납니다. 이 도구는 진단 기기가 아닙니다.

## 이 저장소가 보여주는 것

- **의료영상 좌표계를 끝까지 추적한다.** voxel → NIfTI affine → RAS mm → glTF metres. 회전·shear·비등방 spacing·좌우 반전(LAS) 볼륨을 전부 처리하고, 구조마다 voxel/vertex 한 쌍을 manifest에 남겨 독립 검산이 가능합니다.
- **언어 경계를 건너는 계약을 양쪽에서 강제한다.** GLB 상한(150 MB, 메시당 정점 3,000,000·인덱스 9,000,000), chunk 레이아웃, "schema 2면 모든 구조가 자기 출처를 가진다"는 규칙이 Python 변환기와 TypeScript 뷰어에 각각 구현돼 있고, Python 테스트가 `src/model.ts`를 직접 읽어 두 숫자가 같은지 대조합니다. 한쪽만 바꾸면 CI가 깨집니다.
- **테스트가 무엇을 검증하는지 뮤테이션으로 확인했다.** 상수를 바꾸거나 분기를 지웠을 때 실제로 실패하는 테스트만 남겼습니다. 이 과정에서 "통과하지만 아무것도 검증하지 않는" 테스트 네 개를 찾아 고쳤습니다.
- **분할 경계와 원본 CT를 한 좌표계에 겹친다.** 메시는 분할이 *어디서 끝나는지*를, splat 레이어는 그 경계가 *어떤 조직 속에 앉아 있는지*를 보여줍니다. 복셀당 Gaussian 하나를 학습 없이 볼륨에서 직접 초기화하고(뼈·조영 혈관·연조직의 HU 전달함수), 뷰어는 PLY 헤더의 splat 수, CT 체크섬, voxel→glTF 행렬이 GLB manifest와 일치할 때만 레이어를 받습니다. 다른 피험자·다른 좌표계의 레이어는 열리지 않습니다.
- **데이터는 저장소에 없다.** 코드만 배포하고, 데이터셋은 Zenodo에서 직접 받아 로컬에서 변환합니다. 파생 에셋은 `private-assets/`에 두고 커밋하지 않습니다. 예외는 명시적으로 승인한 두 묶음, BodyParts3D 참조 아틀라스 세 파일과 TopBrain 2025 CTA 사례 다섯 파일(`public/cases/topbrain-ct-001/`, 출처 표기·비상업)뿐이며, 공개 빌드 검사가 그 digest를 고정하고 다른 파일은 거부합니다.

## 데이터셋

**TotalSegmentator** — Wasserthal, J. et al. *TotalSegmentator: Robust Segmentation of 104 Anatomic Structures in CT Images.* Radiology: AI 5(5), 2023. [doi:10.1148/ryai.230024](https://doi.org/10.1148/ryai.230024)
데이터: [Zenodo 10047292](https://doi.org/10.5281/zenodo.10047292) (v2.0.1, 1,228명, 117구조, 23.6 GB) · 탐색용 [소형판 10047263](https://doi.org/10.5281/zenodo.10047263) (102명, 3.2 GB). 라이선스 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). 각 피험자 폴더는 `ct.nii.gz`와 `segmentations/<structure>.nii.gz`(구조별 0/1 마스크)로 구성되고, 변환기는 이 레이아웃을 그대로 읽습니다.

**TopBrain 2025 / TopCoW** — Yang, K. et al. *TopBrain segmentation challenge for whole brain vessel anatomy.* medRxiv 2026 · Yang, K. et al. *The TopCoW Challenge: Topology-Aware Circle of Willis Segmentation for CT and MR Angiography.* NEJM AI 3(8), 2026.
데이터: [TopBrain 데이터 릴리스 21972006](https://doi.org/10.5281/zenodo.21972006) (CTA·MRA 25쌍, 뇌혈관 36클래스 통합 라벨 + 모달리티별 40/42클래스, 2.0 GB) · [TopCoW 릴리스 15692630](https://doi.org/10.5281/zenodo.15692630) (250장, Willis 고리 13클래스, 10.5 GB). 영상은 braincase로 crop·deface된 LPS+ NIfTI이고 라벨은 영상당 정수 라벨맵 하나입니다. 라이선스: [opendata.swiss 조건](https://opendata.swiss/en/terms-of-use)의 "Open use. Must provide the source." — **비상업 사용은 자유, 상업 사용은 데이터 소유자(취리히 대학병원)의 허가 필요.** 이 조건 때문에 TopBrain·TopCoW에서 파생한 GLB·splat은 로컬에만 두고 공개 데모에 싣지 않습니다.

두 데이터셋 모두 혈관이 아닌 구조(두개골·뇌)의 마스크는 뇌혈관 릴리스에 없습니다. 그 맥락은 CTA·MRA 강도 자체를 splat 레이어로 그려서 보여 줍니다.

## 실행

Node.js 22 이상:

```bash
npm ci
npm run dev          # http://127.0.0.1:5181
npm test             # 뷰어 쪽 계약 검증
npm run build        # tsc + vite
```

Python 3.12–3.14 (`requirements-data.txt`가 핀한 numpy 2.5.x가 요구):

```bash
pip install -r requirements-data.txt
python -m unittest discover -s tests -t .
```

## 변환

Zenodo에서 받은 zip을 풀고 피험자 폴더 하나를 지정합니다.

```bash
python scripts/convert_subject.py --subject /path/to/Totalsegmentator_dataset_small_v201/s0011 --output private-assets/local-case
```

`private-assets/local-case.glb`와 `.json`이 생기면 앱의 **Open local case**가 로드합니다(개발/preview 서버가 loopback에만 그 경로들을 제공합니다). 다른 파일은 **Import GLB + manifest**로 브라우저 메모리에서 직접 엽니다.

같은 피험자의 맥락 레이어는 두 번째 스크립트가 같은 출력 stem에 붙입니다.

```bash
python scripts/splat_context.py --subject /path/to/Totalsegmentator_dataset_small_v201/s0011 --output private-assets/local-case
```

`local-case.context.ply`(3DGS 레이아웃의 PLY)와 `.context.json`이 생기면 **Open local case**가 레이어까지 함께 열고, 가져오기에서는 GLB + manifest + PLY + context JSON 네 파일을 한 번에 선택합니다. 레이어는 선택 사항입니다. 전신 CT 한 명은 약 170만 splat·90 MB, 상한은 2,000,000입니다. 상한을 넘는 볼륨은 가장 큰 밴드의 stride를 올려 맞추고 요청값과 실제값을 둘 다 JSON에 적습니다.

TopBrain·TopCoW 릴리스는 라벨맵 하나에 구조가 다 들어 있으므로, 먼저 한 케이스를 피험자 폴더로 꺼냅니다.

```bash
python scripts/prepare_topbrain_subject.py --release /path/to/TopBrain_Data_Release_Batches1n2nTA36_081726 --patient 001 --modality ct --output private-assets/subjects/topcow_ct_001
python scripts/convert_subject.py --subject private-assets/subjects/topcow_ct_001 --output private-assets/local-case
python scripts/splat_context.py --subject private-assets/subjects/topcow_ct_001 --output private-assets/local-case
```

`--modality mr`은 같은 환자의 MRA를 꺼내고(다른 촬영이라 CTA와 정합돼 있지 않습니다), `--labels v1`은 정맥·두개외 동맥이 포함된 모달리티별 라벨을, `--kind topcow`는 TopCoW 릴리스의 13클래스 라벨을 씁니다. 파이프라인과 좌표 계약의 상세는 [docs/DATA.md](docs/DATA.md)에 있습니다.

## 공개 데모 게시

정적 데모는 GitHub Pages의 프로젝트 경로 [https://gj21kr.github.io/topbrain-studio/](https://gj21kr.github.io/topbrain-studio/)에 게시할 수 있습니다. 저장소의 **Settings → Pages → Build and deployment → Source**를 **GitHub Actions**로 설정한 다음, `main` 브랜치에 변경 사항을 반영하거나 **Actions → Publish demo to GitHub Pages → Run workflow**에서 `main`을 선택하세요. 배포가 끝나면 해당 Actions 실행의 `github-pages` 환경 URL을 확인합니다. [GitHub Pages 설정 안내](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)

배포 워크플로는 `npm ci`, `npm test`, `npm run build`, `npm run check:public-build`를 통과한 `dist/`만 업로드합니다. 공개 빌드에서는 Vite의 base URL이 저장소 이름을 따르고(`GITHUB_REPOSITORY`에서 읽으며, 지금은 `/topbrain-studio/`, 저장소 이름을 바꾸면 그대로 따라갑니다) 평소 로컬 개발 빌드는 `/`를 사용합니다. 로컬에서 Pages 빌드를 점검하려면 PowerShell에서 다음을 실행하세요.

```powershell
$env:GITHUB_PAGES = 'true'
npm ci
npm test
npm run build
npm run check:public-build
Remove-Item Env:GITHUB_PAGES
```

**게시 경계:** Pages는 공개 서비스입니다. `public/`과 `dist/`에는 데모 코드·파비콘, `reference/bodyparts3d.glb`, `reference/bodyparts3d.json`, `reference/ATTRIBUTION.txt`, 그리고 `cases/topbrain-ct-001/`의 `case.glb`, `case.json`, `case.context.ply`, `case.context.json`, `ATTRIBUTION.txt`만 허용하며 여덟 파일이 모두 있어야 배포합니다. 빌드 검사는 digest가 고정된 그 파일들 외의 파일·디렉터리·심볼릭 링크·하드 링크·대용량 번들을 거부하고, 사례 manifest·context JSON·PLY가 같은 TopBrain CTA 영상(checksum)과 같은 splat 예산을 가리키는지 확인합니다. 파일명과 manifest의 출처 표기는 라이선스를 증명하지 못하므로 공개 에셋의 원본과 변환 내역은 별도로 검토합니다. 승인되지 않은 데이터셋 원본·파생물(GLB, manifest, splat PLY)은 저장소, `public/`, Pages artifact 어디에도 넣지 마세요. 공개 페이지에는 로컬 개발 서버의 **Open local case** 기능이 없습니다. 다른 사례는 각 방문자가 **Import GLB + manifest**로 자신의 브라우저에서 직접 선택하며, 이 과정에서 파일은 서버로 업로드되지 않습니다.

## 공개 TopBrain CTA 사례

**Open TopBrain CTA case**는 TopBrain 2025 릴리스의 CTA 피험자 `topcow_ct_001`을 엽니다. 23개 혈관 메시(TopBrain v2 라벨, 원본 voxel 격자)와 같은 영상의 CTA splat 레이어가 함께 로드됩니다. 웹 다운로드를 위해 레이어는 `--max-splats 650000`으로 만들어 bone·contrast는 2 voxel, 연부조직은 4 voxel 간격으로 줄였고(624,246 splats, 33 MB), 요청한 stride와 실제 stride를 `case.context.json`에 기록합니다. 라이선스는 opendata.swiss 이용 약관(출처 표기 필수, 비상업 이용 자유, 상업 이용은 데이터 소유자 University Hospital Zurich의 허가)이며 이 데모는 비상업 개인 포트폴리오입니다. 재사용 시 [ATTRIBUTION.txt](https://gj21kr.github.io/topbrain-studio/cases/topbrain-ct-001/ATTRIBUTION.txt)의 표기와 같은 조건을 유지해야 합니다. 그 외 TopBrain·TopCoW 파생물은 로컬에만 둡니다.

## 공개 BodyParts3D 참조 아틀라스

첫 방문 시 공개 참조 모델이 자동으로 로드됩니다. 요청이 실패하면 코드로 만든 모식도가 표시되며, 화면에서 모식도로 전환하거나 BodyParts3D를 다시 열 수 있습니다. 게시 후 정적 파일의 주소는 [bodyparts3d.glb](https://gj21kr.github.io/topbrain-studio/reference/bodyparts3d.glb), [bodyparts3d.json](https://gj21kr.github.io/topbrain-studio/reference/bodyparts3d.json), [ATTRIBUTION.txt](https://gj21kr.github.io/topbrain-studio/reference/ATTRIBUTION.txt)입니다.

공개 모델은 [BodyParts3D 4.0 PART-OF 축소 OBJ 아카이브](https://dbarchive.biosciencedbc.jp/data/bodyparts3d/20130619/partof_BP3D_4.0_obj_99.zip)의 24개 선택 구조를 웹 표시용 GLB로 변환한 참조 해부학입니다. 뇌혈관·두개골·뇌와 근위부 혈관인 상행대동맥, 대동맥활, 팔머리동맥, 좌우 총경동맥·쇄골하동맥이 포함됩니다. 복부까지 이어지는 전체 대동맥은 포함하지 않습니다. 원본 좌표의 mm/Z-up을 glTF의 m/Y-up으로 바꾸며, 정확한 구조별 출처와 변환 내역은 공개 manifest와 `ATTRIBUTION.txt`에 기록합니다. 필수 표기: **“BodyParts3D, © The Database Center for Life Science licensed under CC Attribution 4.0 International”**. [공식 다운로드 목록](https://dbarchive.biosciencedbc.jp/en/bodyparts3d/download.html), [공식 데이터 이용 허락](https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html), [CC BY 4.0 약관](https://creativecommons.org/licenses/by/4.0/)을 함께 확인하세요. 이 공개 데이터의 CC BY 4.0은 프로젝트 코드의 라이선스를 정하지 않습니다.

공식 아카이브에는 좌우 총경동맥과 내경동맥 사이, 좌우 쇄골하동맥과 척추동맥 사이의 목 구간을 잇는 메시가 없습니다. 화면의 점선 네 개는 가장 가까운 원본 메시 꼭짓점 사이를 잇는 **모식적 위치 안내선**입니다. 공식 BodyParts3D 혈관 메시나 검증된 혈관 주행·길이로 해석하지 마세요. 이 구분과 간격은 공개 manifest의 `connectionGuides` 및 `ATTRIBUTION.txt`에 기록합니다.

[공식 데이터베이스 설명](https://dbarchive.biosciencedbc.jp/en/bodyparts3d/desc.html)에 따르면 BodyParts3D는 성인 남성의 **참조 아틀라스**입니다. 가져온 TotalSegmentator 사례와 동일한 피험자 데이터가 아니며, 사례 간 정합도 수행하지 않습니다. 따라서 참조 모델과 가져온 분할을 동일 공간에 맞는 것으로 해석하거나 임상적 비교에 사용하지 마세요.

## BP/HR 맥동 미리보기의 범위

심박수(HR)는 화면의 박동 주기만, 수축기·이완기 혈압(SBP/DBP)은 표시 압력 범위를 정합니다. 맥압(SBP−DBP)에 따른 3D 동맥의 발광 대비 변화는 ±10% 이내이며, 그래프 파형은 모식적 보간으로 측정된 압력·혈류 파형이 아닙니다. [AHA의 혈압 설명](https://www.heart.org/en/health-topics/high-blood-pressure/blood-pressure-explained)과 [심박수 설명](https://www.heart.org/en/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure/all-about-heart-rate-pulse)은 입력값의 일반적 의미를 설명합니다. [뇌혈류 자동조절 원연구](https://pubmed.ncbi.nlm.nih.gov/2492126/)는 실제 동맥압 변화와 Doppler 혈류 속도를 측정했습니다. 이 미리보기는 그런 측정이나 혈역학 계산을 하지 않으므로 혈류 속도·방향·유량·국소 관류 또는 개인별 뇌혈류 자동조절을 추정하지 않습니다.

## 구성

```
scripts/convert_subject.py   NIfTI → GLB + manifest. 두 피험자 레이아웃(마스크 폴더·라벨맵), 좌표 변환, marching cubes, GLB 검증, 구조 카탈로그 2종
scripts/prepare_topbrain_subject.py  TopBrain/TopCoW 릴리스의 한 케이스 → 라벨맵 피험자 폴더(labelmap.json·dataset.json 포함)
scripts/splat_context.py     CT/CTA/MRA → Gaussian splat PLY + context JSON. HU·백분위 전달함수, 자동 stride, PLY 검증
scripts/prepare_bodyparts3d.py  BodyParts3D 공식 아카이브 → 공개 참조 아틀라스 GLB + manifest + ATTRIBUTION
scripts/check-public-build.mjs  Pages 배포 전 dist/ 검사: 허용 파일·크기, 참조 파일 digest, base URL
src/model.ts                 manifest·context 검증, GLB·PLY 사전 검사, connection guide 검증, 뷰어 상태
src/Viewer.tsx               three.js 씬, 로더, Spark splat 레이어, 분해 애니메이션, 맥동·안내선·라벨 배치
src/App.tsx                  탐색 UI. 참조 아틀라스 자동 로드, 로컬 케이스, 가져오기
src/FlowPanel.tsx, flow.ts   BP/HR 맥동 미리보기(모식적 파형, 혈역학 계산 아님)
src/study.ts, arterial.ts    모식도 학습 경로, 동맥 구조 판별
tests/                       Python 50 · TypeScript 20 (전부 합성 fixture)
.github/workflows/ci.yml     Python 3.12·3.14 + Node 22
.github/workflows/pages.yml  main → GitHub Pages(테스트·빌드·공개 빌드 검사 통과 시)
```

## 다음

- **splat 레이어의 학습.** 지금의 레이어는 복셀 초기화 그대로입니다(Gaussian 하나 = 복셀 하나, 크기는 복셀 반폭). 렌더 손실로 위치·크기·불투명도를 몇 단계 최적화하면 같은 화질을 훨씬 적은 splat으로 낼 수 있고, 그때는 원본 복셀 대비 오차를 context JSON에 기록합니다.
- **측정된 단순화.** 1.5 mm 격자의 marching cubes 출력은 계단 모양이 남고, 조밀한 구조는 뷰어의 메시당 상한에 닿습니다. 스무딩·decimation을 허용하되 원본 복셀과의 거리를 측정해 manifest에 기록합니다.

## 독립성

[Model X Studio](https://github.com/ashemag/model-x-studio)의 부품 탐색 UI에서 영감을 받은 독립 구현이며, 그 저장소의 코드나 모델은 포함하지 않습니다.
