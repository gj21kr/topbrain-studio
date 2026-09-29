# Splatomy

공개 CT 데이터셋에서 해부 구조를 3D로 꺼내 브라우저에서 탐색하는 개인 프로젝트입니다. Python 변환기가 [TotalSegmentator 데이터셋](https://doi.org/10.5281/zenodo.10047292)(CC BY 4.0)의 한 피험자 — CT 한 장과 117개 구조의 ground-truth 분할 — 를 임베디드 GLB와 JSON manifest로 바꾸고, 같은 CT의 강도를 Gaussian splat **맥락 레이어**로 만들어 메시와 같은 좌표계에 깔며, three.js + [Spark](https://sparkjs.dev) 뷰어가 둘을 함께 읽습니다. 구조 검색, 그룹별 표시·투명도, 단독 보기, 카메라 프리셋, 분해(explode), 라벨, CT 맥락 on/off·농도를 제공합니다.

공개 데모([GitHub Pages](https://gj21kr.github.io/topbrain-studio/))의 첫 화면은 BodyParts3D 4.0 참조 아틀라스(CC BY 4.0)를 열고, 그 요청이 실패하면 코드로 그린 혈관 모식도가 나타납니다. 둘 다 특정 사례의 CT가 아닙니다. 실제 CT 해부학과 splat 레이어는 변환한 데이터를 열었을 때만 나타납니다. 이 도구는 진단 기기가 아닙니다.

## 이 저장소가 보여주는 것

- **의료영상 좌표계를 끝까지 추적한다.** voxel → NIfTI affine → RAS mm → glTF metres. 회전·shear·비등방 spacing·좌우 반전(LAS) 볼륨을 전부 처리하고, 구조마다 voxel/vertex 한 쌍을 manifest에 남겨 독립 검산이 가능합니다.
- **언어 경계를 건너는 계약을 양쪽에서 강제한다.** GLB 상한(150 MB, 메시당 정점 3,000,000·인덱스 9,000,000), chunk 레이아웃, "schema 2면 모든 구조가 자기 출처를 가진다"는 규칙이 Python 변환기와 TypeScript 뷰어에 각각 구현돼 있고, Python 테스트가 `src/model.ts`를 직접 읽어 두 숫자가 같은지 대조합니다. 한쪽만 바꾸면 CI가 깨집니다.
- **테스트가 무엇을 검증하는지 뮤테이션으로 확인했다.** 상수를 바꾸거나 분기를 지웠을 때 실제로 실패하는 테스트만 남겼습니다. 이 과정에서 "통과하지만 아무것도 검증하지 않는" 테스트 네 개를 찾아 고쳤습니다.
- **분할 경계와 원본 CT를 한 좌표계에 겹친다.** 메시는 분할이 *어디서 끝나는지*를, splat 레이어는 그 경계가 *어떤 조직 속에 앉아 있는지*를 보여줍니다. 복셀당 Gaussian 하나를 학습 없이 볼륨에서 직접 초기화하고(뼈·조영 혈관·연조직의 HU 전달함수), 뷰어는 PLY 헤더의 splat 수, CT 체크섬, voxel→glTF 행렬이 GLB manifest와 일치할 때만 레이어를 받습니다. 다른 피험자·다른 좌표계의 레이어는 열리지 않습니다.
- **데이터는 저장소에 없다.** 코드만 배포하고, 데이터셋은 Zenodo에서 직접 받아 로컬에서 변환합니다. 파생 에셋은 `private-assets/`에 두고 커밋하지 않습니다. 유일한 예외는 명시적으로 승인한 BodyParts3D 참조 아틀라스 세 파일이며, 공개 빌드 검사가 그 digest를 고정하고 다른 파일은 거부합니다.

## 데이터셋

Wasserthal, J. et al. *TotalSegmentator: Robust Segmentation of 104 Anatomic Structures in CT Images.* Radiology: AI 5(5), 2023. [doi:10.1148/ryai.230024](https://doi.org/10.1148/ryai.230024)
데이터: [Zenodo 10047292](https://doi.org/10.5281/zenodo.10047292) (v2.0.1, 1,228명, 117구조, 23.6 GB) · 탐색용 [소형판 10047263](https://doi.org/10.5281/zenodo.10047263) (102명, 3.2 GB). 라이선스 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

각 피험자 폴더는 `ct.nii.gz`와 `segmentations/<structure>.nii.gz`(구조별 0/1 마스크)로 구성됩니다. 변환기는 이 레이아웃을 그대로 읽습니다.

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

같은 피험자의 CT 맥락 레이어는 두 번째 스크립트가 같은 출력 stem에 붙입니다.

```bash
python scripts/splat_context.py --subject /path/to/Totalsegmentator_dataset_small_v201/s0011 --output private-assets/local-case
```

`local-case.context.ply`(3DGS 레이아웃의 PLY)와 `.context.json`이 생기면 **Open local case**가 레이어까지 함께 열고, 가져오기에서는 GLB + manifest + PLY + context JSON 네 파일을 한 번에 선택합니다. 레이어는 선택 사항입니다. 전신 CT 한 명은 약 170만 splat·90 MB, 상한은 2,000,000입니다. 파이프라인과 좌표 계약의 상세는 [docs/DATA.md](docs/DATA.md)에 있습니다.

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

**게시 경계:** Pages는 공개 서비스입니다. `public/`과 `dist/`에는 데모 코드·파비콘과 `reference/bodyparts3d.glb`, `reference/bodyparts3d.json`, `reference/ATTRIBUTION.txt`만 허용하며 세 참조 파일이 모두 있어야 배포합니다. 빌드 검사는 그 외 파일·디렉터리·심볼릭 링크·하드 링크·대용량 번들을 거부합니다. 파일명과 manifest의 출처 표기는 데이터셋 파생물이 아닌지 증명하지 못하므로 공개 참조 모델의 원본과 변환 내역을 별도로 검토해야 합니다. 데이터셋 원본·파생물(GLB, manifest, splat PLY)과 사례별 좌표 정보는 저장소, `public/`, Pages artifact 어디에도 넣지 마세요. 공개 페이지에는 로컬 개발 서버의 **Open local case** 기능이 없습니다. 실제 사례는 각 방문자가 **Import GLB + manifest**로 자신의 브라우저에서 직접 선택하며, 이 과정에서 파일은 서버로 업로드되지 않습니다.

## 공개 BodyParts3D 참조 아틀라스

첫 방문 시 공개 참조 모델이 자동으로 로드됩니다. 요청이 실패하면 코드로 만든 모식도가 표시되며, 화면에서 모식도로 전환하거나 BodyParts3D를 다시 열 수 있습니다. 게시 후 정적 파일의 주소는 [bodyparts3d.glb](https://gj21kr.github.io/topbrain-studio/reference/bodyparts3d.glb), [bodyparts3d.json](https://gj21kr.github.io/topbrain-studio/reference/bodyparts3d.json), [ATTRIBUTION.txt](https://gj21kr.github.io/topbrain-studio/reference/ATTRIBUTION.txt)입니다.

공개 모델은 [BodyParts3D 4.0 PART-OF 축소 OBJ 아카이브](https://dbarchive.biosciencedbc.jp/data/bodyparts3d/20130619/partof_BP3D_4.0_obj_99.zip)의 24개 선택 구조를 웹 표시용 GLB로 변환한 참조 해부학입니다. 뇌혈관·두개골·뇌와 근위부 혈관인 상행대동맥, 대동맥활, 팔머리동맥, 좌우 총경동맥·쇄골하동맥이 포함됩니다. 복부까지 이어지는 전체 대동맥은 포함하지 않습니다. 원본 좌표의 mm/Z-up을 glTF의 m/Y-up으로 바꾸며, 정확한 구조별 출처와 변환 내역은 공개 manifest와 `ATTRIBUTION.txt`에 기록합니다. 필수 표기: **“BodyParts3D, © The Database Center for Life Science licensed under CC Attribution 4.0 International”**. [공식 다운로드 목록](https://dbarchive.biosciencedbc.jp/en/bodyparts3d/download.html), [공식 데이터 이용 허락](https://dbarchive.biosciencedbc.jp/en/bodyparts3d/lic.html), [CC BY 4.0 약관](https://creativecommons.org/licenses/by/4.0/)을 함께 확인하세요. 이 공개 데이터의 CC BY 4.0은 프로젝트 코드의 라이선스를 정하지 않습니다.

공식 아카이브에는 좌우 총경동맥과 내경동맥 사이, 좌우 쇄골하동맥과 척추동맥 사이의 목 구간을 잇는 메시가 없습니다. 화면의 점선 네 개는 가장 가까운 원본 메시 꼭짓점 사이를 잇는 **모식적 위치 안내선**입니다. 공식 BodyParts3D 혈관 메시나 검증된 혈관 주행·길이로 해석하지 마세요. 이 구분과 간격은 공개 manifest의 `connectionGuides` 및 `ATTRIBUTION.txt`에 기록합니다.

[공식 데이터베이스 설명](https://dbarchive.biosciencedbc.jp/en/bodyparts3d/desc.html)에 따르면 BodyParts3D는 성인 남성의 **참조 아틀라스**입니다. 가져온 TotalSegmentator 사례와 동일한 피험자 데이터가 아니며, 사례 간 정합도 수행하지 않습니다. 따라서 참조 모델과 가져온 분할을 동일 공간에 맞는 것으로 해석하거나 임상적 비교에 사용하지 마세요.

## BP/HR 맥동 미리보기의 범위

심박수(HR)는 화면의 박동 주기만, 수축기·이완기 혈압(SBP/DBP)은 표시 압력 범위를 정합니다. 맥압(SBP−DBP)에 따른 3D 동맥의 발광 대비 변화는 ±10% 이내이며, 그래프 파형은 모식적 보간으로 측정된 압력·혈류 파형이 아닙니다. [AHA의 혈압 설명](https://www.heart.org/en/health-topics/high-blood-pressure/blood-pressure-explained)과 [심박수 설명](https://www.heart.org/en/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure/all-about-heart-rate-pulse)은 입력값의 일반적 의미를 설명합니다. [뇌혈류 자동조절 원연구](https://pubmed.ncbi.nlm.nih.gov/2492126/)는 실제 동맥압 변화와 Doppler 혈류 속도를 측정했습니다. 이 미리보기는 그런 측정이나 혈역학 계산을 하지 않으므로 혈류 속도·방향·유량·국소 관류 또는 개인별 뇌혈류 자동조절을 추정하지 않습니다.

## 구성

```
scripts/convert_subject.py   NIfTI → GLB + manifest. 좌표 변환, marching cubes, GLB 검증, 구조 카탈로그
scripts/splat_context.py     CT → Gaussian splat PLY + context JSON. HU 전달함수, 복셀 프레임의 Gaussian, PLY 검증
scripts/prepare_bodyparts3d.py  BodyParts3D 공식 아카이브 → 공개 참조 아틀라스 GLB + manifest + ATTRIBUTION
scripts/check-public-build.mjs  Pages 배포 전 dist/ 검사: 허용 파일·크기, 참조 파일 digest, base URL
src/model.ts                 manifest·context 검증, GLB·PLY 사전 검사, connection guide 검증, 뷰어 상태
src/Viewer.tsx               three.js 씬, 로더, Spark splat 레이어, 분해 애니메이션, 맥동·안내선·라벨 배치
src/App.tsx                  탐색 UI. 참조 아틀라스 자동 로드, 로컬 케이스, 가져오기
src/FlowPanel.tsx, flow.ts   BP/HR 맥동 미리보기(모식적 파형, 혈역학 계산 아님)
src/study.ts, arterial.ts    모식도 학습 경로, 동맥 구조 판별
tests/                       Python 37 · TypeScript 20 (전부 합성 fixture)
.github/workflows/ci.yml     Python 3.12·3.14 + Node 22
.github/workflows/pages.yml  main → GitHub Pages(테스트·빌드·공개 빌드 검사 통과 시)
```

## 다음

- **splat 레이어의 학습.** 지금의 레이어는 복셀 초기화 그대로입니다(Gaussian 하나 = 복셀 하나, 크기는 복셀 반폭). 렌더 손실로 위치·크기·불투명도를 몇 단계 최적화하면 같은 화질을 훨씬 적은 splat으로 낼 수 있고, 그때는 원본 복셀 대비 오차를 context JSON에 기록합니다.
- **측정된 단순화.** 1.5 mm 격자의 marching cubes 출력은 계단 모양이 남고, 조밀한 구조는 뷰어의 메시당 상한에 닿습니다. 스무딩·decimation을 허용하되 원본 복셀과의 거리를 측정해 manifest에 기록합니다.

## 독립성

[Model X Studio](https://github.com/ashemag/model-x-studio)의 부품 탐색 UI에서 영감을 받은 독립 구현이며, 그 저장소의 코드나 모델은 포함하지 않습니다.
